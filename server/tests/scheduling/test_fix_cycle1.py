"""Fix cycle 1: deterministic reproductions of the review findings, forced with events and injected hooks."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from refract.scheduling.asks import NO_ANSWER_TEXT, AskAuthError, AskRegistry
from refract.store.database import Database
from refract.runtime import OrchestrationError, Runtime
from refract.scheduling.cancel import CancelEvent
from refract.scheduling.hub import Hub
from tests.orchestration_helpers import FakeDrivers, config, register_project, repository


async def _runtime(tmp_path: Path, drivers=None, *, start: bool = True, **overrides):
    root = repository(tmp_path)
    runtime = Runtime(replace(config(tmp_path / "home"), **overrides))
    runtime.drivers = drivers or FakeDrivers()
    if start:
        await runtime.start()
    return runtime, register_project(runtime, str(root))


def _registry(tmp_path: Path, job_id: str = "job-1", *, start: bool = True, **kwargs) -> tuple[AskRegistry, Database, Hub]:
    db = Database(tmp_path / "refract.db")
    db.upsert_project(project_id="proj", root=str(tmp_path))
    db.create_job(
        job_id=job_id, project_id="proj", session=job_id, workflow="implement", profile="balanced",
        prompt="work", plan_json="{}", fresh=True,
    )
    if start:
        db.start_job(job_id)
    hub = Hub()
    return AskRegistry(db, hub, **kwargs), db, hub


def _states(db: Database, job_id: str) -> list[str]:
    conn = sqlite3.connect(db._path)
    try:
        return [row[0] for row in conn.execute("SELECT state FROM questions WHERE job_id = ?", (job_id,))]
    finally:
        conn.close()


async def _wait_open(registry: AskRegistry, job_id: str) -> None:
    with registry._hub.subscribe({job_id}) as sub:
        while registry.get_pending(job_id) is None:
            sub.clear()
            if registry.get_pending(job_id) is None:
                await sub.wait(2)


# Finding 1: queued-only cancel compare-and-set

@pytest.mark.asyncio
async def test_finding1_queued_cancel_loses_to_runner_start_and_signals_dispatch(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path, start=False)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        job_id = submission.job_id
        dispatch = runtime.scheduler._current[job_id]
        signals = runtime.hub.subscribe({job_id})
        original = runtime.database.job
        fired = False

        def job_then_runner_starts(requested: str):
            nonlocal fired
            view = original(requested)
            if not fired and view is not None and view.state == "queued":
                fired = True
                # The runner wins the queued-to-running transition after cancel read `queued`.
                dispatch.started = True
                runtime.database.start_job(job_id)
            return view

        runtime.database.job = job_then_runner_starts
        assert await runtime.cancel_job(job_id) == "requested"
        runtime.database.job = original
        assert original(job_id).state == "running"
        assert dispatch.cancel_event.is_set()
        assert signals.drain() == []
        signals.__exit__(None, None, None)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_finding1_runner_stops_when_start_cas_fails(tmp_path) -> None:
    class CountingDrivers(FakeDrivers):
        calls = 0

        async def execute(self, **kwargs):
            type(self).calls += 1
            return await super().execute(**kwargs)

    runtime, project = await _runtime(tmp_path, CountingDrivers(), start=False)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        job_id = submission.job_id
        original = runtime.database.start_job

        def cancel_wins_then_start(requested: str):
            runtime.database.finish_job(requested, "cancelled")
            return original(requested)

        runtime.database.start_job = cancel_wins_then_start
        await runtime.runner.run(job_id, CancelEvent())
        assert CountingDrivers.calls == 0
        assert runtime.database.job(job_id).state == "cancelled"
    finally:
        await runtime.close()


# Finding 2: cancellation during the question insert

@pytest.mark.asyncio
async def test_finding2_cancel_during_blocked_insert_leaves_no_open_question(tmp_path) -> None:
    registry, db, _ = _registry(tmp_path)
    token = registry.issue_token("job-1")
    entered, release = threading.Event(), threading.Event()
    original = db.ask_question

    def blocked(*args, **kwargs):
        entered.set()
        release.wait(5)
        return original(*args, **kwargs)

    db.ask_question = blocked
    task = asyncio.create_task(registry.ask(token, "q?", 5))
    await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    await asyncio.sleep(0)  # deliver the cancellation while the insert is still blocked
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert db.open_question("job-1") is None
    assert _states(db, "job-1") == ["expired"]
    db.close()


# Finding 3: terminal publication

@pytest.mark.asyncio
async def test_finding3_terminal_published_when_cancel_caller_is_cancelled_after_write(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path, start=False)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        job_id = submission.job_id
        waiter = asyncio.create_task(runtime.wait_jobs([job_id], 10))
        while runtime.hub.subscriber_count == 0:
            await asyncio.sleep(0)
        entered, release = threading.Event(), threading.Event()
        original = runtime.database.finish_job

        def written_then_blocked(*args, **kwargs):
            changed = original(*args, **kwargs)
            entered.set()
            release.wait(5)
            return changed

        runtime.database.finish_job = written_then_blocked
        canceller = asyncio.create_task(runtime.cancel_job(job_id))
        await asyncio.to_thread(entered.wait, 5)
        canceller.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await canceller
        result = await asyncio.wait_for(waiter, 3)
        assert result.ready
        assert result.job.state == "cancelled"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_finding3_no_terminal_published_for_reserved_dispatch_returning_in_shutdown(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path, start=False)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        job_id = submission.job_id
        signals = runtime.hub.subscribe({job_id})
        runtime._closing = True
        await runtime.scheduler.start()
        await asyncio.gather(*runtime.scheduler._tasks, return_exceptions=True)
        assert runtime.database.job(job_id).state == "queued"
        assert [signal for signal in signals.drain() if signal[1] == "terminal"] == []
        signals.__exit__(None, None, None)
    finally:
        await runtime.close()


# Finding 4: validation, revocation, and registration

@pytest.mark.asyncio
async def test_finding4_revocation_between_validation_and_insert_registers_nothing(tmp_path) -> None:
    registry, db, hub = _registry(tmp_path)
    token = registry.issue_token("job-1")
    original = hub.subscribe
    fired = False

    def subscribe_then_revoke(*args, **kwargs):
        nonlocal fired
        subscription = original(*args, **kwargs)
        if not fired:
            fired = True
            registry.revoke_token("job-1")  # lands after validation and before registration
        return subscription

    hub.subscribe = subscribe_then_revoke
    with pytest.raises(AskAuthError):
        await registry.ask(token, "q?", 5)
    assert _states(db, "job-1") == []
    db.close()


@pytest.mark.asyncio
async def test_finding4_ask_on_finished_job_registers_nothing(tmp_path) -> None:
    registry, db, _ = _registry(tmp_path)
    token = registry.issue_token("job-1")
    assert db.finish_job("job-1", "succeeded")
    with pytest.raises(AskAuthError):
        await registry.ask(token, "q?", 5)
    assert _states(db, "job-1") == []
    db.close()


# Finding 5: late answers

@pytest.mark.asyncio
async def test_finding5_answer_after_deadline_before_expiry_is_rejected(tmp_path) -> None:
    now = [0.0]
    registry, db, _ = _registry(tmp_path, clock=lambda: now[0])
    token = registry.issue_token("job-1")
    task = asyncio.create_task(registry.ask(token, "q?", 10))
    await _wait_open(registry, "job-1")
    now[0] = 11.0  # the deadline has passed; the ask coroutine has not run its expiry yet
    assert registry.deliver_answer("job-1", "late") is False
    assert await asyncio.wait_for(task, 3) == NO_ANSWER_TEXT
    assert _states(db, "job-1") == ["expired"]
    db.close()


@pytest.mark.asyncio
async def test_finding5_runtime_reports_invalid_state_for_late_answer(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path, start=False)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        job_id = submission.job_id
        runtime.database.start_job(job_id)
        now = [0.0]
        registry = runtime.ask_registry
        registry._clock = lambda: now[0]
        token = registry.issue_token(job_id)
        task = asyncio.create_task(registry.ask(token, "q?", 10))
        await _wait_open(registry, job_id)
        now[0] = 11.0
        with pytest.raises(OrchestrationError) as raised:
            await runtime.job_answer(job_id, "late")
        assert raised.value.code == "invalid_state"
        assert await asyncio.wait_for(task, 3) == NO_ANSWER_TEXT
    finally:
        await runtime.close()


# Finding 6: unknown IDs are validated before readiness

@pytest.mark.asyncio
@pytest.mark.parametrize("unknown_first", [False, True])
async def test_finding6_unknown_id_rejected_in_both_orders(tmp_path, unknown_first) -> None:
    runtime, project = await _runtime(tmp_path)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        assert (await runtime.wait(submission.job_id, 10)).state == "succeeded"
        ids = ["missing", submission.job_id] if unknown_first else [submission.job_id, "missing"]
        with pytest.raises(OrchestrationError) as raised:
            await runtime.wait_jobs(ids, 1)
        assert raised.value.code == "unknown_job"
    finally:
        await runtime.close()


# Finding 7: a closing loop must not stop delivery

class _ClosingLoop:
    def __init__(self) -> None:
        self.attempts = 0

    def is_closed(self) -> bool:
        return False

    def call_soon_threadsafe(self, *_args) -> None:
        self.attempts += 1
        raise RuntimeError("Event loop is closed")


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["publish", "wake"])
async def test_finding7_hub_continues_past_a_closing_loop(method) -> None:
    hub = Hub()
    closing_loop = _ClosingLoop()
    with hub.subscribe({"a"}) as dead, hub.subscribe({"a"}) as live:
        dead._loop = closing_loop
        if method == "publish":
            hub.publish("a", "terminal")
        else:
            hub.wake("a")
        assert closing_loop.attempts == 1
        assert await live.wait(1)


@pytest.mark.asyncio
async def test_finding7_cancel_event_continues_past_a_closing_loop() -> None:
    event = CancelEvent()
    closing_loop = _ClosingLoop()
    event._waiters.append((closing_loop, asyncio.Event()))  # type: ignore[arg-type]
    waiter = asyncio.create_task(event.wait_async())
    await asyncio.sleep(0)
    event.set()
    await asyncio.wait_for(waiter, 1)
    assert closing_loop.attempts == 1
    event._waiters.clear()


# Finding 8: DB-bearing calls run on the store executor

@pytest.mark.asyncio
async def test_finding8_from_job_prepare_runs_on_store_executor_when_saturated(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path)
    release = threading.Event()
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        assert (await runtime.wait(submission.job_id, 10)).state == "succeeded"
        threads: list[str] = []
        original = runtime.admission.prepare_from_job

        def recording(*args):
            threads.append(threading.current_thread().name)
            return original(*args)

        runtime.admission.prepare_from_job = recording
        executor = runtime.database.executor
        size = executor._max_workers
        # Park all but one executor thread; the DB work must still finish on the last one.
        blockers = [executor.submit(release.wait, 10) for _ in range(size - 1)]
        retried = await asyncio.wait_for(runtime.submit_from_job(submission.job_id, target="primary"), 5)
        assert retried.state == "queued"
        assert threads and all(name.startswith("refract-db") for name in threads)
        del blockers
    finally:
        release.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_finding8_wait_response_reads_pending_question_on_store_executor(tmp_path) -> None:
    from refract.api.mcp import tools

    runtime, project = await _runtime(tmp_path)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        job = await runtime.wait(submission.job_id, 10)
        threads: list[str] = []
        original = runtime.ask_registry.get_pending

        def recording(job_id: str):
            threads.append(threading.current_thread().name)
            return original(job_id)

        runtime.ask_registry.get_pending = recording
        await tools._job_response(runtime, job)
        assert threads and all(name.startswith("refract-db") for name in threads)
    finally:
        await runtime.close()
