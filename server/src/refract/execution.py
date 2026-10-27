"""Direct job lifecycle and target execution."""

from __future__ import annotations

import asyncio
import json
import inspect
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from refract.config import DaemonConfig, TargetConfig
from refract.database import Database
from refract.drivers import DriverRegistry, DriverResult, StreamBridge
from refract.logging_setup import get_logger, log_context
from refract.models import ProjectView, TargetView, TERMINAL_STATES
from refract.result_metadata import JobResultMetadata, ExecutionMetadata, FailureMetadata, RetryMetadata, PublicTelemetry
from refract.planning import ExecutionPlan, parse_execution_plan, target_execution_key
from refract.streaming import StreamRecorder
from refract.scheduler import CancelEvent
from refract.telemetry import TelemetryAccumulator, TelemetryData
from refract.workers import run_sync


log = get_logger("execution")


@dataclass(slots=True, frozen=True)
class TargetExecutionResult:
    result: DriverResult
    target_id: str
    target_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _TargetAttempt:
    result: DriverResult | None = None
    recovered: bool = False
    recovery_phase: str = ""
    replay_blocked: bool = False


@dataclass(slots=True, frozen=True)
class _ExecutionContext:
    job_id: str
    project: ProjectView
    workflow: str
    context_key: str
    plan: ExecutionPlan
    prompt: str
    cwd: Path
    cancel_event: CancelEvent
    fresh_session: bool
    target: TargetConfig
    target_key: str
    session_id: str
    effective_prompt: str
    semaphore: asyncio.Semaphore
    accumulator: TelemetryAccumulator


