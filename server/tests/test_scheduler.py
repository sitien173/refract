from __future__ import annotations

import asyncio
import threading

import pytest

from refract.scheduling.cancel import CancelEvent
from refract.scheduling.scheduler import ProjectScheduler


async def _settled(scheduler: ProjectScheduler) -> None:
    """Wait until every dispatched task has returned."""
    await asyncio.wait_for(asyncio.gather(*scheduler._tasks), 1)


@pytest.mark.asyncio
async def test_jobs_run_concurrently_up_to_capacity() -> None:
    both_started = asyncio.Event()
    release = asyncio.Event()
    active: set[str] = set()

    async def run_job(job_id: str, _: threading.Event) -> None:
        active.add(job_id)
        if len(active) == 2:
            both_started.set()
        await release.wait()

    scheduler = ProjectScheduler(2, run_job)
    await scheduler.start()
    scheduler.enqueue("a1")
    scheduler.enqueue("a2")
    await asyncio.wait_for(both_started.wait(), 1)
    release.set()
    await _settled(scheduler)
    await scheduler.close()


def test_scheduler_has_exactly_one_queue_structure() -> None:
    scheduler = ProjectScheduler(1, lambda *_: asyncio.sleep(0))
    queues = [
        name for name, value in vars(scheduler).items()
        if isinstance(value, asyncio.Queue) or type(value).__name__ == "deque"
    ]
    assert queues == ["_queue"]


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
    scheduler.enqueue("a1")
    scheduler.enqueue("a2")
    await first_started.wait()
    assert scheduler.queued_jobs == 1
    assert scheduler.cancel("a2") == "queued"
    assert scheduler.queued_jobs == 0
    release_first.set()
    await _settled(scheduler)
    assert calls == ["a1"]
    assert scheduler._current == {}
    await scheduler.close()


@pytest.mark.asyncio
async def test_cancel_reports_missing_and_running() -> None:
    started = asyncio.Event()
    seen: list[threading.Event] = []

    async def run_job(_: str, cancel_event: threading.Event) -> None:
        seen.append(cancel_event)
        started.set()
        await asyncio.get_running_loop().run_in_executor(None, cancel_event.wait)

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    assert scheduler.cancel("nope") == "missing"
    scheduler.enqueue("job")
    await started.wait()
    assert scheduler.cancel("job") == "running"
    assert seen[0].is_set()
    await _settled(scheduler)
    await scheduler.close()


@pytest.mark.asyncio
async def test_fifo_admission_order() -> None:
    order: list[str] = []

    async def run_job(job_id: str, _: threading.Event) -> None:
        order.append(job_id)
        await asyncio.sleep(0)

    scheduler = ProjectScheduler(1, run_job)
    for name in ("a", "b", "c"):
        scheduler.enqueue(name)
    await scheduler.start()
    while scheduler._tasks or scheduler.queued_jobs:
        await asyncio.sleep(0)
    assert order == ["a", "b", "c"]
    await scheduler.close()


@pytest.mark.asyncio
async def test_close_cancels_running_keeps_queued_and_clears_bookkeeping() -> None:
    started = asyncio.Event()

    async def run_job(_: str, cancel_event: CancelEvent) -> None:
        started.set()
        await cancel_event.wait_async()

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    scheduler.enqueue("running")
    scheduler.enqueue("queued")
    await started.wait()
    await scheduler.close()

    assert scheduler._current == {}
    assert not scheduler._queue
    assert not scheduler._tasks


@pytest.mark.asyncio
async def test_close_cancels_job_whose_slot_was_already_released() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def run_job(_: str, cancel_event: CancelEvent) -> None:
        started.set()
        await cancel_event.wait_async()
        cancelled.set()

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    scheduler.enqueue("job")
    await started.wait()
    scheduler.complete("job")
    assert scheduler.active_jobs == 0
    await scheduler.close()
    assert cancelled.is_set()


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
    scheduler.enqueue("first")
    await asyncio.wait_for(first_started.wait(), 1)
    scheduler.enqueue("second")

    assert not second_started.is_set()
    release_first.set()
    await asyncio.wait_for(second_started.wait(), 1)
    await _settled(scheduler)
    await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_survives_run_callback_exception() -> None:
    second_started = asyncio.Event()

    async def run_job(job_id: str, _: threading.Event) -> None:
        if job_id == "fails":
            raise RuntimeError("injected callback failure")
        second_started.set()

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    scheduler.enqueue("fails")
    scheduler.enqueue("succeeds")
    await asyncio.wait_for(second_started.wait(), 1)
    await _settled(scheduler)
    await scheduler.close()


