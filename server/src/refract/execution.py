"""Direct job lifecycle and target execution."""

from __future__ import annotations

import asyncio
import json
import inspect
import hashlib
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from refract.config import DaemonConfig, RetryPolicy, TargetConfig
from refract.database import Database
from refract.drivers import DriverRegistry, DriverResult
from refract.logging_setup import get_logger, log_context
from refract.models import ProjectView, TargetView, TERMINAL_STATES
from refract.planning import ExecutionPlan, parse_execution_plan, target_execution_key
from refract.scheduler import CancelEvent
from refract.telemetry import CONSUMPTION_KEYS, TokenCounters
from refract.workers import run_sync


log = get_logger("execution")


@dataclass(slots=True, frozen=True)
class TargetExecutionResult:
    result: DriverResult
    target_id: str
    target_key: str = ""
    outcome: dict[str, Any] = field(default_factory=dict)
    session_key: str = ""
    scoped_session: str = ""


@dataclass(slots=True)
class _TargetAttempt:
    result: DriverResult | None = None
    replay_blocked: bool = False


@dataclass(slots=True, frozen=True)
class _ExecutionContext:
    job_id: str
    project: ProjectView
    workflow: str
    session: str
    plan: ExecutionPlan
    prompt: str
    cwd: Path
    cancel_event: CancelEvent
    fresh: bool
    target: TargetConfig
    target_key: str
    session_target_key: str
    session_id: str
    attempt_tokens: list[TokenCounters]
    skipped_targets: int | None = None
    bound_env: dict[str, str] = field(default_factory=dict)


def _counters_from(values: dict[str, Any]) -> TokenCounters:
    """Build one attempt's counters from a snapshot; a key absent from the snapshot is unknown."""
    counters = TokenCounters()
    counters.record_totals(
        input=values.get("input"),
        output=values.get("output"),
        cache_read=values.get("cache_read"),
        cache_write=values.get("cache_write"),
    )
    counters.record_context(used=values.get("context_used"), window=values.get("context_window"))
    return counters


def _job_tokens(attempt_tokens: list[TokenCounters], target: TargetConfig | None) -> dict[str, int | None] | None:
    """Sum consumption over attempts; context and configured window come from the latest attempt."""
    capacity = target.context_window if target is not None else None
    if not attempt_tokens and capacity is None:
        return None
    tokens: dict[str, int | None] = {}
    for key in CONSUMPTION_KEYS:
        known = [value for value in (counters.as_dict()[key] for counters in attempt_tokens) if value is not None]
        tokens[key] = sum(known) if known else None
    latest = attempt_tokens[-1].as_dict() if attempt_tokens else {}
    tokens["context_used"] = latest.get("context_used")
    tokens["context_window"] = capacity if capacity is not None else latest.get("context_window")
    if tokens["context_used"] is None and tokens["input"] is not None and tokens["output"] is not None:
        tokens["context_used"] = tokens["input"] + tokens["output"]
    return tokens


