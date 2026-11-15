"""The attempt loop: each attempt holds its target resources in its own `AsyncExitStack`.

`execute` walks targets in order. On one target, `_run_target` runs attempts until the first matching row of the
DESIGN.md attempt table (`replay.next_step`) says to stop, retry, start a fresh session, or fall back to the next
target. An attempt's semaphore and probe are released before the next attempt starts. The session lock is not
taken here: `JobRunner` holds it for the whole job, across every attempt and fallback.
The last attempt stays `running`; the job's terminal commit closes it with the job state.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from refract.config import DaemonConfig, TargetConfig
from refract.store.database import Database
from refract.logging_setup import get_logger
from refract.models import ProjectView
from refract.runner.drivers import DriverRegistry, DriverResult
from refract.runner.planning import ExecutionPlan, target_execution_key
from refract.runner.replay import Attempt, next_step, replay_safe
from refract.runner.invocation import Invocation
from refract.runner.targets import TargetPool
from refract.runner.tokens import TokenCounters, attempt_tokens as tokens_of
from refract.scheduling.cancel import CancelEvent
from refract.store.pool import run_db, run_on, run_sync

log = get_logger("execution")
_CANCELLED = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")


@dataclass(slots=True, frozen=True)
class TargetExecutionResult:
    """The last attempt of a job: its result and outcome, and the next target when the job ends unrecovered."""

    result: DriverResult
    target_id: str
    target_key: str = ""
    outcome: dict[str, Any] = field(default_factory=dict)
    session_key: str = ""
    scoped_session: str = ""
    next_target: str | None = None


@dataclass(slots=True)
class _Job:
    """State one `execute` call carries across its attempts."""

    id: str
    project: ProjectView
    workflow: str
    session: str
    plan: ExecutionPlan
    prompt: str
    cwd: Path
    cancel_event: CancelEvent
    fresh: bool
    order: tuple[str, ...]
    started_at: float
    fresh_used: bool = False
    attempts: int = 0
    tried: set[str] = field(default_factory=set)
    last: TargetExecutionResult | None = None


@dataclass(slots=True, frozen=True)
class _Segment:
    """One target the job runs on: its keys and bound environment."""

    target: TargetConfig
    target_key: str
    session_target_key: str
    scoped_session: str
    bound_env: dict[str, str]


@dataclass(slots=True)
class _Finished:
    result: DriverResult
    counters: TokenCounters | None
    duration_ms: int
    attempt_id: int | None
    streams: bool
    tool_started: bool
    replay_safe: bool
    held_probe: bool


class TargetExecutor(Invocation, TargetPool):
    def __init__(
        self, config: DaemonConfig, database: Database, drivers: DriverRegistry,
        *, ask_registry: Any = None,
        environment_resolver: Callable[[ProjectView, str], tuple[dict[str, str], str]] | None = None,
    ) -> None:
        super().__init__(config, database, drivers)
        self.ask_registry = ask_registry
        self.environment_resolver = environment_resolver

    async def execute(
        self, *, job_id: str, project: ProjectView, workflow: str, session: str, plan: ExecutionPlan, prompt: str,
        cwd: Path, cancel_event: CancelEvent, fresh: bool = False,
    ) -> TargetExecutionResult:
        if not plan.selection.targets:
            return self._unavailable()
        if cancel_event.is_set():
            return TargetExecutionResult(_CANCELLED, "", outcome=self._outcome(_CANCELLED, None, None))
        order = plan.selection.targets
        sticky = await run_db(self.database.sticky_target, project.id, session, workflow)
        if sticky in order:
            order = (sticky, *(target_id for target_id in order if target_id != sticky))
        job = _Job(job_id, project, workflow, session, plan, prompt, cwd, cancel_event, fresh, order,
                   time.monotonic(), fresh_used=fresh)
        while True:
            remaining = tuple(target_id for target_id in order if target_id not in job.tried)
            target, _ = await run_on(self.database.executor, self._select_target, remaining, plan, job_id)
            if target is None:
                return job.last or self._unavailable()
            job.tried.add(target.id)
            finished = await self._run_target(job, target)
            if finished is not None:
                return finished

    def _unavailable(self) -> TargetExecutionResult:
        result = DriverResult("REQUEST_FATAL", "", "", "No admissible target", "circuit_open")
        return TargetExecutionResult(result, "", outcome=self._outcome(result, None, None, circuit_open=True))

    @classmethod
    def _configuration_failure(
        cls, target: TargetConfig, target_key: str, message: str, attempt_tokens: list[TokenCounters] | None = None,
    ) -> TargetExecutionResult:
        result = DriverResult("REQUEST_FATAL", "", "", message, "configuration_error")
        return TargetExecutionResult(result, target.id, target_key,
                                     cls._outcome(result, target, None, attempt_tokens=attempt_tokens))

    async def _resolve_environment(
        self, project: ProjectView, target: TargetConfig, target_key: str, job_id: str,
    ) -> tuple[dict[str, str], str] | TargetExecutionResult:
        """Return the bound env and its opaque revision, or a configuration failure after releasing the probe."""
        if self.environment_resolver is None:
            await self._release_probe(target_key, job_id)
            return self._configuration_failure(target, target_key, "Target environment configuration is unavailable")
        try:
            bound_env, revision_context = await run_sync(self.environment_resolver, project, target.id)
            return bound_env, hashlib.sha256((project.id + revision_context).encode()).hexdigest()[:20]
        except asyncio.CancelledError:
            await self._release_probe(target_key, job_id)
            raise
        except Exception:
            await self._release_probe(target_key, job_id)
            return self._configuration_failure(target, target_key, "Target environment configuration is invalid")

    async def _run_target(self, job: _Job, target: TargetConfig) -> TargetExecutionResult | None:
        """Run attempts on one target; None means the job falls back to the next target."""
        target_key = target_execution_key(target)
        try:
            return await self._attempts_on(job, target, target_key)
        except BaseException as exc:
            self._attach_outcome(exc, target, int((time.monotonic() - job.started_at) * 1000))
            raise

    async def _attempts_on(self, job: _Job, target: TargetConfig, target_key: str) -> TargetExecutionResult | None:
        bound_env: dict[str, str] = {}
        session_target_key, scoped_session = target_key, job.session
        if target.id in job.plan.environment_targets:
            resolved = await self._resolve_environment(job.project, target, target_key, job.id)
            if isinstance(resolved, TargetExecutionResult):
                return resolved
            bound_env, revision = resolved
            session_target_key = f"{target_key}:env:{revision}"
            scoped_session = f"{job.session}:env:{revision}"
        health = await run_db(self.database.target_health, target_key)
        segment = _Segment(target, target_key, session_target_key, scoped_session, bound_env)
        held_probe = health.get("probe_job_id") == job.id
        probe_open = held_probe

        async def release_probe() -> None:
            nonlocal probe_open
            if probe_open:
                probe_open = False
                await self._release_probe(target_key, job.id)

        reason: str = "fallback" if len(job.tried) > 1 else "initial"
        retries_done = 0
        session_id = ""
        async with AsyncExitStack() as target_scope:
            target_scope.push_async_callback(release_probe)
            session_id = await self._prepare_session(
                job.project, scoped_session, job.workflow, session_target_key, job.fresh,
            )
            while True:
                async with AsyncExitStack() as attempt_scope:
                    attempt_scope.push_async_callback(release_probe)
                    if not await self._enter_capacity(attempt_scope, target, job.cancel_event):
                        return self._cancelled(target, target_key)
                    if reason == "fresh_session":
                        session_id = ""
                    finished = await self._attempt(job, segment, session_id, reason, held_probe)
                    result = finished.result
                    attempt = Attempt(result.outcome, self._failure_kind(result), result.error_code, result.error,
                                      finished.replay_safe)
                    remaining = tuple(target_id for target_id in job.order if target_id not in job.tried)
                    eligible = await run_on(self.database.executor, self.eligible_targets, remaining, job.plan)
                    step = next_step(
                        attempt, policy=target.retry, retries_done=retries_done, fresh_used=job.fresh_used,
                        target_remains=bool(eligible), cancelled=job.cancel_event.is_set(),
                    )
                    last = self._last_result(job, segment, finished, None if step else (eligible or [None])[0])
                    job.last = last
                    if step is None or step == "fallback":
                        await self._record_health(job, segment, finished)
                if step in {"retry", "fresh_session"}:
                    # Each attempt owns the probe it runs under: take the target's admission again.
                    admitted, held_probe = await run_on(
                        self.database.executor, self.readmit_target, target, job.plan, job.id,
                    )
                    probe_open = held_probe
                    if not admitted:
                        step = next_step(
                            attempt, policy=target.retry, retries_done=target.retry.attempts, fresh_used=True,
                            target_remains=bool(eligible), cancelled=job.cancel_event.is_set(),
                        )
                        last = self._last_result(job, segment, finished, None if step else (eligible or [None])[0])
                        job.last = last
                        await self._record_health(job, segment, finished)
                if step is not None and finished.attempt_id is not None:
                    await run_db(
                        self.database.finish_attempt, finished.attempt_id, "failed",
                        failure_kind=attempt.failure_kind, replay_safe=finished.replay_safe,
                        model=last.outcome["model"], duration_ms=finished.duration_ms,
                        tokens=last.outcome["tokens"],
                    )
                if step is None:
                    return last
                if step == "fallback":
                    return None
                retries_done += step == "retry"
                job.fresh_used = job.fresh_used or step == "fresh_session"
                reason = step

    async def _prepare_session(
        self, project: ProjectView, session: str, workflow: str, target_key: str, fresh: bool,
    ) -> str:
        if fresh:
            return ""
        return await run_db(self.database.session, project.id, session, workflow, target_key)

    def _last_result(
        self, job: _Job, segment: _Segment, finished: _Finished, next_target: str | None,
    ) -> TargetExecutionResult:
        counters = [finished.counters] if finished.counters is not None else []
        outcome = self._outcome(
            finished.result, segment.target, finished.duration_ms, replay_safe=finished.replay_safe,
            attempt_tokens=counters,
        )
        return TargetExecutionResult(
            finished.result, segment.target.id, segment.target_key, outcome, segment.session_target_key,
            segment.scoped_session, next_target,
        )

    async def _record_health(self, job: _Job, segment: _Segment, finished: _Finished) -> None:
        result = finished.result
        if result.outcome == "SUCCESS":
            await run_db(
                self.database.record_target_success, segment.target_key, self.config.breaker_base_cooldown_s, job.id,
            )
            if not job.fresh:
                await run_db(
                    self.database.store_session, project_id=job.project.id, session=segment.scoped_session,
                    workflow=job.workflow, target_key=segment.session_target_key, backend_session_id=result.session_id,
                )
        elif not finished.tool_started:
            # A failure after a tool ran says nothing about the target's health.
            await self._update_target_health(result, segment.target_key, finished.held_probe, job.id)

    def _cancelled(self, target: TargetConfig, target_key: str) -> TargetExecutionResult:
        return TargetExecutionResult(_CANCELLED, target.id, target_key, self._outcome(_CANCELLED, target, None))

    async def _enter_capacity(self, stack: AsyncExitStack, target: TargetConfig, cancel_event: CancelEvent) -> bool:
        """Take one slot of the target's semaphore for the attempt; `stack` gives it back."""
        semaphore = self._target_semaphores.setdefault(target.id, asyncio.Semaphore(target.max_concurrency))
        self._target_users[target.id] = self._target_users.get(target.id, 0) + 1
        self._target_active.setdefault(target.id, 0)
        stack.callback(self._release_capacity, target.id)
        if not await self._acquire_target(semaphore, cancel_event):
            return False
        stack.callback(semaphore.release)
        self._target_active[target.id] += 1
        stack.callback(self._decrement_active, target.id)
        return True

    def _decrement_active(self, target_id: str) -> None:
        if target_id in self._target_active:
            self._target_active[target_id] -= 1

    async def _start_attempt(
        self, job_id: str, target: TargetConfig, plan: ExecutionPlan, workflow: str, session_id: str,
        attempt_number: int, cancel_event: CancelEvent, reason: str = "initial",
    ) -> tuple[int | None, float, bool]:
        attempt_id = await run_db(self.database.begin_attempt, job_id, target.id, reason)
        started_at = time.monotonic()
        log.info("Target attempt started", extra={"event": "target.attempt_started", "job_id": job_id, "target_id": target.id, "profile": plan.profile, "workflow": workflow, "attempt": attempt_number, "reason": reason, "timeout_s": plan.selection.timeout_s, "resumed_session": bool(session_id)})
        probed = await self.drivers.supports_structured_streaming(target, cancel_event)
        return attempt_id, started_at, probed

    async def _attempt(
        self, job: _Job, segment: _Segment, session_id: str, reason: str, held_probe: bool,
    ) -> _Finished:
        """Run one attempt and return its facts; a failure of the attempt itself propagates with its outcome."""
        target = segment.target
        job.attempts += 1
        number = job.attempts
        try:
            attempt_id, started_at, streams = await self._start_attempt(
                job.id, target, job.plan, job.workflow, session_id, number, job.cancel_event, reason,
            )
        except BaseException as exc:
            self._attach_outcome(exc, target, int((time.monotonic() - job.started_at) * 1000))
            raise
        counters: list[TokenCounters] = []
        result: DriverResult | None = None
        tool_started = False
        driver_exc: BaseException | None = None
        try:
            ask_env = self._issue_ask_env(job.id, job.plan, started_at)
            if job.cancel_event.is_set():
                result = _CANCELLED
            else:
                result, tool_started = await self._run_target_invocation(
                    job_id=job.id, attempt=number, attempt_tokens=counters, target=target, prompt=job.prompt,
                    session_id=session_id, cwd=job.cwd, timeout_s=job.plan.selection.timeout_s,
                    cancel_event=job.cancel_event, supports_streaming=streams,
                    env={**segment.bound_env, **(ask_env or {}), "REFRACT_JOB_ID": job.id},
                )
        except BaseException as exc:
            driver_exc = exc
        finally:
            revoke_exc: BaseException | None = None
            try:
                self._revoke_ask_token(job.id)
            except BaseException as exc:
                revoke_exc = exc
            if job.cancel_event.is_set() or isinstance(driver_exc, asyncio.CancelledError):
                result = _CANCELLED
            rec_exc: BaseException | None = None
            try:
                await self._record_attempt_finished(job.id, number, target, streams, result, driver_exc,
                                                    job.cancel_event)
            except BaseException as exc:
                rec_exc = exc
            self._log_attempt_finished(job, target, number, started_at, result, driver_exc)
            primary_exc = driver_exc or rec_exc or revoke_exc
            if primary_exc is not None:
                self._attach_outcome(
                    primary_exc, target, int((time.monotonic() - job.started_at) * 1000),
                    attempt_tokens=counters,
                )
                raise primary_exc
        asked = attempt_id is not None and await run_db(self.database.attempt_asked_question, attempt_id)
        result = result or DriverResult("REQUEST_FATAL", "", "", "execution_failed", "execution_error")
        return _Finished(
            result, counters[-1] if counters else None, int((time.monotonic() - started_at) * 1000), attempt_id,
            streams, tool_started,
            replay_safe(streams=streams, tool_started=tool_started, asked_question=asked),
            held_probe,
        )

    def _issue_ask_env(self, job_id: str, plan: ExecutionPlan, started_at: float) -> dict[str, str] | None:
        if self.ask_registry is None:
            return None
        token = self.ask_registry.issue_token(job_id, workflow_timeout_s=plan.selection.timeout_s, started_at=started_at)
        return {
            "REFRACT_ASK_URL": f"http://{self.config.host}:{self.config.port}/ask",
            "REFRACT_ASK_TOKEN": token,
            "REFRACT_ASK_TIMEOUT_S": str(self.config.ask_timeout_s),
        }

    def _revoke_ask_token(self, job_id: str) -> None:
        if self.ask_registry is not None:
            self.ask_registry.revoke_token(job_id)

    @staticmethod
    def _log_attempt_finished(
        job: _Job, target: TargetConfig, attempt_number: int, started_at: float, result: DriverResult | None,
        driver_exc: BaseException | None,
    ) -> None:
        if driver_exc is not None and result is None:
            result = DriverResult("REQUEST_FATAL", "", "", str(driver_exc), "execution_error")
        if result is not None:
            log.info("Target attempt finished", extra={
                "event": "target.attempt_finished", "job_id": job.id, "target_id": target.id,
                "workflow": job.workflow, "attempt": attempt_number, "outcome": result.outcome,
                "error_code": result.error_code, "duration_ms": int((time.monotonic() - started_at) * 1000),
            })

    async def _record_attempt_finished(
        self, job_id: str, attempt: int, target: TargetConfig, supports_streaming: bool,
        result: DriverResult | None, driver_exc: BaseException | None, cancel_event: CancelEvent,
    ) -> None:
        if not supports_streaming:
            return
        if result is None:
            result = DriverResult("REQUEST_FATAL", "", "", str(driver_exc) if driver_exc else "execution_failed",
                                  "execution_error")
        if cancel_event.is_set() or result.outcome == "CANCELLED":
            status = "cancelled"
        elif result.outcome == "SUCCESS":
            status = "succeeded"
        else:
            status = "failed"
        await self._record_stream_event(job_id, attempt, target, {
            "kind": "attempt.finished",
            "data": {"status": status, "outcome": result.outcome, "error_code": result.error_code},
        })

    @classmethod
    def _attach_outcome(
        cls, exc: BaseException, target: TargetConfig | None, duration_ms: int | None,
        *, attempt_tokens: list[TokenCounters] | None = None,
    ) -> None:
        if hasattr(exc, "_refract_outcome"):
            return
        cancelled = isinstance(exc, asyncio.CancelledError)
        result = DriverResult(
            "CANCELLED" if cancelled else "REQUEST_FATAL", "", "", "cancelled" if cancelled else str(exc),
            "cancelled" if cancelled else "execution_error",
        )
        try:
            setattr(exc, "_refract_outcome", cls._outcome(result, target, duration_ms, attempt_tokens=attempt_tokens))
        except (AttributeError, TypeError):
            pass

    @staticmethod
    def _failure_kind(result: DriverResult, circuit_open: bool = False) -> str | None:
        if result.outcome == "SUCCESS":
            return None
        if result.outcome == "CANCELLED":
            return "cancelled"
        if circuit_open or result.error_code == "circuit_open":
            return "circuit_open"
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
        result: DriverResult, target: TargetConfig | None, duration_ms: int | None, *,
        replay_safe: bool | None = None, circuit_open: bool = False, attempt_tokens: list[TokenCounters] | None = None,
    ) -> dict[str, Any]:
        """The final attempt's fields for the job's terminal commit."""
        model_name = result.model
        if model_name is None and target is not None:
            model_name = target.model or None
        outcome: dict[str, Any] = {
            "failure_kind": TargetExecutor._failure_kind(result, circuit_open),
            "model": model_name or "",
            "duration_ms": duration_ms,
            "tokens": tokens_of(attempt_tokens[-1] if attempt_tokens else None,
                                target.context_window if target is not None else None),
        }
        if replay_safe is not None:
            outcome["replay_safe"] = replay_safe
        return outcome
