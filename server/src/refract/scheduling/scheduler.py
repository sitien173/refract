"""Global worker pool with FIFO admission."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol, override

from refract.scheduling.cancel import CancelEvent


class _SchedulerLifecycle(Protocol):
    """Keep startup and shutdown awaitable for runtime lifecycle callers."""

    async def start(self) -> None: ...

    async def close(self) -> None: ...


RunJob = Callable[[str, CancelEvent], Awaitable[None]]


@dataclass(slots=True, eq=False)
class _Dispatch:
    job_id: str
    session_key: tuple[str, ...] | None = None
    cancel_event: CancelEvent = field(default_factory=CancelEvent)
    started: bool = False


class ProjectScheduler(_SchedulerLifecycle):
    """Admit queued jobs in FIFO order, at most `max_jobs` at a time.

    A job whose session key is held by an admitted job stays queued and is skipped, so it never occupies a worker slot.
    """

    def __init__(self, max_jobs: int, run_job: RunJob, on_finished: Callable[[str], None] | None = None) -> None:
        if max_jobs < 1:
            raise ValueError("max_jobs must be positive")
        self.max_jobs = max_jobs
        self._run_job = run_job
        self._on_finished = on_finished
        self._queue: deque[_Dispatch] = deque()
        self._current: dict[str, _Dispatch] = {}
        self._active: set[_Dispatch] = set()
        self._tasks: dict[asyncio.Task[None], _Dispatch] = {}
        self._busy_sessions: dict[tuple[str, ...], _Dispatch] = {}
        self._closing = False
        self._started = False

    @property
    def workers(self) -> int:
        return self.max_jobs if self._started else 0

    @property
    def active_jobs(self) -> int:
        return len(self._active)

    @property
    def queued_jobs(self) -> int:
        return len(self._queue)

    @override
    async def start(self) -> None:
        self._closing = False
        self._started = True
        self._schedule()

    def enqueue(self, job_id: str, session_key: tuple[str, ...] | None = None) -> None:
        """Queue one job for FIFO admission; jobs sharing a `session_key` run one at a time, in queue order."""
        if job_id in self._current:
            return
        dispatch = _Dispatch(job_id=job_id, session_key=session_key)
        self._current[job_id] = dispatch
        self._queue.append(dispatch)
        self._schedule()

    def cancel(self, job_id: str) -> str:
        """Cancel a queued job outright or signal a running one; returns `missing`, `queued`, or `running`."""
        dispatch = self._current.get(job_id)
        if dispatch is None:
            return "missing"
        if dispatch.started:
            dispatch.cancel_event.set()
            return "running"
        self._release(dispatch)
        return "queued"

    def complete(self, job_id: str) -> None:
        """Release the admission slot at terminal commit, before the run callback returns."""
        dispatch = self._current.get(job_id)
        if dispatch is not None:
            self._release(dispatch)

    @override
    async def close(self) -> None:
        self._closing = True
        # Tasks outlive their slot once `complete` runs, so cancel through the task map.
        for dispatch in tuple(self._tasks.values()):
            dispatch.cancel_event.set()
        tasks = tuple(self._tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._started = False
        # Queued jobs stay durable in SQLite and are re-enqueued on next start.
        self._queue.clear()
        self._current.clear()
        self._active.clear()
        self._tasks.clear()
        self._busy_sessions.clear()

    def _schedule(self) -> None:
        if self._closing or not self._started:
            return
        # Walk the queue in order: a job whose session is busy is skipped and keeps its place, and the first
        # job of each idle session reserves it. A reserved job starts only when a worker task is free,
        # and a task stays a worker until its run callback returns. Never stop early: a reserved job can sit
        # behind a skipped or unreservable one and still needs its start.
        for dispatch in tuple(self._queue):
            key = dispatch.session_key
            if dispatch not in self._active:
                if len(self._active) >= self.max_jobs:
                    continue
                if key is not None and key in self._busy_sessions:
                    continue
                self._active.add(dispatch)
                if key is not None:
                    self._busy_sessions[key] = dispatch
            if len(self._tasks) >= self.max_jobs:
                continue
            self._queue.remove(dispatch)
            dispatch.started = True
            task = asyncio.create_task(self._run(dispatch), name=f"refract-job-{dispatch.job_id}")
            self._tasks[task] = dispatch
            task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.pop(task, None)
        self._schedule()

    def _release(self, dispatch: _Dispatch) -> None:
        if dispatch in self._queue:
            self._queue.remove(dispatch)
        self._active.discard(dispatch)
        key = dispatch.session_key
        if key is not None and self._busy_sessions.get(key) is dispatch:
            del self._busy_sessions[key]
        if self._current.get(dispatch.job_id) is dispatch:
            del self._current[dispatch.job_id]
        self._schedule()

    async def _run(self, dispatch: _Dispatch) -> None:
        try:
            await self._run_job(dispatch.job_id, dispatch.cancel_event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).exception(
                "Scheduled job callback failed", extra={"job_id": dispatch.job_id}
            )
        finally:
            self._release(dispatch)
            if self._on_finished is not None:
                self._on_finished(dispatch.job_id)


__all__ = ["CancelEvent", "ProjectScheduler"]
