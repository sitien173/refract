from __future__ import annotations

import asyncio
import threading

import pytest

from openmcp.scheduler import ProjectScheduler


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
async def test_same_project_readers_with_distinct_scopes_overlap() -> None:
    started: set[str] = set()
    both_started = asyncio.Event()
    release = asyncio.Event()

    async def run_job(job_id: str, _: threading.Event) -> None:
        started.add(job_id)
        if len(started) == 2:
            both_started.set()
        await release.wait()

    scheduler = ProjectScheduler(2, run_job, max_project_readers=2)
    await scheduler.start()
    for job_id, scope in (("reader-a", "scope-a"), ("reader-b", "scope-b")):
        scheduler.enqueue(
            job_id,
            "project",
            access_mode="parallel_read",
            workflow="consult",
            context_key=scope,
        )
    await asyncio.wait_for(both_started.wait(), 1)
    assert started == {"reader-a", "reader-b"}
    release.set()
    await asyncio.gather(scheduler.wait("reader-a", 1), scheduler.wait("reader-b", 1))
    await scheduler.close()


@pytest.mark.asyncio
async def test_identical_read_session_scopes_serialize_even_when_fresh() -> None:
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()

    async def run_job(job_id: str, _: threading.Event) -> None:
        if job_id == "fresh-one":
            first_started.set()
            await release_first.wait()
        else:
            second_started.set()

    scheduler = ProjectScheduler(2, run_job, max_project_readers=2)
    await scheduler.start()
    for job_id in ("fresh-one", "fresh-two"):
        scheduler.enqueue(
            job_id,
            "project",
            access_mode="parallel_read",
            workflow="consult",
            context_key="same-scope",
        )
    await asyncio.wait_for(first_started.wait(), 1)
    assert scheduler.waiting_reason("fresh-two") == "waiting for project session scope"
    assert not second_started.is_set()
    release_first.set()
    await asyncio.wait_for(second_started.wait(), 1)
    await scheduler.wait("fresh-two", 1)
    await scheduler.close()


@pytest.mark.asyncio
async def test_ready_writer_is_barrier_for_later_readers() -> None:
    first_reader_started = asyncio.Event()
    release_first_reader = asyncio.Event()
    writer_started = asyncio.Event()
    release_writer = asyncio.Event()
    later_reader_started = asyncio.Event()

    async def run_job(job_id: str, _: threading.Event) -> None:
        if job_id == "reader-first":
            first_reader_started.set()
            await release_first_reader.wait()
        elif job_id == "writer":
            writer_started.set()
            await release_writer.wait()
        else:
            later_reader_started.set()

    scheduler = ProjectScheduler(3, run_job, max_project_readers=3)
    await scheduler.start()
    scheduler.enqueue("reader-first", "project", access_mode="parallel_read", workflow="review", context_key="one")
    await asyncio.wait_for(first_reader_started.wait(), 1)
    scheduler.enqueue("writer", "project", access_mode="exclusive", workflow="implement", context_key="write")
    scheduler.enqueue("reader-later", "project", access_mode="parallel_read", workflow="review", context_key="two")
    assert scheduler.waiting_reason("writer") == "waiting for project readers to finish"
    assert scheduler.waiting_reason("reader-later") == "waiting behind exclusive job writer"
    assert not later_reader_started.is_set()

    release_first_reader.set()
    await asyncio.wait_for(writer_started.wait(), 1)
    assert not later_reader_started.is_set()
    release_writer.set()
    await asyncio.wait_for(later_reader_started.wait(), 1)
    await asyncio.wait_for(scheduler.wait("reader-later", 1), 1)
    await scheduler.close()


@pytest.mark.asyncio
async def test_dependency_blocked_candidate_uses_no_worker_and_does_not_block_ready_work() -> None:
    dependency_succeeded = False
    blocked_started = asyncio.Event()
    independent_started = asyncio.Event()
    release_independent = asyncio.Event()

    def ready(job_id: str) -> bool:
        return dependency_succeeded if job_id == "blocked" else True

    async def run_job(job_id: str, _: threading.Event) -> None:
        if job_id == "blocked":
            blocked_started.set()
        else:
            independent_started.set()
            await release_independent.wait()

    scheduler = ProjectScheduler(1, run_job, is_ready=ready)
    await scheduler.start()
    scheduler.enqueue("blocked", "project-a", access_mode="exclusive")
    scheduler.enqueue("independent", "project-b", access_mode="exclusive")
    await asyncio.wait_for(independent_started.wait(), 1)
    assert scheduler.waiting_reason("blocked") == "waiting on dependency"
    assert not blocked_started.is_set()
    dependency_succeeded = True
    scheduler.reevaluate()
    release_independent.set()
    await asyncio.wait_for(blocked_started.wait(), 1)
    await asyncio.wait_for(scheduler.wait("blocked", 1), 1)
    await scheduler.close()