@pytest.mark.asyncio
async def test_terminal_commit_reserves_next_job_but_worker_starts_it_after_callback_returns() -> None:
    first_started = asyncio.Event()
    second_started = asyncio.Event()
    allow_first_to_return = asyncio.Event()

    async def run_job(job_id: str, _: threading.Event) -> None:
        if job_id == "first":
            first_started.set()
            await allow_first_to_return.wait()
        else:
            second_started.set()

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    scheduler.enqueue("first")
    await asyncio.wait_for(first_started.wait(), 1)
    scheduler.complete("first")
    scheduler.enqueue("second")
    # The slot is free, so `second` holds the reservation, but the only worker is still in the first callback.
    assert scheduler.active_jobs == 1
    assert not scheduler._current["second"].started
    assert not second_started.is_set()
    allow_first_to_return.set()
    await asyncio.wait_for(second_started.wait(), 1)
    await _settled(scheduler)
    await scheduler.close()


@pytest.mark.asyncio
async def test_old_dispatch_cleanup_does_not_release_requeued_job() -> None:
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
    scheduler.enqueue("retryable")
    await asyncio.wait_for(first_started.wait(), 1)
    scheduler.complete("retryable")
    scheduler.enqueue("retryable")
    finish_old_dispatch.set()
    await asyncio.wait_for(retry_started.wait(), 1)
    assert "retryable" in scheduler._current
    assert scheduler.active_jobs == 1
    finish_retry.set()
    await _settled(scheduler)
    await scheduler.close()


@pytest.mark.asyncio
async def test_busy_session_waiters_do_not_starve_other_sessions() -> None:
    release = asyncio.Event()
    started: list[str] = []
    session_s, session_t = ("p", "s", "w"), ("p", "t", "w")

    async def run_job(job_id: str, _: threading.Event) -> None:
        started.append(job_id)
        if job_id.startswith("s"):
            await release.wait()

    scheduler = ProjectScheduler(4, run_job)
    await scheduler.start()
    for name in ("s1", "s2", "s3", "s4"):
        scheduler.enqueue(name, session_s)
    scheduler.enqueue("t1", session_t)
    await asyncio.sleep(0.05)
    assert started == ["s1", "t1"]
    assert scheduler.queued_jobs == 3
    assert scheduler.cancel("s3") == "queued"
    release.set()
    await asyncio.sleep(0.05)
    assert started == ["s1", "t1", "s2", "s4"]
    await scheduler.close()


@pytest.mark.asyncio
async def test_reserved_job_starts_behind_unreservable_session_waiter_when_worker_frees() -> None:
    release_a1 = asyncio.Event()
    b_committed = asyncio.Event()
    release_b = asyncio.Event()
    started: list[str] = []
    session_a, session_b, session_c = ("p", "a", "w"), ("p", "b", "w"), ("p", "c", "w")

    async def run_job(job_id: str, _: threading.Event) -> None:
        started.append(job_id)
        if job_id == "a1":
            await release_a1.wait()
        elif job_id == "b":
            await b_committed.wait()
            await release_b.wait()

    scheduler = ProjectScheduler(2, run_job)
    await scheduler.start()
    scheduler.enqueue("a1", session_a)
    scheduler.enqueue("b", session_b)
    await asyncio.sleep(0.05)
    scheduler.enqueue("a2", session_a)
    scheduler.enqueue("c", session_c)
    await asyncio.sleep(0.05)
    assert started == ["a1", "b"]
    # b commits: c takes the freed reservation but b's callback still holds the second worker.
    scheduler.complete("b")
    b_committed.set()
    await asyncio.sleep(0.05)
    assert started == ["a1", "b"]
    assert scheduler.active_jobs == 2
    release_b.set()
    await asyncio.sleep(0.05)
    # a2 waits behind a1's session lock; reserved c must start without a1 finishing.
    assert started == ["a1", "b", "c"]
    assert scheduler.queued_jobs == 1
    release_a1.set()
    await asyncio.sleep(0.05)
    assert started == ["a1", "b", "c", "a2"]
    await scheduler.close()
