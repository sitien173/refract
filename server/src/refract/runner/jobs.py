"""JobRunner: runs one queued job through `TargetExecutor` and commits its terminal state."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from refract.store.database import Database
from refract.logging_setup import get_logger
from refract.models import ProjectView, TERMINAL_STATES
from refract.runner.attempts import TargetExecutionResult, TargetExecutor
from refract.runner.drivers import DriverResult
from refract.runner.planning import parse_execution_plan
from refract.scheduling.cancel import CancelEvent
from refract.store.pool import run_db, run_on

log = get_logger("execution")

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
        return await run_on(self.database.executor, work)

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
        record = await run_db(self.database.job_record, job_id)
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
        # Held for the whole job and released after the terminal commit, before the terminal signal.
        session_scope = AsyncExitStack()
        try:
            hold = self.targets.hold_session(project.id, record["session"], record["workflow"], cancel_event)
            if not await session_scope.enter_async_context(hold):
                # Cancelled or shut down while queued behind the session; the job keeps its queued row.
                return
            if not await run_db(self.database.start_job, job_id):
                # Cancel won the queued-to-running transition; it owns the terminal state and publication.
                return
            await self._notify(job_id)
            plan = parse_execution_plan(json.loads(record["plan_json"]))
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
                changed = await self._commit(job_id, self.database.finish_job, job_id, final_state, error=execution.result.error or execution.result.outcome, next_target=execution.next_target, **outcome)
                committed_state = final_state
                await session_scope.aclose()
                await self._terminal(job_id, final_state, changed)
                await self._notify(job_id)
                return
            changed = await self._finish_success(job_id, project, record, execution)
            committed_state = "succeeded"
            await session_scope.aclose()
            await self._terminal(job_id, committed_state, changed)
            await self._notify(job_id)
        except asyncio.CancelledError as exc:
            await self._finish_cancelled_job(job_id, exc, committed_state)
            raise
        except Exception as exc:
            await self._finish_failed_job(job_id, exc, final_state, committed_state, outcome)
        finally:
            await session_scope.aclose()
            self._commits.pop(job_id, None)
            completed = await run_db(self.database.job, job_id)
            log.info("Job finished", extra={"event": "job.finished", "job_id": job_id, "project_id": project_id, "state": completed.state if completed else "unknown", "duration_ms": round((time.monotonic() - started_at) * 1000, 2)})

    async def _prepare_job(self, job_id: str, project_id: str, cancel_event: CancelEvent) -> ProjectView | None:
        if self.is_closing():
            # A reserved-but-undispatched queue item remains durable for restart.
            return None
        if cancel_event.is_set():
            state = "interrupted" if self.is_closing() else "cancelled"
            await self._finish_reporting(job_id, state, error="cancelled before execution")
            return None
        project = await run_db(self.database.project, project_id)
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
        completed = await run_db(self.database.job, job_id)
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


__all__ = ["JobNotifier", "JobRunner"]
