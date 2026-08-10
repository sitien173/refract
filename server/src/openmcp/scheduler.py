"""Global workers with per-project FIFO serialization."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from collections.abc import Awaitable, Callable, Iterable


RunJob = Callable[[str, threading.Event], Awaitable[None]]


class ProjectScheduler:
    def __init__(self, max_jobs: int, run_job: RunJob) -> None:
        self.max_jobs = max_jobs
        self._run_job = run_job
        self._ready: asyncio.Queue[str | None] = asyncio.Queue()
        self._queues: dict[str, deque[str]] = {}
        self._queued_projects: dict[str, str] = {}
        self._scheduled_projects: set[str] = set()
        self._active_projects: set[str] = set()
        self._cancel_events: dict[str, threading.Event] = {}
        self._completion_events: dict[str, asyncio.Event] = {}
        self._workers: list[asyncio.Task[None]] = []
        self._closing = False

    @property
    def workers(self) -> int:
        return sum(not worker.done() for worker in self._workers)

    @property
    def active_jobs(self) -> int:
        return len(self._cancel_events)

    @property
    def queued_jobs(self) -> int:
        return len(self._queued_projects)

    async def start(self, queued: Iterable[tuple[str, str]] = ()) -> None:
        self._closing = False
        self._workers = [
            asyncio.create_task(self._worker(), name=f"openmcp-worker-{index}")
            for index in range(self.max_jobs)
        ]
        for job_id, project_id in queued:
            self.enqueue(job_id, project_id)

    def enqueue(self, job_id: str, project_id: str) -> None:
        if job_id in self._queued_projects or job_id in self._cancel_events:
            return
        self._completion_events[job_id] = asyncio.Event()
        self._queues.setdefault(project_id, deque()).append(job_id)
        self._queued_projects[job_id] = project_id
        self._schedule(project_id)

    async def wait(self, job_id: str, timeout_s: int = 0) -> None:
        event = self._completion_events.get(job_id)
        if event is None:
            return
        if timeout_s > 0:
            try:
                await asyncio.wait_for(event.wait(), timeout_s)
            except TimeoutError:
                return
        else:
            await event.wait()

    def cancel(self, job_id: str) -> str:
        running = self._cancel_events.get(job_id)
        if running is not None:
            running.set()
            return "running"
        project_id = self._queued_projects.pop(job_id, "")
        if not project_id:
            return "missing"
        queue = self._queues[project_id]
        queue.remove(job_id)
        if not queue:
            self._queues.pop(project_id, None)
        self.signal(job_id)
        return "queued"

    async def close(self) -> None:
        self._closing = True
        for event in self._cancel_events.values():
            event.set()
        for _ in self._workers:
            self._ready.put_nowait(None)
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        for job_id in tuple(self._completion_events):
            self.signal(job_id)
        self._queues.clear()
        self._queued_projects.clear()
        self._scheduled_projects.clear()

    def signal(self, job_id: str) -> None:
        event = self._completion_events.pop(job_id, None)
        if event is not None:
            event.set()

    def _schedule(self, project_id: str) -> None:
        if (
            self._closing
            or project_id in self._active_projects
            or project_id in self._scheduled_projects
            or not self._queues.get(project_id)
        ):
            return
        self._scheduled_projects.add(project_id)
        self._ready.put_nowait(project_id)

    async def _worker(self) -> None:
        while True:
            project_id = await self._ready.get()
            try:
                if project_id is None:
                    return
                self._scheduled_projects.discard(project_id)
                queue = self._queues.get(project_id)
                if self._closing or not queue:
                    continue
                job_id = queue.popleft()
                self._queued_projects.pop(job_id, None)
                self._active_projects.add(project_id)
                cancel_event = threading.Event()
                self._cancel_events[job_id] = cancel_event
                try:
                    await self._run_job(job_id, cancel_event)
                finally:
                    self._cancel_events.pop(job_id, None)
                    self._active_projects.discard(project_id)
                    self.signal(job_id)
                    self._schedule(project_id)
                    if not self._queues.get(project_id):
                        self._queues.pop(project_id, None)
            finally:
                self._ready.task_done()


__all__ = ["ProjectScheduler"]
