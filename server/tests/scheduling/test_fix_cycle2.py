"""Fix cycle 2: deterministic reproductions of the re-review findings, forced with events and injected hooks."""

from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import contextmanager

import pytest

from refract.scheduling.asks import NO_ANSWER_TEXT, AskAuthError
from tests.scheduling.test_fix_cycle1 import _registry, _runtime, _states, _wait_open


@contextmanager
def _watchdog(release: threading.Event, after_s: float = 3):
    """Free a blocked DB call if the loop-side call under test never returns, so a regression fails instead of hanging."""
    timer = threading.Timer(after_s, release.set)
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
        release.set()


# Finding R1: the event loop never waits on a lock held across DB work

@pytest.mark.asyncio
async def test_r1_revoke_token_does_not_wait_for_blocked_registration(tmp_path) -> None:
    registry, db, _ = _registry(tmp_path)
    token = registry.issue_token("job-1")
    entered, release = threading.Event(), threading.Event()
    original = db.ask_question

    def blocked(*args, **kwargs):
        entered.set()
        release.wait(10)
        return original(*args, **kwargs)

    db.ask_question = blocked
    with _watchdog(release):
        task = asyncio.create_task(registry.ask(token, "q?", 5))
        await asyncio.to_thread(entered.wait, 5)
        registry.revoke_token("job-1")  # runs on the loop, as `cancel_job` does
        assert not release.is_set(), "revoke_token waited for the blocked registration"
        release.set()
        with pytest.raises(AskAuthError):
            await task
    assert db.open_question("job-1") is None  # no question stays registered under the revoked token
    assert _states(db, "job-1") == ["expired"]
    db.close()


@pytest.mark.asyncio
async def test_r1_cancel_job_does_not_wait_for_blocked_answer_delivery(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path, start=False)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        job_id = submission.job_id
        runtime.database.start_job(job_id)
        registry = runtime.ask_registry
        token = registry.issue_token(job_id)
        asker = asyncio.create_task(registry.ask(token, "q?", 30))
        await _wait_open(registry, job_id)
        entered, release = threading.Event(), threading.Event()
        original = runtime.database.answer_question

        def blocked(*args, **kwargs):
            entered.set()
            release.wait(10)
            return original(*args, **kwargs)

        runtime.database.answer_question = blocked
        with _watchdog(release):
            answerer = asyncio.create_task(runtime.job_answer(job_id, "yes"))
            await asyncio.to_thread(entered.wait, 5)
            await runtime.cancel_job(job_id)
            assert not release.is_set(), "cancel_job waited for the blocked answer delivery"
            release.set()
            await answerer
            await asyncio.wait_for(asker, 3)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_r1_ask_wait_loop_does_not_wait_for_blocked_answer_delivery(tmp_path) -> None:
    registry, db, hub = _registry(tmp_path)
    token = registry.issue_token("job-1")
    asker = asyncio.create_task(registry.ask(token, "q?", 30))
    await _wait_open(registry, "job-1")
    entered, release = threading.Event(), threading.Event()
    original = db.answer_question

    def blocked(*args, **kwargs):
        entered.set()
        release.wait(10)
        return original(*args, **kwargs)

    db.answer_question = blocked
    revoked_seen = threading.Event()
    original_token_is = registry._token_is

    def token_is(job_id, bound):
        current = original_token_is(job_id, bound)
        if not current:
            revoked_seen.set()
        return current

    registry._token_is = token_is
    with _watchdog(release):
        answerer = asyncio.create_task(asyncio.to_thread(registry.deliver_answer, "job-1", "yes"))
        await asyncio.to_thread(entered.wait, 5)
        registry.revoke_token("job-1")  # wakes the ask, whose revoked check runs on the loop
        await asyncio.to_thread(revoked_seen.wait, 3)  # explicit checkpoint: the wait loop saw the revocation
        assert revoked_seen.is_set() and not release.is_set(), "the ask wait loop waited for the blocked answer delivery"
        release.set()
        await answerer
        await asker
    db.close()


@pytest.mark.asyncio
async def test_r1_answer_paused_before_token_check_is_rejected_after_revocation(tmp_path) -> None:
    registry, db, _ = _registry(tmp_path)
    token = registry.issue_token("job-1")
    asker = asyncio.create_task(registry.ask(token, "q?", 30))
    await _wait_open(registry, "job-1")
    entered, release = threading.Event(), threading.Event()
    original = db.open_question

    def paused_after_lookup(job_id):
        row = original(job_id)
        entered.set()
        release.wait(10)
        return row

    db.open_question = paused_after_lookup
    with _watchdog(release):
        answerer = asyncio.create_task(asyncio.to_thread(registry.deliver_answer, "job-1", "late"))
        await asyncio.to_thread(entered.wait, 5)
        registry.revoke_token("job-1")  # runs to completion while the answer is paused before its token check
        assert not release.is_set(), "revoke_token waited for the paused answer delivery"
        db.open_question = original
        release.set()
        assert await answerer is False
        assert await asyncio.wait_for(asker, 3) == NO_ANSWER_TEXT
    assert db.open_question("job-1") is None
    assert _states(db, "job-1") == ["expired"]
    db.close()