class TargetExecutor:
    def __init__(
        self, config: DaemonConfig, database: Database, drivers: DriverRegistry,
        *, ask_registry: Any = None,
        environment_resolver: Callable[[ProjectView, str], tuple[dict[str, str], str]] | None = None,
    ) -> None:
        self.config = config
        self.database = database
        self.drivers = drivers
        self.ask_registry = ask_registry
        self.environment_resolver = environment_resolver
        # Values each running job was launched with, held in memory only so the terminal
        # callback can redact them from telemetry after the configuration has rotated.
        self.run_secrets: dict[str, tuple[str, ...]] = {}
        self._target_semaphores: dict[str, asyncio.Semaphore] = {}
        self._target_active: dict[str, int] = {}
        self._target_users: dict[str, int] = {}
        # Jobs that resume the same backend session run one at a time.
        self._session_locks: dict[tuple[str, str, str, str], asyncio.Semaphore] = {}
        self._session_users: dict[tuple[str, str, str, str], int] = {}

    def refresh_configuration(self, config: DaemonConfig) -> None:
        """Adopt settings; occupied capacity drains before replacing its limit."""
        self.config = config
        self._target_semaphores = {
            key: semaphore for key, semaphore in self._target_semaphores.items()
            if self._target_users.get(key, 0)
        }
    async def execute(self, *, job_id: str, project: ProjectView, workflow: str, session: str, plan: ExecutionPlan, prompt: str, cwd: Path, cancel_event: CancelEvent, fresh: bool = False) -> TargetExecutionResult:
        attempt_tokens: list[TokenCounters] = []
        run_secrets = tuple(value for target in plan.targets for value in (*target.args, *target.env.values()))
        self.run_secrets[job_id] = run_secrets

        last = DriverResult("REQUEST_FATAL", "", "", "No admissible target", "circuit_open")
        if not plan.selection.targets:
            return TargetExecutionResult(last, "", outcome=self._outcome(last, None, None, circuit_open=True, attempt_tokens=attempt_tokens))
        if cancel_event.is_set():
            cancelled = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")
            return TargetExecutionResult(cancelled, "", outcome=self._outcome(cancelled, None, None, attempt_tokens=attempt_tokens))
        order = plan.selection.targets
        sticky = await run_sync(self.database.sticky_target, project.id, session, workflow)
        if sticky in order:
            order = (sticky, *(target_id for target_id in order if target_id != sticky))
        target, skipped_targets = await run_sync(self._select_target, order, plan, job_id)
        if target is None:
            return TargetExecutionResult(last, "", outcome=self._outcome(last, None, None, circuit_open=True, attempt_tokens=attempt_tokens))
        target_key = target_execution_key(target)
        bound_env: dict[str, str] = {}
        session_target_key = target_key
        scoped_session = session
        if target.id in plan.environment_targets:
            resolved = await self._resolve_environment(project, target, target_key, job_id, attempt_tokens)
            if isinstance(resolved, TargetExecutionResult):
                return resolved
            bound_env, opaque_revision = resolved
            self.run_secrets[job_id] = (*run_secrets, *bound_env.values())
            session_target_key = f"{target_key}:env:{opaque_revision}"
            scoped_session = f"{session}:env:{opaque_revision}"
        session_key = (project.id, scoped_session, workflow, session_target_key)
        session_lock = self._session_locks.setdefault(session_key, asyncio.Semaphore(1))
        self._session_users[session_key] = self._session_users.get(session_key, 0) + 1
        try:
            session_locked = await self._acquire_target(session_lock, cancel_event)
        except BaseException as exc:
            try:
                self._release_session(session_key, locked=False)
            finally:
                await self._release_probe(target_key, job_id)
            self._attach_outcome(exc, target, None, attempt_tokens=attempt_tokens)
            raise
        if not session_locked:
            try:
                self._release_session(session_key, locked=False)
            finally:
                await self._release_probe(target_key, job_id)
            cancelled = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")
            return TargetExecutionResult(cancelled, target.id, target_key, self._outcome(cancelled, target, None, attempt_tokens=attempt_tokens))
        try:
            session_id = await self._prepare_session(
                project, scoped_session, workflow, session_target_key, fresh
            )
        except BaseException as exc:
            try:
                self._release_session(session_key, locked=True)
            finally:
                await self._release_probe(target_key, job_id)
            self._attach_outcome(exc, target, None, attempt_tokens=attempt_tokens)
            raise
        semaphore = self._target_semaphores.setdefault(target.id, asyncio.Semaphore(target.max_concurrency))
        self._target_users[target.id] = self._target_users.get(target.id, 0) + 1
        self._target_active.setdefault(target.id, 0)
        try:
            acquired = await self._acquire_target(semaphore, cancel_event)
        except BaseException as exc:
            try:
                self._release_capacity(target.id)
                self._release_session(session_key, locked=True)
            finally:
                await self._release_probe(target_key, job_id)
            self._attach_outcome(exc, target, None, attempt_tokens=attempt_tokens)
            raise
        if not acquired:
            try:
                self._release_capacity(target.id)
                self._release_session(session_key, locked=True)
            finally:
                await self._release_probe(target_key, job_id)
            cancelled = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")
            return TargetExecutionResult(cancelled, target.id, target_key, self._outcome(cancelled, target, None, attempt_tokens=attempt_tokens))

        self._target_active[target.id] += 1
        try:
            return await self._execute_attempt(_ExecutionContext(
                job_id=job_id, project=project, workflow=workflow,
                session=scoped_session, plan=plan, prompt=prompt, cwd=cwd,
                cancel_event=cancel_event, fresh=fresh,
                target=target, target_key=target_key, session_target_key=session_target_key, session_id=session_id,
                attempt_tokens=attempt_tokens,
                skipped_targets=skipped_targets,
                bound_env=bound_env,
            ))
        finally:
            try:
                self._target_active[target.id] -= 1
            finally:
                try:
                    semaphore.release()
                finally:
                    try:
                        self._release_capacity(target.id)
                        self._release_session(session_key, locked=True)
                    finally:
                        await self._release_probe(target_key, job_id)

    @classmethod
    def _configuration_failure(cls, target: TargetConfig, target_key: str, message: str,
                               attempt_tokens: list[TokenCounters] | None = None) -> TargetExecutionResult:
        result = DriverResult("REQUEST_FATAL", "", "", message, "configuration_error")
        return TargetExecutionResult(result, target.id, target_key,
                                     cls._outcome(result, target, None, attempt_tokens=attempt_tokens))

    async def _release_probe(self, target_key: str, job_id: str) -> None:
        try:
            await run_sync(self.database.release_target_probe, target_key, job_id)
        except Exception:
            log.warning("Failed to release target probe", exc_info=True)

    async def _resolve_environment(
        self, project: ProjectView, target: TargetConfig, target_key: str, job_id: str, attempt_tokens: list[TokenCounters],
    ) -> tuple[dict[str, str], str] | TargetExecutionResult:
        """Return the bound env and its opaque revision, or a configuration failure after releasing the probe."""
        if self.environment_resolver is None:
            await self._release_probe(target_key, job_id)
            return self._configuration_failure(target, target_key, "Target environment configuration is unavailable", attempt_tokens)
        try:
            bound_env, revision_context = await run_sync(self.environment_resolver, project, target.id)
            return bound_env, hashlib.sha256((project.id + revision_context).encode()).hexdigest()[:20]
        except asyncio.CancelledError:
            await self._release_probe(target_key, job_id)
            raise
        except Exception:
            await self._release_probe(target_key, job_id)
            return self._configuration_failure(target, target_key, "Target environment configuration is invalid", attempt_tokens)

    @staticmethod
    def _matches_retry_policy(policy: RetryPolicy, result: DriverResult) -> bool:
        if not policy.codes and not policy.patterns:
            return True
        if result.error_code and result.error_code in policy.codes:
            return True
        if result.error and policy.patterns:
            err_lower = result.error.lower()
            if any(pat.lower() in err_lower for pat in policy.patterns):
                return True
        return False

    @classmethod
    def _can_retry_attempt(
        cls,
        *,
        policy: RetryPolicy,
        policy_retries_done: int,
        result: DriverResult,
        replay_blocked: bool,
        supports_streaming: bool,
        cancel_event: CancelEvent,
    ) -> bool:
        if cancel_event.is_set():
            return False
        if policy_retries_done >= policy.attempts:
            return False
        if result.outcome != "RETRYABLE":
            return False
        if result.error_code == "context_overflow":
            return False
        if replay_blocked or not supports_streaming:
            return False
        return cls._matches_retry_policy(policy, result)

    async def _prepare_session(
        self, project: ProjectView, session: str, workflow: str,
        target_key: str, fresh: bool,
    ) -> str:
        if fresh:
            return ""
        return await run_sync(self.database.session, project.id, session, workflow, target_key)

    async def _start_attempt(
        self, job_id: str, target: TargetConfig, plan: ExecutionPlan,
        workflow: str, session_id: str, attempt_number: int, cancel_event: CancelEvent,
    ) -> tuple[float, bool]:
        await run_sync(self.database.record_job_target, job_id, target.id)
        started_at = time.monotonic()
        log.info("Target attempt started", extra={"event": "target.attempt_started", "job_id": job_id, "target_id": target.id, "profile": plan.profile, "workflow": workflow, "attempt": attempt_number, "timeout_s": plan.selection.timeout_s, "resumed_session": bool(session_id)})
        supports_streaming = await self.drivers.supports_structured_streaming(target, cancel_event)
        return started_at, supports_streaming

    async def _execute_attempt(self, context: _ExecutionContext) -> TargetExecutionResult:
        job_id = context.job_id
        cancel_event = context.cancel_event
        target = context.target
        attempt_tokens = context.attempt_tokens

        policy_retries_done = 0
        attempt_number = 0
        overall_started_at = time.monotonic()

        while True:
            attempt_number += 1
            attempt = _TargetAttempt()
            if cancel_event.is_set():
                attempt.result = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")
                break

            started_at, supports_streaming = await self._begin_attempt(context, attempt_number, overall_started_at)

            driver_exc: BaseException | None = None
            try:
                await self._run_attempt(context, attempt, attempt_number, started_at, supports_streaming)
            except BaseException as exc:
                driver_exc = exc
            finally:
                revoke_exc: BaseException | None = None
                try:
                    self._revoke_ask_token(job_id)
                except BaseException as exc:
                    revoke_exc = exc

                self._apply_cancellation(attempt, cancel_event, driver_exc)

                rec_exc: BaseException | None = None
                try:
                    await self._record_attempt_finished(
                        job_id, attempt_number, target, supports_streaming, attempt.result, driver_exc, cancel_event,
                    )
                except BaseException as exc:
                    rec_exc = exc

                self._log_attempt_finished(context, attempt, attempt_number, started_at, driver_exc)

                primary_exc = driver_exc or rec_exc or revoke_exc
                if primary_exc is not None:
                    duration_ms = int((time.monotonic() - overall_started_at) * 1000)
                    self._attach_outcome(primary_exc, target, duration_ms, attempt_tokens=attempt_tokens)
                    raise primary_exc
            if not self._should_retry(context, attempt, policy_retries_done, supports_streaming):
                break
            policy_retries_done += 1

        total_duration_ms = int((time.monotonic() - overall_started_at) * 1000)
        return await self._finish_execution(context, attempt, total_duration_ms, attempt_number)

    async def _begin_attempt(
        self, context: _ExecutionContext, attempt_number: int, overall_started_at: float,
    ) -> tuple[float, bool]:
        try:
            return await self._start_attempt(
                context.job_id, context.target, context.plan, context.workflow, context.session_id, attempt_number,
                context.cancel_event,
            )
        except BaseException as exc:
            duration_ms = int((time.monotonic() - overall_started_at) * 1000)
            self._attach_outcome(exc, context.target, duration_ms, attempt_tokens=context.attempt_tokens)
            raise

    def _issue_ask_env(self, job_id: str, plan: ExecutionPlan, started_at: float) -> dict[str, str] | None:
        if self.ask_registry is None:
            return None
        token = self.ask_registry.issue_token(
            job_id,
            workflow_timeout_s=plan.selection.timeout_s,
            started_at=started_at,
        )
        ask_url = f"http://{self.config.host}:{self.config.port}/ask"
        return {
            "REFRACT_ASK_URL": ask_url,
            "REFRACT_ASK_TOKEN": token,
            "REFRACT_ASK_TIMEOUT_S": str(self.config.ask_timeout_s),
        }

    async def _run_attempt(
        self, context: _ExecutionContext, attempt: _TargetAttempt, attempt_number: int,
        started_at: float, supports_streaming: bool,
    ) -> None:
        job_id = context.job_id
        ask_env = self._issue_ask_env(job_id, context.plan, started_at)
        if context.cancel_event.is_set():
            attempt.result = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")
            return
        inv_result, has_tool_activity = await self._run_target_invocation(
            job_id=job_id,
            attempt=attempt_number,
            attempt_tokens=context.attempt_tokens,
            target=context.target,
            prompt=context.prompt,
            session_id=context.session_id,
            cwd=context.cwd,
            timeout_s=context.plan.selection.timeout_s,
            cancel_event=context.cancel_event,
            supports_streaming=supports_streaming,
            env={**context.bound_env, **(ask_env or {}), "REFRACT_JOB_ID": job_id},
        )
        attempt.result = inv_result
        attempt.replay_blocked = has_tool_activity and inv_result.outcome != "SUCCESS"

    def _revoke_ask_token(self, job_id: str) -> None:
        if self.ask_registry is not None:
            self.ask_registry.revoke_token(job_id)

    @staticmethod
    def _apply_cancellation(
        attempt: _TargetAttempt, cancel_event: CancelEvent, driver_exc: BaseException | None
    ) -> None:
        if cancel_event.is_set() or isinstance(driver_exc, asyncio.CancelledError):
            attempt.result = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")

    @staticmethod
    def _log_attempt_finished(
        context: _ExecutionContext, attempt: _TargetAttempt, attempt_number: int,
        started_at: float, driver_exc: BaseException | None,
    ) -> None:
        event_result = attempt.result
        if driver_exc is not None and event_result is None:
            event_result = DriverResult("REQUEST_FATAL", "", "", str(driver_exc), "execution_error")
        if event_result is not None:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            log.info(
                "Target attempt finished",
                extra={
                    "event": "target.attempt_finished",
                    "job_id": context.job_id,
                    "target_id": context.target.id,
                    "workflow": context.workflow,
                    "attempt": attempt_number,
                    "outcome": event_result.outcome,
                    "error_code": event_result.error_code,
                    "duration_ms": duration_ms,
                },
            )

    def _should_retry(
        self, context: _ExecutionContext, attempt: _TargetAttempt, policy_retries_done: int, supports_streaming: bool,
    ) -> bool:
        if attempt.result is None:
            attempt.result = DriverResult("REQUEST_FATAL", "", "", "execution_failed", "execution_error")
        if attempt.result.outcome == "SUCCESS":
            return False
        return self._can_retry_attempt(
            policy=context.target.retry,
            policy_retries_done=policy_retries_done,
            result=attempt.result,
            replay_blocked=attempt.replay_blocked,
            supports_streaming=supports_streaming,
            cancel_event=context.cancel_event,
        )

    async def _finish_execution(
        self, context: _ExecutionContext, attempt: _TargetAttempt, total_duration_ms: int,
        attempt_number: int,
    ) -> TargetExecutionResult:
        target = context.target
        last = attempt.result or DriverResult("REQUEST_FATAL", "", "", "execution_failed", "execution_error")
        try:
            if last.outcome == "SUCCESS":
                await run_sync(
                    self.database.record_target_success, context.target_key, self.config.breaker_base_cooldown_s
                )
                if not context.fresh:
                    await run_sync(self.database.store_session,
                        project_id=context.project.id,
                        session=context.session,
                        workflow=context.workflow,
                        target_key=context.session_target_key,
                        backend_session_id=last.session_id,
                    )
            else:
                await self._update_target_health(last, context.target_key, context.job_id, attempt.replay_blocked)
        except BaseException as exc:
            self._attach_outcome(exc, target, total_duration_ms, attempt_tokens=context.attempt_tokens)
            raise

        return TargetExecutionResult(
            last,
            target.id,
            context.target_key,
            self._outcome(
                last,
                target,
                total_duration_ms,
                replay_blocked=attempt.replay_blocked,
                attempt_tokens=context.attempt_tokens,
                attempts=attempt_number,
                skipped_targets=context.skipped_targets,
            ),
            context.session_target_key,
            context.session,
        )

    async def _record_attempt_finished(
        self, job_id: str, attempt: int, target: TargetConfig, supports_streaming: bool,
        result: DriverResult | None, driver_exc: BaseException | None, cancel_event: CancelEvent,
    ) -> None:
        if not supports_streaming:
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
        await self._record_stream_event(job_id, attempt, target, {
            "kind": "attempt.finished",
            "data": {
                "status": status,
                "outcome": result.outcome,
                "error_code": result.error_code,
            },
        })

    async def _record_stream_event(self, job_id: str, attempt: int, target: TargetConfig, event: dict[str, Any]) -> None:
        try:
            await run_sync(self.database.append_stream, job_id, [{
                "attempt": attempt,
                "target_id": target.id,
                "backend": target.backend,
                "kind": str(event.get("kind", "")),
                "entity_id": str(event.get("entity_id", "")),
                "parent_entity_id": str(event.get("parent_entity_id", "")),
                "data": dict(event.get("data", {})),
            }])
        except Exception as exc:
            log.exception(
                "Stream persistence failed",
                extra={"event": "stream.persistence_failed", "job_id": job_id, "error": str(exc)},
            )

    async def _update_target_health(
        self, result: DriverResult, target_key: str, job_id: str, replay_blocked: bool,
    ) -> None:
        health = await run_sync(self.database.target_health, target_key)
        held_probe = health.get("probe_job_id") == job_id
        if result.outcome in {"CANCELLED", "REQUEST_FATAL"}:
            return
        if result.error_code == "context_overflow" or replay_blocked:
            return
        elif result.outcome == "TARGET_FATAL":
            await run_sync(self._record_failure, target_key, immediate=True, failed_probe=False)
        elif result.outcome == "RETRYABLE":
            await run_sync(self._record_failure, target_key, failed_probe=held_probe)
        elif held_probe:
            return

    @classmethod
    def _attach_outcome(
        cls,
        exc: BaseException,
        target: TargetConfig | None,
        duration_ms: int | None,
        *,
        attempt_tokens: list[TokenCounters] | None = None,
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
            setattr(exc, "_refract_outcome", cls._outcome(result, target, duration_ms, attempt_tokens=attempt_tokens))
        except (AttributeError, TypeError):
            pass

    @staticmethod
    def _failure_kind(result: DriverResult, replay_blocked: bool, circuit_open: bool) -> str | None:
        if result.outcome == "SUCCESS":
            return None
        if result.outcome == "CANCELLED":
            return "cancelled"
        if circuit_open or result.error_code == "circuit_open":
            return "circuit_open"
        if replay_blocked:
            return "replay_blocked"
        if result.error_code == "context_overflow":
            return "context_overflow"
        if result.error_code == "configuration_error":
            return "request_fatal"
        if result.outcome == "TARGET_FATAL":
            return "target_fatal"
        if result.outcome == "RETRYABLE":
            return "transient"
        return "request_fatal"

    @staticmethod
    def _outcome(
        result: DriverResult,
        target: TargetConfig | None,
        duration_ms: int | None,
        *,
        replay_blocked: bool = False,
        circuit_open: bool = False,
        attempt_tokens: list[TokenCounters] | None = None,
        attempts: int | None = None,
        skipped_targets: int | None = None,
    ) -> dict[str, Any]:
        failure_kind = TargetExecutor._failure_kind(result, replay_blocked, circuit_open)
        model_name = result.model
        if model_name is None and target is not None:
            model_name = target.model or None
        return {
            "failure_kind": failure_kind,
            "model": model_name or "",
            "duration_ms": duration_ms,
            "tokens": _job_tokens(attempt_tokens or [], target),
            "attempts": attempts,
            "skipped_targets": skipped_targets,
        }

    async def _run_target_invocation(
        self,
        *,
        job_id: str,
        attempt: int,
        attempt_tokens: list[TokenCounters],
        target: TargetConfig,
        prompt: str,
        session_id: str,
        cwd: Path,
        timeout_s: float,
        cancel_event: threading.Event,
        supports_streaming: bool,
        env: dict[str, str] | None = None,
    ) -> tuple[DriverResult, bool]:
        attempt_tokens.append(TokenCounters())
        consumed_tool_activity = False
        streamed_consumption = False

        async def consume(event: dict[str, Any]) -> None:
            """Apply one stream event to telemetry and the stream log."""
            nonlocal consumed_tool_activity, streamed_consumption
            consumed_tool_activity = consumed_tool_activity or self._is_event_kind(event, "tool.started")
            if self._is_event_kind(event, "telemetry.updated"):
                streamed_consumption = self._apply_telemetry(attempt_tokens, event) or streamed_consumption
            if supports_streaming:
                await self._record_stream_event(job_id, attempt, target, event)

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
                    on_event=consume if supports_streaming else None,
                    env=env,
                    on_spawn=lambda pid: self._record_process_group(job_id, pid),
                )
        except BaseException as exc:
            driver_exc = exc
            raise
        finally:
            if cancel_event.is_set() or isinstance(driver_exc, asyncio.CancelledError):
                attempt_result = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")
            # Returned counts apply only when stream events did not already report consumption.
            if attempt_result is not None and not streamed_consumption:
                self._merge_returned_tokens(attempt_tokens, attempt_result)

        if attempt_result is None:
            attempt_result = self._no_result(driver_exc)

        return attempt_result, consumed_tool_activity

    @staticmethod
    def _is_event_kind(event: Any, kind: str) -> bool:
        return isinstance(event, dict) and event.get("kind") == kind

    @staticmethod
    def _apply_telemetry(attempt_tokens: list[TokenCounters], event: dict[str, Any]) -> bool:
        """Record one telemetry event; return whether it reported consumption."""
        try:
            data = event.get("data")
            if not isinstance(data, dict):
                return False
            attempt_tokens[-1] = _counters_from(data)
            return any(key in data for key in CONSUMPTION_KEYS)
        except Exception:
            log.warning("Telemetry update failed", exc_info=True)
            return False

    async def _record_process_group(self, job_id: str, pgid: int) -> None:
        try:
            await run_sync(self.database.set_pgid, job_id, pgid)
        except Exception:
            log.warning("Worker process group not recorded", exc_info=True)

    @staticmethod
    def _merge_returned_tokens(attempt_tokens: list[TokenCounters], attempt_result: DriverResult) -> None:
        try:
            current = attempt_tokens[-1].as_dict()
            reported = _counters_from(attempt_result.tokens or {}).as_dict()
            attempt_tokens[-1] = _counters_from({**current, **{k: v for k, v in reported.items() if v is not None}})
        except Exception:
            log.warning("Ignoring malformed backend telemetry", exc_info=True)

    @staticmethod
    def _no_result(driver_exc: BaseException | None) -> DriverResult:
        err_msg = str(driver_exc) if driver_exc else "execution_failed"
        return DriverResult("REQUEST_FATAL", "", "", err_msg, "execution_error")

    def _release_capacity(self, target_id: str) -> None:
        self._target_users[target_id] -= 1
        if not self._target_users[target_id]:
            self._target_users.pop(target_id)
            self._target_semaphores.pop(target_id, None)
            self._target_active.pop(target_id, None)

    def _release_session(self, key: tuple[str, str, str, str], *, locked: bool) -> None:
        if locked:
            self._session_locks[key].release()
        self._session_users[key] -= 1
        if not self._session_users[key]:
            self._session_users.pop(key)
            self._session_locks.pop(key, None)

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

    def _select_target(self, target_ids: tuple[str, ...], plan: ExecutionPlan, job_id: str = "") -> tuple[TargetConfig | None, int]:
        now = datetime.now(timezone.utc)
        healthy: list[TargetConfig] = []
        claimed_probes: list[str] = []
        rejected = 0
        for target_id in target_ids:
            target = plan.target(target_id)
            target_key = target_execution_key(target)
            if not self._admit_target(target, target_key, now, job_id, claimed_probes):
                rejected += 1
                continue
            healthy.append(target)
            if self._target_active.get(target.id, 0) < target.max_concurrency:
                self._release_unselected_probes(claimed_probes, target_key, job_id)
                return target, rejected
        if not healthy:
            return None, rejected
        selected = healthy[0]
        self._release_unselected_probes(claimed_probes, target_execution_key(selected), job_id)
        return selected, rejected

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
JobTerminalCallback = Callable[..., Any]


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
        self.on_terminal = on_terminal or (lambda _job_id, _state, **_kwargs: None)
        self._commits: dict[str, bool] = {}

    async def _notify(self, job_id: str) -> None:
        try:
            await self.notifier(job_id)
        except Exception:
            log.warning(
                "Job resource notification failed",
                extra={"event": "job.resource_notification_failed", "job_id": job_id},
                exc_info=True,
            )

    async def _commit(self, job_id: str, call: Callable[..., bool], /, *args: Any, **kwargs: Any) -> bool:
        """Run a terminal commit and record its transition result in the worker thread, so a cancel that joins the thread keeps it."""
        def work() -> bool:
            changed = call(*args, **kwargs)
            self._commits[job_id] = changed
            return changed
        return await run_sync(work)

    async def _finish_reporting(self, job_id: str, state: str, *, notify: bool = True, **fields: Any) -> None:
        """Commit a terminal state and report it; a cancel during the commit still reports this runner's transition once."""
        try:
            changed = await self._commit(job_id, self.database.finish_job, job_id, state, **fields)
        except asyncio.CancelledError:
            await self._terminal(job_id, state, self._commits.pop(job_id, False))
            raise
        self._commits.pop(job_id, None)
        await self._terminal(job_id, state, changed)
        if notify:
            await self._notify(job_id)

    async def _terminal(self, job_id: str, state: str, changed: bool) -> None:
        """Report a terminal state; ``changed`` is true only for the call that committed the transition."""
        try:
            result = self.on_terminal(job_id, state, changed=changed)
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
        outcome: dict[str, Any] | None = None
        try:
            await run_sync(self.database.start_job, job_id)
            await self._notify(job_id)
            plan = parse_execution_plan(json.loads(record["execution_plan_json"]))
            execution = await self.targets.execute(
                job_id=job_id,
                project=project,
                workflow=record["workflow"],
                session=record["session"],
                plan=plan,
                prompt=record["prompt"],
                cwd=root,
                cancel_event=cancel_event,
                fresh=bool(record.get("fresh", 0)),
            )
            outcome = execution.outcome
            if execution.result.outcome != "SUCCESS" or cancel_event.is_set():
                final_state = self._failure_state(cancel_event)
                changed = await self._commit(job_id, self.database.finish_job, job_id, final_state, error=execution.result.error or execution.result.outcome, **outcome)
                committed_state = final_state
                await self._terminal(job_id, final_state, changed)
                await self._notify(job_id)
                return
            changed = await self._finish_success(job_id, project, record, execution)
            committed_state = "succeeded"
            await self._terminal(job_id, committed_state, changed)
            await self._notify(job_id)
        except asyncio.CancelledError as exc:
            await self._finish_cancelled_job(job_id, exc, committed_state)
            raise
        except Exception as exc:
            await self._finish_failed_job(job_id, exc, final_state, committed_state, outcome)
        finally:
            # Release the launch values however the run exits; the terminal callback has already taken them on the normal path.
            self.targets.run_secrets.pop(job_id, None)
            self._commits.pop(job_id, None)
            completed = await run_sync(self.database.job, job_id)
            log.info("Job finished", extra={"event": "job.finished", "job_id": job_id, "project_id": project_id, "state": completed.state if completed else "unknown", "duration_ms": round((time.monotonic() - started_at) * 1000, 2)})

    async def _prepare_job(self, job_id: str, project_id: str, cancel_event: CancelEvent) -> ProjectView | None:
        if self.is_closing():
            # A reserved-but-undispatched queue item remains durable for restart.
            return None
        if cancel_event.is_set():
            state = "interrupted" if self.is_closing() else "cancelled"
            await self._finish_reporting(job_id, state, error="cancelled before execution")
            return None
        project = await run_sync(self.database.project, project_id)
        if project is None:
            await self._finish_reporting(job_id, "failed", error="Project was removed")
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
    ) -> bool:
        if bool(record.get("fresh", 0)):
            return await self._commit(job_id, self.database.finish_fresh_job_success,
                job_id=job_id,
                project_id=project.id,
                session=execution.scoped_session or record["session"],
                workflow=record["workflow"],
                target=execution.target_id,
                target_key=execution.session_key or execution.target_key,
                backend_session_id=execution.result.session_id,
                text=execution.result.text,
                **execution.outcome,
            )
        return await self._commit(job_id, self.database.finish_job, job_id, "succeeded", text=execution.result.text, target=execution.target_id, **execution.outcome)

    async def _finish_cancelled_job(
        self, job_id: str, exc: asyncio.CancelledError, committed_state: str | None,
    ) -> None:
        completed = await run_sync(self.database.job, job_id)
        if completed is not None and completed.state in TERMINAL_STATES:
            # A normal-path commit has already reported; only a commit that the cancel interrupted is still unreported.
            changed = committed_state is None and self._commits.pop(job_id, False)
            committed_state = completed.state
            await self._terminal(job_id, committed_state, changed)
        if committed_state is None:
            final_state = "interrupted" if self.is_closing() else "cancelled"
            outcome = (
                getattr(exc, "_refract_outcome", None)
                or self.targets._outcome(
                    DriverResult("CANCELLED", "", "", "cancelled", "cancelled"), None, None
                )
            )
            await self._finish_reporting(job_id, final_state, notify=False, error="execution task cancelled", **outcome)

    async def _finish_failed_job(
        self, job_id: str, exc: Exception, final_state: str,
        committed_state: str | None, outcome: dict[str, Any] | None,
    ) -> None:
        if committed_state is not None:
            log.warning(
                "Post-terminal job operation failed",
                extra={"event": "job.post_terminal_failed", "job_id": job_id, "state": committed_state},
                exc_info=True,
            )
            return
        outcome = (
            getattr(exc, "_refract_outcome", None)
            or outcome
            or self.targets._outcome(
                DriverResult("REQUEST_FATAL", "", "", str(exc), "execution_error"), None, None
            )
        )
        log.exception(
            "Unexpected job failure",
            extra={"event": "job.exception", "job_id": job_id},
        )
        await self._finish_reporting(job_id, final_state, error=str(exc), **outcome)


__all__ = ["JobNotifier", "JobRunner", "TargetExecutor", "TargetExecutionResult"]