@pytest.mark.asyncio
async def test_active_writer_reports_exclusive_and_reader_wait_reasons() -> None:
    writer_started = asyncio.Event()
    release_writer = asyncio.Event()
    async def run_job(job_id: str, _: threading.Event) -> None:
        if job_id == "active-writer":
            writer_started.set()
            await release_writer.wait()

    scheduler = ProjectScheduler(3, run_job, max_project_readers=2)
    await scheduler.start()
    scheduler.enqueue("active-writer", "project", access_mode="exclusive", workflow="implement", context_key="write")
    await asyncio.wait_for(writer_started.wait(), 1)
    scheduler.enqueue("reader", "project", access_mode="parallel_read", workflow="consult", context_key="read")
    scheduler.enqueue("writer-2", "project", access_mode="exclusive", workflow="review", context_key="write-2")

    assert scheduler.waiting_reason("writer-2") == "waiting for project exclusive job"
    assert scheduler.waiting_reason("reader") == "waiting for project write slot"
    release_writer.set()
    await asyncio.wait_for(scheduler.wait("reader", 1), 1)
    await scheduler.close()


@pytest.mark.asyncio
async def test_dependency_blocked_writer_does_not_bar_later_reader() -> None:
    writer_ready = False
    writer_started = asyncio.Event()
    reader_started = asyncio.Event()
    later_reader_started = asyncio.Event()
    release_reader = asyncio.Event()
    release_writer = asyncio.Event()

    def ready(job_id: str) -> bool:
        return writer_ready if job_id == "blocked-writer" else True

    async def run_job(job_id: str, _: threading.Event) -> None:
        if job_id == "blocked-writer":
            writer_started.set()
            await release_writer.wait()
        elif job_id == "reader-later":
            later_reader_started.set()
        else:
            reader_started.set()
            await release_reader.wait()

    scheduler = ProjectScheduler(2, run_job, max_project_readers=2, is_ready=ready)
    await scheduler.start()
    scheduler.enqueue("blocked-writer", "project", access_mode="exclusive")
    scheduler.enqueue("reader", "project", access_mode="parallel_read", workflow="review", context_key="read")
    await asyncio.wait_for(reader_started.wait(), 1)
    assert not writer_started.is_set()

    writer_ready = True
    scheduler.reevaluate()
    scheduler.enqueue("reader-later", "project", access_mode="parallel_read", workflow="review", context_key="later")
    assert not writer_started.is_set()
    assert not later_reader_started.is_set()
    release_reader.set()
    await asyncio.wait_for(writer_started.wait(), 1)
    assert not later_reader_started.is_set()
    release_writer.set()
    await asyncio.wait_for(later_reader_started.wait(), 1)
    await asyncio.wait_for(scheduler.wait("reader-later", 1), 1)
    await scheduler.close()


@pytest.mark.asyncio
async def test_project_reader_capacity_refills_after_reader_completion() -> None:
    started: set[str] = set()
    first_two_started = asyncio.Event()
    third_started = asyncio.Event()
    releases = {job_id: asyncio.Event() for job_id in ("reader-1", "reader-2", "reader-3")}

    async def run_job(job_id: str, _: threading.Event) -> None:
        started.add(job_id)
        if len(started) == 2:
            first_two_started.set()
        if job_id == "reader-3":
            third_started.set()
        await releases[job_id].wait()

    scheduler = ProjectScheduler(3, run_job, max_project_readers=2)
    await scheduler.start()
    for index in range(1, 4):
        scheduler.enqueue(
            f"reader-{index}", "project", access_mode="parallel_read",
            workflow="review", context_key=f"scope-{index}",
        )
    await asyncio.wait_for(first_two_started.wait(), 1)
    assert started == {"reader-1", "reader-2"}
    assert scheduler.waiting_reason("reader-3") == "waiting for project reader capacity"
    assert not third_started.is_set()
    releases["reader-1"].set()
    await asyncio.wait_for(third_started.wait(), 1)
    releases["reader-2"].set()
    releases["reader-3"].set()
    await asyncio.gather(*(scheduler.wait(f"reader-{i}", 1) for i in range(1, 4)))
    await scheduler.close()


@pytest.mark.asyncio
async def test_global_capacity_waiting_reason_is_derived() -> None:
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def run_job(job_id: str, _: threading.Event) -> None:
        if job_id == "first":
            first_started.set()
            await release_first.wait()

    scheduler = ProjectScheduler(1, run_job)
    await scheduler.start()
    scheduler.enqueue("first", "project-a")
    await asyncio.wait_for(first_started.wait(), 1)
    scheduler.enqueue("second", "project-b")

    assert scheduler.waiting_reason("second") == "waiting for global worker capacity"
    release_first.set()
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
