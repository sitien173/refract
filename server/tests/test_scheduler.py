from __future__ import annotations

import asyncio
import threading

import pytest

from refract.scheduler import ProjectScheduler


@pytest.mark.asyncio
async def test_same_project_jobs_run_in_fifo_order() -> None:
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    calls: list[str] = []

    async def run_job(job_id: str, _: threading.Event) -> None:
        calls.append(job_id)
        if job_id == "a1":
            first_started.set()
            await release_first.wait()

    scheduler = ProjectScheduler(2, run_job)
    await scheduler.start()
    scheduler.enqueue("a1", "project-a")
    scheduler.enqueue("a2", "project-a")
    await first_started.wait()
    await asyncio.sleep(0)
    assert calls == ["a1"]
    release_first.set()
    await scheduler.wait("a2", 1)
    assert calls == ["a1", "a2"]
    await scheduler.close()


@pytest.mark.asyncio
async def test_different_projects_run_concurrently() -> None:
    both_started = asyncio.Event()
    release = asyncio.Event()
    active: set[str] = set()

    async def run_job(job_id: str, _: threading.Event) -> None:
        active.add(job_id)
        if len(active) == 2:
            both_started.set()
        await release.wait()
        active.remove(job_id)

    scheduler = ProjectScheduler(2, run_job)
    await scheduler.start()
    scheduler.enqueue("a1", "project-a")
    scheduler.enqueue("b1", "project-b")
    await asyncio.wait_for(both_started.wait(), 1)
    release.set()
    await scheduler.wait("a1", 1)
    await scheduler.wait("b1", 1)
    await scheduler.close()


@pytest.mark.asyncio
async def test_queued_cancel_removes_job_without_running() -> None:
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    calls: list[str] = []

    async def run_job(job_id: str, _: threading.Event) -> None:
        calls.append(job_id)
        if job_id == "a1":
            first_started.set()
            await release_first.wait()

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    scheduler.enqueue("a1", "project-a")
    scheduler.enqueue("a2", "project-a")
    await first_started.wait()
    assert scheduler.cancel("a2") == "queued"
    await asyncio.wait_for(scheduler.wait("a2"), 1)
    release_first.set()
    await scheduler.wait("a1", 1)
    assert calls == ["a1"]
    assert scheduler._completion_events == {}
    assert scheduler._queues == {}
    await scheduler.close()


@pytest.mark.asyncio
async def test_completed_job_supports_multiple_and_late_waiters() -> None:
    release = asyncio.Event()

    async def run_job(_: str, __: threading.Event) -> None:
        await release.wait()

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    scheduler.enqueue("job", "project")
    first = asyncio.create_task(scheduler.wait("job"))
    second = asyncio.create_task(scheduler.wait("job"))
    release.set()
    await asyncio.wait_for(asyncio.gather(first, second), 1)
    await asyncio.wait_for(scheduler.wait("job"), 1)
    assert scheduler._completion_events == {}
    assert scheduler._queues == {}
    await scheduler.close()


@pytest.mark.asyncio
async def test_close_releases_queued_waiters_and_bookkeeping() -> None:
    started = asyncio.Event()

    async def run_job(_: str, cancel_event: threading.Event) -> None:
        started.set()
        while not cancel_event.is_set():
            await asyncio.sleep(0)

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    scheduler.enqueue("running", "project")
    scheduler.enqueue("queued", "project")
    await started.wait()
    waiter = asyncio.create_task(scheduler.wait("queued"))
    await scheduler.close()

    await asyncio.wait_for(waiter, 1)
    assert scheduler._completion_events == {}
    assert scheduler._queues == {}
    assert scheduler._queued_projects == {}




@pytest.mark.asyncio
async def test_global_capacity_queues_jobs_from_other_projects() -> None:
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    release_first = asyncio.Event()

    async def run_job(job_id: str, _: threading.Event) -> None:
        if job_id == "first":
            first_started.set()
            await release_first.wait()
        else:
            second_started.set()

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    scheduler.enqueue("first", "project-a")
    await asyncio.wait_for(first_started.wait(), 1)
    scheduler.enqueue("second", "project-b")

    assert not second_started.is_set()
    release_first.set()
    await asyncio.wait_for(second_started.wait(), 1)
    await asyncio.wait_for(scheduler.wait("second", 1), 1)
    await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_worker_survives_run_callback_exception() -> None:
    second_started = asyncio.Event()

    async def run_job(job_id: str, _: threading.Event) -> None:
        if job_id == "fails":
            raise RuntimeError("injected callback failure")
        second_started.set()

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    scheduler.enqueue("fails", "project-a")
    scheduler.enqueue("succeeds", "project-b")
    await asyncio.wait_for(second_started.wait(), 1)
    await asyncio.wait_for(scheduler.wait("succeeds", 1), 1)
    await scheduler.close()


@pytest.mark.asyncio
async def test_terminal_commit_releases_project_before_notifier_finishes() -> None:
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    allow_first_to_return = asyncio.Event()

    async def run_job(job_id: str, _: threading.Event) -> None:
        if job_id == "first":
            first_started.set()
            await allow_first_to_return.wait()
        else:
            second_started.set()

    scheduler = ProjectScheduler(2, run_job)
    await scheduler.start()
    scheduler.enqueue("first", "project")
    await asyncio.wait_for(first_started.wait(), 1)
    scheduler.complete("first", signal=False)
    scheduler.enqueue("second", "project")
    await asyncio.wait_for(second_started.wait(), 1)
    allow_first_to_return.set()
    await scheduler.wait("second", 1)
    await scheduler.close()


@pytest.mark.asyncio
async def test_old_terminal_dispatch_cleanup_does_not_signal_retry_waiter() -> None:
    first_started = asyncio.Event()
    finish_old_dispatch = asyncio.Event()
    retry_started = asyncio.Event()
    finish_retry = asyncio.Event()
    calls = 0

    async def run_job(_: str, __: threading.Event) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            first_started.set()
            await finish_old_dispatch.wait()
        else:
            retry_started.set()
            await finish_retry.wait()

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    scheduler.enqueue("retryable", "project")
    await asyncio.wait_for(first_started.wait(), 1)
    scheduler.complete("retryable")
    scheduler.enqueue("retryable", "project")
    waiter = asyncio.create_task(scheduler.wait("retryable"))
    finish_old_dispatch.set()
    await asyncio.wait_for(retry_started.wait(), 1)
    assert not waiter.done()
    finish_retry.set()
    await asyncio.wait_for(waiter, 1)
    await scheduler.close()