class TargetExecutor:
    def __init__(
        self, config: DaemonConfig, database: Database, drivers: DriverRegistry,
        *, on_stream_commit: Callable[[str, int], Any] | None = None,
        ask_registry: Any = None,
    ) -> None:
        self.config = config
        self.database = database
        self.drivers = drivers
        self.on_stream_commit = on_stream_commit
        self.ask_registry = ask_registry
        self._target_semaphores: dict[str, asyncio.Semaphore] = {}
        self._target_active: dict[str, int] = {}
        self._target_users: dict[str, int] = {}

    def refresh_configuration(self, config: DaemonConfig) -> None:
        """Adopt settings; occupied capacity drains before replacing its limit."""
        self.config = config
        self._target_semaphores = {
            key: semaphore for key, semaphore in self._target_semaphores.items()
            if self._target_users.get(key, 0)
        }
    @staticmethod
    def _safe_telemetry_dump(accumulator: TelemetryAccumulator | None) -> dict[str, Any] | None:
        if accumulator is None:
            return None
        try:
            if accumulator._has_any_consumption or accumulator._context_used_tokens.value is not None:
                return accumulator.snapshot().model_dump(mode="json")
        except Exception:
            log.warning("Failed to serialize telemetry snapshot", exc_info=True)
        return None

    async def execute(self, *, job_id: str, project: ProjectView, workflow: str, context_key: str, plan: ExecutionPlan, prompt: str, cwd: Path, cancel_event: CancelEvent, fresh_session: bool = False) -> TargetExecutionResult:
        record = await run_sync(self.database.job_record, job_id)
        telemetry_state = json.loads(record.get("telemetry_state_json") or "{}") if record else {}
        accumulator = TelemetryAccumulator(telemetry_state if telemetry_state else None)

        last = DriverResult("REQUEST_FATAL", "", "", "No admissible target", "circuit_open")
        if not plan.selection.targets:
            tel = self._safe_telemetry_dump(accumulator)
            return TargetExecutionResult(last, "", metadata=self._result_metadata(last, None, None, circuit_open=True, telemetry=tel))
        if cancel_event.is_set():
            cancelled = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")
            tel = self._safe_telemetry_dump(accumulator)
            return TargetExecutionResult(cancelled, "", metadata=self._result_metadata(cancelled, None, None, telemetry=tel))
        target = await run_sync(self._select_target, plan.selection.targets, plan, job_id)
        if target is None:
            tel = self._safe_telemetry_dump(accumulator)
            return TargetExecutionResult(last, "", metadata=self._result_metadata(last, None, None, circuit_open=True, telemetry=tel))
        target_key = target_execution_key(target)
        session_id, effective_prompt = await self._prepare_session(
            project, context_key, workflow, target_key, prompt, fresh_session
        )
        await run_sync(self.database.event, job_id, "target.selected", {"workflow": workflow, "target": target.id, "attempt": 1})
        semaphore = self._target_semaphores.setdefault(target.id, asyncio.Semaphore(target.max_concurrency))
        self._target_users[target.id] = self._target_users.get(target.id, 0) + 1
        self._target_active.setdefault(target.id, 0)
        try:
            acquired = await self._acquire_target(semaphore, cancel_event)
        except BaseException as exc:
            self._release_capacity(target.id)
            await run_sync(self.database.release_target_probe, target_key, job_id)
            self._attach_exception_metadata(exc, None, None, accumulator=accumulator)
            raise
        if not acquired:
            self._release_capacity(target.id)
            await run_sync(self.database.release_target_probe, target_key, job_id)
            cancelled = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")
            tel = self._safe_telemetry_dump(accumulator)
            return TargetExecutionResult(cancelled, target.id, target_key, self._result_metadata(cancelled, target, None, telemetry=tel))
        return await self._execute_attempt(_ExecutionContext(
            job_id=job_id, project=project, workflow=workflow,
            context_key=context_key, plan=plan, prompt=prompt, cwd=cwd,
            cancel_event=cancel_event, fresh_session=fresh_session,
            target=target, target_key=target_key, session_id=session_id,
            effective_prompt=effective_prompt, semaphore=semaphore,
            accumulator=accumulator,
        ))

    async def _prepare_session(
        self, project: ProjectView, context_key: str, workflow: str,
        target_key: str, prompt: str, fresh_session: bool,
    ) -> tuple[str, str]:
        if fresh_session:
            return "", prompt
        session_id = await run_sync(self.database.session, project.id, context_key, workflow, target_key)
        effective_prompt = prompt if session_id else await run_sync(self._with_history, project.id, context_key, workflow, prompt)
        return session_id, effective_prompt

    async def _start_attempt(
        self, job_id: str, target: TargetConfig, plan: ExecutionPlan,
        workflow: str, session_id: str,
    ) -> tuple[float, bool, StreamRecorder | None, int]:
        attempt_number = await run_sync(self.database.record_job_attempt, job_id, target.id)
        started_at = time.monotonic()
        log.info("Target attempt started", extra={"event": "target.attempt_started", "job_id": job_id, "target_id": target.id, "profile": plan.profile, "workflow": workflow, "attempt": attempt_number, "timeout_s": plan.selection.timeout_s, "resumed_session": bool(session_id)})
        supports_streaming = await run_sync(self.drivers.supports_structured_streaming, target)
        recorder = None
        if supports_streaming:
            on_commit = None
            if self.on_stream_commit:
                on_commit = lambda cursor: self.on_stream_commit(job_id, cursor)
            recorder = await run_sync(StreamRecorder,
                database=self.database,
                job_id=job_id,
                attempt=attempt_number,
                target_id=target.id,
                backend=target.backend,
                on_commit=on_commit,
            )
        return started_at, supports_streaming, recorder, attempt_number

    async def _execute_attempt(self, context: _ExecutionContext) -> TargetExecutionResult:
        job_id = context.job_id
        project = context.project
        workflow = context.workflow
        context_key = context.context_key
        plan = context.plan
        prompt = context.prompt
        cancel_event = context.cancel_event
        fresh_session = context.fresh_session
        target = context.target
        target_key = context.target_key
        session_id = context.session_id
        semaphore = context.semaphore
        self._target_active[target.id] += 1
        try:
            started_at, supports_streaming, recorder, attempt_number = await self._start_attempt(
                job_id, target, plan, workflow, session_id
            )
        except BaseException:
            self._target_active[target.id] -= 1
            semaphore.release()
            self._release_capacity(target.id)
            await run_sync(self.database.release_target_probe, target_key, job_id)
            raise

        ask_env: dict[str, str] | None = None
        if self.ask_registry is not None:
            token = self.ask_registry.issue_token(
                job_id,
                workflow_timeout_s=plan.selection.timeout_s,
                started_at=started_at,
            )
            ask_url = f"http://{self.config.host}:{self.config.port}/ask"
            ask_env = {
                "REFRACT_ASK_URL": ask_url,
                "REFRACT_ASK_TOKEN": token,
            }

        attempt = _TargetAttempt()
        driver_exc: BaseException | None = None
        try:
            await self._recover_session(
                attempt=attempt, context=context, recorder=recorder,
                supports_streaming=supports_streaming, env=ask_env,
                attempt_number=attempt_number,
            )
        except BaseException as exc:
            driver_exc = exc
            duration_ms = int((time.monotonic() - started_at) * 1000)
            await run_sync(self.database.release_target_probe, target_key, job_id)
            self._attach_exception_metadata(exc, target, duration_ms, accumulator=context.accumulator)
            raise
        finally:
            if self.ask_registry is not None:
                self.ask_registry.revoke_token(job_id)
            if cancel_event.is_set() or isinstance(driver_exc, asyncio.CancelledError):
                attempt.result = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")
            try:
                await self._finish_recorder(recorder, attempt.result, driver_exc, cancel_event)
            except BaseException as exc:
                duration_ms = int((time.monotonic() - started_at) * 1000)
                await run_sync(self.database.release_target_probe, target_key, job_id)
                self._attach_exception_metadata(exc, target, duration_ms, accumulator=context.accumulator)
                raise
            finally:
                self._target_active[target.id] -= 1
                semaphore.release()
                self._release_capacity(target.id)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        return await self._complete_attempt(
            attempt, job_id, project, workflow, context_key, target, target_key,
            prompt, fresh_session, duration_ms,
            attempt_number=attempt_number,
            accumulator=context.accumulator,
        )

    async def _recover_session(
        self, *, attempt: _TargetAttempt, context: _ExecutionContext,
        recorder: StreamRecorder | None, supports_streaming: bool,
        env: dict[str, str] | None = None,
        attempt_number: int = 1,
    ) -> None:
        job_id = context.job_id
        project = context.project
        workflow = context.workflow
        context_key = context.context_key
        target = context.target
        prompt = context.prompt
        effective_prompt = context.effective_prompt
        session_id = context.session_id
        cwd = context.cwd
        timeout_s = context.plan.selection.timeout_s
        cancel_event = context.cancel_event
        fresh_session = context.fresh_session
        phase_prompt = effective_prompt
        phase_session = session_id
        for invocation_idx, phase in enumerate(("initial", "reconstruct", "fresh"), start=1):
            details = {"workflow": workflow, "target": target.id}
            if phase != "initial":
                details["phase"] = phase
                details["invocation"] = invocation_idx
                context.accumulator.invalidate_context()
                await run_sync(self.database.event, job_id, "target.session_recovery_started", details)
            attempt.result, has_tool_activity = await self._run_target_invocation(
                job_id=job_id,
                attempt=attempt_number,
                invocation=invocation_idx,
                accumulator=context.accumulator,
                target=target, prompt=phase_prompt, session_id=phase_session,
                cwd=cwd, timeout_s=timeout_s, cancel_event=cancel_event,
                recorder=recorder, supports_streaming=supports_streaming,
                env=env,
            )
            last = attempt.result
            await self._record_recovery_result(job_id, phase, details, last)
            attempt.replay_blocked = has_tool_activity and last.outcome != "SUCCESS"
            if last.outcome == "SUCCESS":
                attempt.recovered = phase != "initial"
                attempt.recovery_phase = phase if attempt.recovered else ""
                break
            if not self._can_recover(last, fresh_session, session_id, attempt.replay_blocked, cancel_event, phase):
                break
            if phase == "initial":
                phase_prompt = await run_sync(self._with_history, project.id, context_key, workflow, prompt)
                phase_session = ""
            elif phase_prompt != prompt:
                phase_prompt = prompt
            else:
                break

    async def _record_recovery_result(
        self, job_id: str, phase: str, details: dict[str, str], result: DriverResult,
    ) -> None:
        if phase != "initial":
            await run_sync(self.database.event, job_id, "target.session_recovery_finished", {
                **details, "outcome": result.outcome, "error_code": result.error_code,
            })
        if result.error_code == "context_overflow":
            await run_sync(self.database.event, job_id, "target.context_overflow", {
                **details, "error_code": "context_overflow",
            })

    @staticmethod
    def _can_recover(
        result: DriverResult, fresh_session: bool, session_id: str,
        replay_blocked: bool, cancel_event: CancelEvent, phase: str,
    ) -> bool:
        return not (
            fresh_session or not session_id or replay_blocked
            or cancel_event.is_set()
            or result.outcome in {"CANCELLED", "REQUEST_FATAL"}
            or result.error_code != "context_overflow"
            or phase == "fresh"
        )

    @staticmethod
    async def _finish_recorder(
        recorder: StreamRecorder | None, result: DriverResult | None,
        driver_exc: BaseException | None, cancel_event: CancelEvent,
    ) -> None:
        if not recorder:
            return
        if result is None:
            err_msg = str(driver_exc) if driver_exc else "execution_failed"
            result = DriverResult("REQUEST_FATAL", "", "", err_msg, "execution_error")
        if cancel_event.is_set() or result.outcome == "CANCELLED":
            status = "cancelled"
        elif result.outcome == "SUCCESS":
            status = "succeeded"
        else:
            status = "failed"
        try:
            await recorder.record({
                "kind": "attempt.finished",
                "data": {
                    "status": status,
                    "outcome": result.outcome,
                    "error_code": result.error_code,
                },
            })
        finally:
            await recorder.close()

    async def _complete_attempt(
        self, attempt: _TargetAttempt, job_id: str, project: ProjectView,
        workflow: str, context_key: str, target: TargetConfig, target_key: str,
        prompt: str, fresh_session: bool, duration_ms: int,
        attempt_number: int = 1,
        accumulator: TelemetryAccumulator | None = None,
    ) -> TargetExecutionResult:
        last = attempt.result
        await run_sync(self.database.event, job_id, "target.attempt_finished", {"workflow": workflow, "target": target.id, "attempt": attempt_number, "outcome": last.outcome, "error_code": last.error_code})
        log.info("Target attempt finished", extra={"event": "target.attempt_finished", "job_id": job_id, "target_id": target.id, "workflow": workflow, "attempt": attempt_number, "outcome": last.outcome, "error_code": last.error_code, "duration_ms": duration_ms})
        if last.outcome == "SUCCESS":
            await run_sync(self.database.record_target_success, target_key, self.config.breaker_base_cooldown_s)
            if not fresh_session:
                await self._store_turn(attempt, job_id, project, workflow, context_key, target, target_key, prompt)
        else:
            await self._update_target_health(last, target_key, job_id, attempt.replay_blocked)
        telemetry = self._safe_telemetry_dump(accumulator)
        return TargetExecutionResult(last, target.id, target_key, self._result_metadata(last, target, duration_ms, replay_blocked=attempt.replay_blocked, telemetry=telemetry))

    async def _store_turn(
        self, attempt: _TargetAttempt, job_id: str, project: ProjectView,
        workflow: str, context_key: str, target: TargetConfig, target_key: str, prompt: str,
    ) -> None:
        await run_sync(self.database.append_turn,
            project_id=project.id,
            context_key=context_key,
            role=workflow,
            target_id=target.id,
            target_key=target_key,
            session_id=attempt.result.session_id,
            prompt=prompt,
            response=attempt.result.text,
            clear_sessions=attempt.recovered,
        )
        if attempt.recovered:
            await run_sync(self.database.event,
                job_id,
                "target.session_replaced",
                {"workflow": workflow, "target": target.id, "phase": attempt.recovery_phase},
            )

    async def _update_target_health(
        self, result: DriverResult, target_key: str, job_id: str, replay_blocked: bool,
    ) -> None:
        health = await run_sync(self.database.target_health, target_key)
        held_probe = health.get("probe_job_id") == job_id
        if result.outcome in {"CANCELLED", "REQUEST_FATAL"}:
            if held_probe:
                await run_sync(self.database.release_target_probe, target_key, job_id)
            return
        if result.error_code == "context_overflow" or replay_blocked:
            if held_probe:
                await run_sync(self.database.release_target_probe, target_key, job_id)
        elif result.outcome == "TARGET_FATAL":
            await run_sync(self._record_failure, target_key, immediate=True, failed_probe=False)
        elif result.outcome == "RETRYABLE":
            await run_sync(self._record_failure, target_key, failed_probe=held_probe)
        elif held_probe:
            await run_sync(self.database.release_target_probe, target_key, job_id)

    @classmethod
    def _attach_exception_metadata(
        cls,
        exc: BaseException,
        target: TargetConfig | None,
        duration_ms: int | None,
        *,
        accumulator: TelemetryAccumulator | None = None,
    ) -> None:
        cancelled = isinstance(exc, asyncio.CancelledError)
        result = DriverResult(
            "CANCELLED" if cancelled else "REQUEST_FATAL",
            "",
            "",
            "cancelled" if cancelled else str(exc),
            "cancelled" if cancelled else "execution_error",
        )
        try:
            telemetry = cls._safe_telemetry_dump(accumulator)
            setattr(exc, "_refract_result_metadata", cls._result_metadata(result, target, duration_ms, telemetry=telemetry))
        except (AttributeError, TypeError):
            pass

    @staticmethod
    def _result_metadata(
        result: DriverResult,
        target: TargetConfig | None,
        duration_ms: int | None,
        *,
        replay_blocked: bool = False,
        circuit_open: bool = False,
        telemetry: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if result.outcome == "SUCCESS":
            failure_kind, retryable = None, None
        elif result.outcome == "CANCELLED":
            failure_kind, retryable = "cancelled", False
        elif circuit_open or result.error_code == "circuit_open":
            failure_kind, retryable = "circuit_open", False
        elif replay_blocked:
            failure_kind, retryable = "replay_blocked", False
        elif result.error_code == "context_overflow":
            failure_kind, retryable = "context_overflow", True
        elif result.outcome == "REQUEST_FATAL":
            failure_kind, retryable = "request_fatal", False
        elif result.outcome == "TARGET_FATAL":
            failure_kind, retryable = "target_fatal", False
        elif result.outcome == "RETRYABLE":
            failure_kind, retryable = "retryable", False
        else:
            failure_kind, retryable = "request_fatal", False
        model_name = result.model
        if model_name is None and target is not None:
            model_name = target.model or None
        canonical = JobResultMetadata(
            execution=ExecutionMetadata(model=model_name, duration_ms=duration_ms),
            failure=FailureMetadata(kind=failure_kind) if failure_kind else None,
            retry=RetryMetadata(retryable=retryable, next_target=None),
            telemetry=PublicTelemetry.from_internal(
                TelemetryData.model_validate(telemetry)
            ) if telemetry is not None else PublicTelemetry(),
        )
        return canonical.model_dump(mode="json")

    async def _run_target_invocation(
        self,
        *,
        job_id: str,
        attempt: int,
        invocation: int,
        accumulator: TelemetryAccumulator,
        target: TargetConfig,
        prompt: str,
        session_id: str,
        cwd: Path,
        timeout_s: float,
        cancel_event: threading.Event,
        recorder: StreamRecorder | None,
        supports_streaming: bool,
        env: dict[str, str] | None = None,
    ) -> tuple[DriverResult, bool]:
        bridge = StreamBridge(queue_capacity=256) if supports_streaming else None
        invocation_observed_consumption = False

        async def _handle_telemetry(event: dict[str, Any]) -> None:
            nonlocal invocation_observed_consumption
            data = event.get("data")
            if not isinstance(data, dict):
                return
            source = data.get("source", "stream")
            quality = data.get("quality", "reported")
            observed_at = data.get("observed_at")

            if data.get("invalidate_context") is True:
                accumulator.invalidate_context(observed_at=observed_at)
            elif "context_used_tokens" in data or "context_window_size" in data or "context_remaining_percent" in data:
                accumulator.record_context_snapshot(
                    used_tokens=data.get("context_used_tokens"),
                    window_size=data.get("context_window_size"),
                    remaining_percent=data.get("context_remaining_percent"),
                    source=source,
                    quality=quality,
                    observed_at=observed_at,
                    attempt=attempt,
                    invocation=invocation,
                )

            if "total_input_tokens" in data or "total_output_tokens" in data:
                accumulator.reconcile_cumulative(
                    attempt=attempt,
                    invocation=invocation,
                    total_input=data.get("total_input_tokens"),
                    total_output=data.get("total_output_tokens"),
                    cache_read=data.get("cache_read_tokens"),
                    cache_write=data.get("cache_write_tokens"),
                    source=source,
                    quality=quality,
                    observed_at=observed_at,
                )
                invocation_observed_consumption = True
            elif "input_tokens" in data or "output_tokens" in data or "cache_read_tokens" in data or "cache_write_tokens" in data:
                accumulator.record_consumption(
                    attempt=attempt,
                    invocation=invocation,
                    response_id=data.get("response_id"),
                    input_tokens=data.get("input_tokens"),
                    output_tokens=data.get("output_tokens"),
                    cache_read_tokens=data.get("cache_read_tokens"),
                    cache_write_tokens=data.get("cache_write_tokens"),
                    is_snapshot=bool(data.get("is_snapshot", False)),
                    source=source,
                    quality=quality,
                    observed_at=observed_at,
                )
                invocation_observed_consumption = True

            snap = accumulator.snapshot()
            await run_sync(self.database.merge_job_telemetry, job_id, snap)

        async def drain_stream() -> None:
            if bridge:
                async for event in bridge.consumer():
                    if isinstance(event, dict) and event.get("kind") == "telemetry.updated":
                        try:
                            await _handle_telemetry(event)
                        except Exception:
                            log.warning("Telemetry update failed", exc_info=True)
                    if recorder and supports_streaming:
                        await recorder.record(event)
                if recorder and supports_streaming:
                    await recorder.flush()

        drain_task = asyncio.create_task(drain_stream()) if bridge else None
        attempt_result: DriverResult | None = None
        driver_exc: BaseException | None = None
        try:
            with log_context(target_id=target.id):
                attempt_result = await self.drivers.execute(
                    target=target,
                    prompt=prompt,
                    cwd=cwd,
                    session_id=session_id,
                    timeout_s=timeout_s,
                    cancel_event=cancel_event,
                    emitter=bridge.emit if bridge else None,
                    env=env,
                )
        except BaseException as exc:
            driver_exc = exc
            raise
        finally:
            if bridge:
                await bridge.close()
            if drain_task:
                await drain_task
            if cancel_event.is_set() or isinstance(driver_exc, asyncio.CancelledError):
                attempt_result = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")
            # Record unknown contribution and finalize even when the driver raises.
            if not invocation_observed_consumption:
                accumulator.record_missing_contribution(attempt=attempt, invocation=invocation)
            accumulator.finalize_invocation(attempt=attempt, invocation=invocation)
            try:
                await run_sync(self.database.merge_job_telemetry, job_id, accumulator.snapshot())
            except Exception:
                log.warning("Could not persist final invocation telemetry", exc_info=True)

        has_tool_activity = bridge.has_tool_activity if bridge else False
        if attempt_result is None:
            err_msg = str(driver_exc) if driver_exc else "execution_failed"
            attempt_result = DriverResult("REQUEST_FATAL", "", "", err_msg, "execution_error")

        return attempt_result, has_tool_activity

    def _release_capacity(self, target_id: str) -> None:
        self._target_users[target_id] -= 1
        if not self._target_users[target_id]:
            self._target_users.pop(target_id)
            self._target_semaphores.pop(target_id, None)
            self._target_active.pop(target_id, None)

    @staticmethod
    async def _acquire_target(semaphore: asyncio.Semaphore, cancel_event: CancelEvent) -> bool:
        if cancel_event.is_set():
            return False
        acquire = asyncio.create_task(semaphore.acquire())
        cancelled = asyncio.create_task(cancel_event.wait_async())
        accepted = False
        try:
            await asyncio.wait((acquire, cancelled), return_when=asyncio.FIRST_COMPLETED)
            accepted = acquire.done() and not cancel_event.is_set()
            return accepted
        finally:
            acquire.cancel()
            cancelled.cancel()
            await asyncio.gather(acquire, cancelled, return_exceptions=True)
            if not accepted and not acquire.cancelled() and acquire.exception() is None:
                semaphore.release()

    def _select_target(self, target_ids: tuple[str, ...], plan: ExecutionPlan, job_id: str = "") -> TargetConfig | None:
        now = datetime.now(timezone.utc)
        healthy: list[TargetConfig] = []
        claimed_probes: list[str] = []
        for target_id in target_ids:
            target = plan.target(target_id)
            target_key = target_execution_key(target)
            if not self._admit_target(target, target_key, now, job_id, claimed_probes):
                continue
            healthy.append(target)
            if self._target_active.get(target.id, 0) < target.max_concurrency:
                self._release_unselected_probes(claimed_probes, target_key, job_id)
                return target
        if not healthy:
            return None
        selected = healthy[0]
        self._release_unselected_probes(claimed_probes, target_execution_key(selected), job_id)
        return selected

    def _admit_target(
        self, target: TargetConfig, target_key: str, now: datetime,
        job_id: str, claimed_probes: list[str],
    ) -> bool:
        health = self.database.target_health(target_key)
        open_until = str(health["circuit_open_until"])
        probe_job = str(health.get("probe_job_id", ""))
        try:
            half_open = bool(open_until) and datetime.fromisoformat(open_until) <= now and not probe_job
        except ValueError:
            half_open = False
        if self.is_circuit_open(open_until, now, probe_job) or not self.drivers.available(target):
            return False
        if half_open:
            if not job_id or not self.database.claim_target_probe(target_key, job_id, now.isoformat()):
                return False
            claimed_probes.append(target_key)
        return True

    def _release_unselected_probes(self, claimed_probes: list[str], selected_key: str, job_id: str) -> None:
        for claimed_key in claimed_probes:
            if claimed_key != selected_key:
                self.database.release_target_probe(claimed_key, job_id)

    def _record_failure(self, target_key: str, *, immediate: bool = False, failed_probe: bool = False) -> None:
        self.database.record_target_failure(
            target_key,
            threshold=self.config.breaker_failure_threshold,
            base_cooldown_s=self.config.breaker_base_cooldown_s,
            max_cooldown_s=self.config.breaker_max_cooldown_s,
            failed_probe=failed_probe,
            immediate=immediate,
        )

    @staticmethod
    def is_circuit_open(value: str, now: datetime, probe_job_id: str = "") -> bool:
        if probe_job_id:
            return True
        if not value:
            return False
        try:
            return datetime.fromisoformat(value) > now
        except ValueError:
            return False

    def _with_history(self, project_id: str, context_key: str, role: str, prompt: str) -> str:
        turns = self.database.recent_turns(project_id, context_key, role, self.config.history_turns)
        if not turns:
            return prompt
        blocks: list[str] = []
        size = 0
        for turn in reversed(turns):
            block = f"User:\n{turn['prompt']}\n\nAssistant:\n{turn['response']}"
            encoded = len(block.encode("utf-8"))
            if size + encoded > self.config.history_bytes:
                break
            blocks.append(block)
            size += encoded
        if not blocks:
            # Every stored turn exceeded the byte budget. Returning the
            # unwrapped prompt keeps reconstruction identical to the original
            # prompt so callers can skip a redundant prompt-only recovery.
            return prompt
        blocks.reverse()
        return f"Previous context:\n\n{'\n\n---\n\n'.join(blocks)}\n\nCurrent request:\n\n{prompt}"

    def views(self, targets: tuple[TargetConfig, ...]) -> list[TargetView]:
        now = datetime.now(timezone.utc)
        result: list[TargetView] = []
        for target in targets:
            target_key = target_execution_key(target)
            health = self.database.target_health(target_key)
            open_until = str(health["circuit_open_until"])
            probe_job_id = str(health["probe_job_id"])
            probing = bool(probe_job_id)
            if probing:
                breaker_state = "half_open"
            elif not open_until:
                breaker_state = "closed"
            elif self.is_circuit_open(open_until, now):
                breaker_state = "open"
            else:
                breaker_state = "half_open"
            result.append(TargetView(id=target.id, model=target.model, max_concurrency=target.max_concurrency, active=self._target_active.get(target.id, 0), healthy=self.drivers.available(target) and not self.is_circuit_open(open_until, now), circuit_open_until=open_until, breaker_state=breaker_state, cooldown_s=int(health["cooldown_s"]), probing=probing))
        return result


JobNotifier = Callable[[str], Awaitable[None]]
JobTerminalCallback = Callable[[str, str], Any]


async def _noop_notifier(_: str) -> None:
    return None


class JobRunner:
    def __init__(
        self,
        database: Database,
        targets: TargetExecutor,
        *,
        is_closing: Callable[[], bool],
        notifier: JobNotifier | None = None,
        on_terminal: JobTerminalCallback | None = None,
    ) -> None:
        self.database = database
        self.targets = targets
        self.is_closing = is_closing
        self.notifier = notifier or _noop_notifier
        self.on_terminal = on_terminal or (lambda _job_id, _state: None)

    async def _notify(self, job_id: str) -> None:
        try:
            await self.notifier(job_id)
        except Exception:
            log.warning(
                "Job resource notification failed",
                extra={"event": "job.resource_notification_failed", "job_id": job_id},
                exc_info=True,
            )

    async def _terminal(self, job_id: str, state: str) -> None:
        try:
            result = self.on_terminal(job_id, state)
            if inspect.isawaitable(result):
                await result
        except Exception:
            log.exception(
                "Job terminal transition callback failed",
                extra={"event": "job.terminal_callback_failed", "job_id": job_id, "state": state},
            )

    async def run(self, job_id: str, cancel_event: CancelEvent) -> None:
        started_at = time.monotonic()
        record = await run_sync(self.database.job_record, job_id)
        if record is None or record["state"] != "queued":
            return
        project_id = str(record["project_id"])
        project = await self._prepare_job(job_id, project_id, cancel_event)
        if project is None:
            return
        root = Path(project.root)
        log.info("Job started", extra={"event": "job.started", "job_id": job_id, "project_id": project.id, "workflow": record["workflow"]})
        final_state = "failed"
        committed_state: str | None = None
        execution_metadata: dict[str, Any] | None = None
        try:
            await run_sync(self.database.start_job, job_id)
            await self._notify(job_id)
            plan = parse_execution_plan(json.loads(record["execution_plan_json"]))
            execution = await self.targets.execute(
                job_id=job_id,
                project=project,
                workflow=record["workflow"],
                context_key=record["context_key"],
                plan=plan,
                prompt=record["prompt"],
                cwd=root,
                cancel_event=cancel_event,
                fresh_session=bool(record.get("fresh_session", 0)),
            )
            execution_metadata = execution.metadata
            if execution.result.outcome != "SUCCESS" or cancel_event.is_set():
                final_state = self._failure_state(cancel_event)
                await run_sync(self.database.finish_job, job_id, final_state, error=execution.result.error or execution.result.outcome, metadata=execution_metadata)
                committed_state = final_state
                await self._terminal(job_id, final_state)
                await self._notify(job_id)
                return
            await self._finish_success(job_id, project, record, execution)
            committed_state = "succeeded"
            await self._terminal(job_id, committed_state)
            await self._notify(job_id)
        except asyncio.CancelledError as exc:
            await self._finish_cancelled_job(job_id, exc, committed_state)
            raise
        except Exception as exc:
            await self._finish_failed_job(job_id, exc, final_state, committed_state, execution_metadata)
        finally:
            completed = await run_sync(self.database.job, job_id)
            log.info("Job finished", extra={"event": "job.finished", "job_id": job_id, "project_id": project_id, "state": completed.state if completed else "unknown", "duration_ms": round((time.monotonic() - started_at) * 1000, 2)})

    async def _prepare_job(self, job_id: str, project_id: str, cancel_event: CancelEvent) -> ProjectView | None:
        if self.is_closing():
            # A reserved-but-undispatched queue item remains durable for restart.
            return None
        if cancel_event.is_set():
            state = "interrupted" if self.is_closing() else "cancelled"
            await run_sync(self.database.finish_job, job_id, state, error="cancelled before execution")
            await self._terminal(job_id, state)
            await self._notify(job_id)
            return None
        project = await run_sync(self.database.project, project_id)
        if project is None:
            await run_sync(self.database.finish_job, job_id, "failed", error="Project was removed")
            await self._terminal(job_id, "failed")
            await self._notify(job_id)
        return project

    def _failure_state(self, cancel_event: CancelEvent) -> str:
        if cancel_event.is_set() and self.is_closing():
            return "interrupted"
        if cancel_event.is_set():
            return "cancelled"
        return "failed"

    async def _finish_success(
        self, job_id: str, project: ProjectView, record: dict[str, Any],
        execution: TargetExecutionResult,
    ) -> None:
        if bool(record.get("fresh_session", 0)):
            await run_sync(self.database.finish_fresh_job_success,
                job_id=job_id,
                project_id=project.id,
                context_key=record["context_key"],
                role=record["workflow"],
                target_id=execution.target_id,
                target_key=execution.target_key,
                session_id=execution.result.session_id,
                prompt=record["prompt"],
                response=execution.result.text,
                metadata=execution.metadata,
            )
        else:
            await run_sync(self.database.finish_job, job_id, "succeeded", text=execution.result.text, target_id=execution.target_id, metadata=execution.metadata)

    async def _finish_cancelled_job(
        self, job_id: str, exc: asyncio.CancelledError, committed_state: str | None,
    ) -> None:
        completed = await run_sync(self.database.job, job_id)
        if completed is not None and completed.state in TERMINAL_STATES:
            committed_state = completed.state
            await self._terminal(job_id, committed_state)
        if committed_state is None:
            final_state = "interrupted" if self.is_closing() else "cancelled"
            execution_metadata = (
                getattr(exc, "_refract_result_metadata", None)
                or self.targets._result_metadata(
                    DriverResult("CANCELLED", "", "", "cancelled", "cancelled"), None, None
                )
            )
            await run_sync(self.database.finish_job, job_id, final_state, error="execution task cancelled", metadata=execution_metadata)
            await self._terminal(job_id, final_state)

    async def _finish_failed_job(
        self, job_id: str, exc: Exception, final_state: str,
        committed_state: str | None, execution_metadata: dict[str, Any] | None,
    ) -> None:
        if committed_state is not None:
            log.warning(
                "Post-terminal job operation failed",
                extra={"event": "job.post_terminal_failed", "job_id": job_id, "state": committed_state},
                exc_info=True,
            )
            return
        execution_metadata = (
            getattr(exc, "_refract_result_metadata", None)
            or execution_metadata
            or self.targets._result_metadata(
                DriverResult("REQUEST_FATAL", "", "", str(exc), "execution_error"), None, None
            )
        )
        log.exception(
            "Unexpected job failure",
            extra={"event": "job.exception", "job_id": job_id},
        )
        await run_sync(self.database.finish_job, job_id, final_state, error=str(exc), metadata=execution_metadata)
        await self._terminal(job_id, final_state)
        await self._notify(job_id)


__all__ = ["JobNotifier", "JobRunner", "TargetExecutor", "TargetExecutionResult"]