# Finding R2: the CAS-loss signal belongs to the detached cancel operation

@pytest.mark.asyncio
async def test_r2_cancelled_caller_still_signals_dispatch_when_runner_wins_start_cas(tmp_path) -> None:
    runtime, project = await _runtime(tmp_path, start=False)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        job_id = submission.job_id
        dispatch = runtime.scheduler._current[job_id]
        entered, release = threading.Event(), threading.Event()
        original = runtime.database.finish_job

        def runner_starts_then_cas_runs(*args, **kwargs):
            dispatch.started = True
            runtime.database.start_job(job_id)  # the runner wins the queued-to-running transition
            entered.set()
            release.wait(5)
            return original(*args, **kwargs)

        runtime.database.finish_job = runner_starts_then_cas_runs
        caller = asyncio.create_task(runtime.cancel_job(job_id))
        await asyncio.to_thread(entered.wait, 5)
        caller.cancel()
        await asyncio.sleep(0)  # deliver the cancellation while the queued-only CAS is blocked
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await caller
        await asyncio.gather(*runtime.canceller.tasks, return_exceptions=True)
        runtime.database.finish_job = original
        assert runtime.database.job(job_id).state == "running"
        assert dispatch.cancel_event.is_set()
    finally:
        await runtime.close()


# Finding R3: expiry and deadline removal are one step

@pytest.mark.asyncio
async def test_r3_late_answer_in_cancelled_insert_cleanup_is_rejected(tmp_path) -> None:
    now = [0.0]
    registry, db, _ = _registry(tmp_path, clock=lambda: now[0])
    token = registry.issue_token("job-1")
    entered, release = threading.Event(), threading.Event()
    original = db.ask_question

    def blocked(*args, **kwargs):
        entered.set()
        release.wait(5)
        return original(*args, **kwargs)

    db.ask_question = blocked
    task = asyncio.create_task(registry.ask(token, "q?", 10))
    await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    await asyncio.sleep(0)  # deliver the cancellation while the insert is still blocked
    now[0] = 11.0  # the deadline passes before the cancelled ask cleans up
    outcomes: list[bool] = []
    expire = registry._expire

    def answer_then_expire(question_id: int) -> bool:
        outcomes.append(registry.deliver_answer("job-1", "late"))  # lands between insert completion and cleanup
        return expire(question_id)

    registry._expire = answer_then_expire
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert outcomes == [False]
    assert _states(db, "job-1") == ["expired"]
    assert not registry._deadlines
    db.close()


# Non-blocking: detached cancel task failures are logged

@pytest.mark.asyncio
async def test_detached_cancel_task_exception_is_logged(tmp_path, caplog) -> None:
    runtime, project = await _runtime(tmp_path, start=False)
    try:
        submission = await runtime.submit(project.id, "implement", "inspect")
        job_id = submission.job_id
        entered, release = threading.Event(), threading.Event()

        def failing(*args, **kwargs):
            entered.set()
            release.wait(5)
            raise RuntimeError("boom")

        runtime.database.finish_job = failing
        caller = asyncio.create_task(runtime.cancel_job(job_id))
        await asyncio.to_thread(entered.wait, 5)
        caller.cancel()
        await asyncio.sleep(0)
        with caplog.at_level(logging.ERROR):
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await caller
            await asyncio.gather(*runtime.canceller.tasks, return_exceptions=True)
            await asyncio.sleep(0)  # let the done callbacks run
        records = [r for r in caplog.records if getattr(r, "event", "") == "cancel.task_failed"]
        assert len(records) == 1
        assert records[0].exc_info is not None and "boom" in str(records[0].exc_info[1])
    finally:
        await runtime.close()


# Final re-review: an answer that arrives after revocation never wins

@pytest.mark.asyncio
async def test_answer_after_revocation_is_rejected_before_the_ask_expires_its_question(tmp_path) -> None:
    registry, db, _ = _registry(tmp_path)
    token = registry.issue_token("job-1")
    asker = asyncio.create_task(registry.ask(token, "q?", 30))
    await _wait_open(registry, "job-1")
    registry.revoke_token("job-1")
    # No await in between: the ask has not run its revoked check, so the question row is still open.
    assert db.open_question("job-1") is not None
    assert registry.deliver_answer("job-1", "yes") is False
    assert _states(db, "job-1") == ["expired"]
    assert await asyncio.wait_for(asker, 3) == NO_ANSWER_TEXT
    db.close()
