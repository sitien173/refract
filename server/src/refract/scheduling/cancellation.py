"""Cancel by compare-and-set. A terminal job is never overwritten."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Literal

from refract.logging_setup import get_logger
from refract.models import LIST_JOB_ID_ACTION, UNKNOWN_JOB_MESSAGE, OrchestrationError
from refract.scheduling.asks import AskRegistry
from refract.scheduling.hub import Hub
from refract.scheduling.scheduler import ProjectScheduler
from refract.store.database import Database
from refract.store.pool import run_db

log = get_logger("runtime")
CancelStatus = Literal["terminated", "requested", "already_terminal"]


class Canceller:
    def __init__(
        self,
        database: Database,
        scheduler: ProjectScheduler,
        hub: Hub,
        asks: AskRegistry,
        notify: Callable[[str], Awaitable[None]],
    ) -> None:
        self.database = database
        self.scheduler = scheduler
        self.hub = hub
        self.asks = asks
        self.notify = notify
        # Queued-cancel completions detached from their caller so a cancelled caller still publishes terminal.
        self.tasks: set[asyncio.Task[CancelStatus]] = set()

    async def cancel_job(self, job_id: str) -> CancelStatus:
        self.asks.revoke_token(job_id)
        job = await run_db(self.database.job, job_id)
        if job is None:
            raise OrchestrationError(UNKNOWN_JOB_MESSAGE, code="unknown_job", next_action=LIST_JOB_ID_ACTION)
        if job.state == "queued":
            # The write, the CAS-loss signal and the follow-up run detached, so a cancelled caller loses neither.
            task = asyncio.ensure_future(self._cancel_queued(job_id))
            self.tasks.add(task)
            task.add_done_callback(self._task_done)
            return await asyncio.shield(task)
        if job.state == "running":
            self.scheduler.cancel(job_id)
            return "requested"
        return "already_terminal"

    def _task_done(self, task: asyncio.Task[CancelStatus]) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            log.error("Detached cancel failed", exc_info=error, extra={"event": "cancel.task_failed"})

    async def _cancel_queued(self, job_id: str) -> CancelStatus:
        """Queued-only terminal compare-and-set and its follow-up; returns the final `cancel_status`.

        On a win release the slot, notify, then publish `terminal`. On a loss a runner started the job
        between the caller's read and the compare-and-set, so signal the running dispatch here.
        """
        if not await run_db(self.database.finish_job, job_id, "cancelled", queued_only=True):
            job = await run_db(self.database.job, job_id)
            if job is not None and job.state == "running":
                self.scheduler.cancel(job_id)
                return "requested"
            return "already_terminal"
        try:
            # Wake a dispatch that is still waiting on its session lock, then free its slot.
            self.scheduler.cancel(job_id)
            self.scheduler.complete(job_id)
            await self.notify(job_id)
        finally:
            self.hub.publish(job_id, "terminal")
        return "terminated"

    async def drain(self) -> None:
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
