"""Global worker pool with FIFO admission."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol, override


class _SchedulerLifecycle(Protocol):
    """Keep startup and shutdown awaitable for runtime lifecycle callers."""

    async def start(self) -> None: ...

    async def close(self) -> None: ...


class CancelEvent(threading.Event):
    """Thread-safe cancellation with an event-loop waiter."""

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._async_event = asyncio.Event()

    def set(self) -> None:
        super().set()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._async_event.set)

    async def wait_async(self) -> None:
        self._loop = asyncio.get_running_loop()
        if self.is_set():
            return
        await self._async_event.wait()


RunJob = Callable[[str, CancelEvent], Awaitable[None]]


@dataclass(slots=True, eq=False)
class _Dispatch:
    job_id: str
    completion: asyncio.Event = field(default_factory=asyncio.Event)
    cancel_event: CancelEvent = field(default_factory=CancelEvent)
    reserved: bool = False
    started: bool = False


class ProjectScheduler(_SchedulerLifecycle):
    """Reserve global admission before dispatching a job."""

    def __init__(
        self,
        max_jobs: int,
        run_job: RunJob,
    ) -> None:
        if max_jobs < 1:
            raise ValueError("max_jobs must be positive")
        self.max_jobs = max_jobs
        self._run_job = run_job
        self._ready: asyncio.Queue[_Dispatch | None] = asyncio.Queue()
        self._pending: deque[_Dispatch] = deque()
        self._current: dict[str, _Dispatch] = {}
        self._terminal_waiters: dict[str, _Dispatch] = {}
        self._active: set[_Dispatch] = set()
        self._workers: list[asyncio.Task[None]] = []
        self._closing = False
        self._started = False

    @property
    def workers(self) -> int:
        return sum(not worker.done() for worker in self._workers)

    @property
    def active_jobs(self) -> int:
        return len(self._active)

    @property
    def queued_jobs(self) -> int:
        return len(self._pending)

    @override
    async def start(self) -> None:
        self._closing = False
        self._started = True
        self._workers = [
            asyncio.create_task(self._worker(), name=f"refract-worker-{index}")
            for index in range(self.max_jobs)
        ]
        self._schedule()

    def enqueue(self, job_id: str) -> None:
        """Queue one job for FIFO admission."""
        existing = self._current.get(job_id)
        if existing is not None:
            return
        dispatch = _Dispatch(job_id=job_id)
        self._current[job_id] = dispatch
        self._pending.append(dispatch)
        self._schedule()

    async def wait(self, job_id: str, timeout_s: int = 0) -> None:
        dispatch = self._current.get(job_id) or self._terminal_waiters.get(job_id)
        if dispatch is not None:
            await self._wait_for(dispatch.completion, timeout_s)

    @staticmethod
    async def _wait_for(event: asyncio.Event, timeout_s: int) -> None:
        if timeout_s > 0:
            try:
                await asyncio.wait_for(event.wait(), timeout_s)
            except TimeoutError:
                return
        else:
            await event.wait()

    def cancel(self, job_id: str) -> str:
        dispatch = self._current.get(job_id)
        if dispatch is None:
            return "missing"
        if dispatch.reserved and dispatch.started:
            dispatch.cancel_event.set()
            return "running"
        if dispatch.reserved:
            dispatch.cancel_event.set()
            self._release(dispatch)
            return "queued"
        self._release(dispatch)
        return "queued"

    def complete(self, job_id: str, *, signal: bool = True) -> None:
        """Release admission at terminal commit, optionally deferring waiter release."""
        dispatch = self._current.get(job_id)
        if dispatch is not None:
            self._release(dispatch, signal=signal)

    @override
    async def close(self) -> None:
        self._closing = True
        for dispatch in tuple(self._active):
            dispatch.cancel_event.set()
        for dispatch in tuple(self._terminal_waiters.values()):
            dispatch.completion.set()
        # Pending jobs stay durable in SQLite and are re-enqueued on next start.
        for dispatch in tuple(self._pending):
            self._release(dispatch, schedule=False)
        for _ in self._workers:
            self._ready.put_nowait(None)
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        for dispatch in tuple(self._active):
            self._release(dispatch, schedule=False)
        self._started = False
        self._pending.clear()
        self._current.clear()
        self._terminal_waiters.clear()
        self._active.clear()

    def _schedule(self) -> None:
        if self._closing or not self._started:
            return
        while self._pending and len(self._active) < self.max_jobs:
            selected = self._pending.popleft()
            selected.reserved = True
            self._active.add(selected)
            self._ready.put_nowait(selected)

    def _release(
        self,
        dispatch: _Dispatch,
        *,
        schedule: bool = True,
        signal: bool = True,
    ) -> None:
        if dispatch in self._pending:
            self._pending.remove(dispatch)
        if dispatch.reserved:
            dispatch.reserved = False
            self._active.discard(dispatch)
        if self._current.get(dispatch.job_id) is dispatch:
            self._current.pop(dispatch.job_id, None)
            if signal:
                dispatch.completion.set()
            else:
                self._terminal_waiters[dispatch.job_id] = dispatch
        elif signal:
            dispatch.completion.set()
        if signal and self._terminal_waiters.get(dispatch.job_id) is dispatch:
            self._terminal_waiters.pop(dispatch.job_id, None)
        if schedule:
            self._schedule()

    async def _worker(self) -> None:
        while True:
            dispatch = await self._ready.get()
            try:
                if dispatch is None:
                    return
                if (
                    not dispatch.reserved
                    or self._current.get(dispatch.job_id) is not dispatch
                ):
                    continue
                dispatch.started = True
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
            finally:
                self._ready.task_done()


__all__ = ["ProjectScheduler"]
