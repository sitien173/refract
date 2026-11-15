"""The three replay_safe conditions, alone and on every automatic re-run path."""

from __future__ import annotations

import pytest

from refract.config import RetryPolicy
from refract.runner.replay import Attempt, matches_retry_policy, next_step, replay_safe
from tests.runner.support import OK, OVERFLOW, TRANSIENT, ScriptedDrivers, Step, run_job, target

RETRY = RetryPolicy(2, ("rate_limit",), ())


def test_replay_safe_needs_all_three_conditions() -> None:
    assert replay_safe(streams=True, tool_started=False, asked_question=False)
    assert not replay_safe(streams=False, tool_started=False, asked_question=False)
    assert not replay_safe(streams=True, tool_started=True, asked_question=False)
    assert not replay_safe(streams=True, tool_started=False, asked_question=True)


def test_retry_policy_matches_code_or_pattern_only() -> None:
    policy = RetryPolicy(1, ("rate_limit",), ("Overloaded",))
    assert matches_retry_policy(policy, "rate_limit", "")
    assert matches_retry_policy(policy, "other", "server is overloaded")
    assert not matches_retry_policy(policy, "other", "boom")
    assert not matches_retry_policy(RetryPolicy(1, (), ()), "rate_limit", "overloaded")


@pytest.mark.parametrize("kind,outcome", [("transient", "RETRYABLE"), ("target_fatal", "TARGET_FATAL")])
def test_next_step_never_reruns_an_unsafe_attempt(kind: str, outcome: str) -> None:
    unsafe = Attempt(outcome, kind, "rate_limit", "", False)
    for fresh_used in (False, True):
        assert next_step(unsafe, policy=RETRY, retries_done=0, fresh_used=fresh_used, target_remains=True, cancelled=False) is None
    unsafe_overflow = Attempt("RETRYABLE", "context_overflow", "context_overflow", "", False)
    assert next_step(unsafe_overflow, policy=RETRY, retries_done=0, fresh_used=False, target_remains=True, cancelled=False) is None


def test_next_step_order_is_retry_then_fresh_then_fallback() -> None:
    safe = Attempt("RETRYABLE", "transient", "rate_limit", "", True)
    kwargs = {"fresh_used": False, "target_remains": True, "cancelled": False}
    assert next_step(safe, policy=RETRY, retries_done=0, **kwargs) == "retry"
    assert next_step(safe, policy=RETRY, retries_done=2, **kwargs) == "fallback"
    overflow = Attempt("RETRYABLE", "context_overflow", "context_overflow", "", True)
    assert next_step(overflow, policy=RetryPolicy(2, ("context_overflow",), ()), retries_done=0, **kwargs) == "retry"
    assert next_step(overflow, policy=RETRY, retries_done=0, **kwargs) == "fresh_session"
    assert next_step(overflow, policy=RETRY, retries_done=0, fresh_used=True, target_remains=True, cancelled=False) is None
    assert next_step(safe, policy=RETRY, retries_done=0, fresh_used=False, target_remains=True, cancelled=True) is None


PATHS = {
    "retry": ((target("a", retry=RETRY),), TRANSIENT),
    "fresh_session": ((target("a"), target("b")), OVERFLOW),
    "fallback": ((target("a"), target("b")), TRANSIENT),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", sorted(PATHS))
@pytest.mark.parametrize("condition", ["tool_started", "question", "non_streaming"])
async def test_no_automatic_rerun_on_any_path_when_a_condition_fails(tmp_path, path: str, condition: str) -> None:
    targets, failure = PATHS[path]
    failing_probe = tuple(t.id for t in targets) if condition == "non_streaming" else ()
    step = Step(failure, tool=condition == "tool_started", ask=condition == "question")
    runtime, job, rows = await run_job(tmp_path, ScriptedDrivers(step, OK, probe_fails=failing_probe), targets)
    try:
        assert job.state == "failed"
        assert [(r[0], r[4]) for r in rows] == [("initial", 0)]
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["claude", "codex", "pi", "agy"])
async def test_replay_safe_follows_a_passing_probe_for_any_backend(tmp_path, backend: str) -> None:
    runtime, job, rows = await run_job(
        tmp_path, ScriptedDrivers(TRANSIENT, OK), (target("a", backend=backend), target("b", backend=backend)),
    )
    try:
        assert job.state == "succeeded"
        assert [(r[0], r[1], r[4]) for r in rows] == [("initial", "a", 1), ("fallback", "b", 1)]
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["claude", "codex", "pi", "agy"])
async def test_built_in_target_with_a_failing_probe_is_unsafe_and_never_rerun(tmp_path, backend: str) -> None:
    drivers = ScriptedDrivers(TRANSIENT, OK, probe_fails=("a",))
    runtime, job, rows = await run_job(
        tmp_path, drivers, (target("a", backend=backend, retry=RETRY), target("b", backend=backend)),
    )
    try:
        assert job.state == "failed"
        assert [(r[0], r[1], r[4]) for r in rows] == [("initial", "a", 0)]
        assert drivers.calls == [("a", "")]
    finally:
        await runtime.close()


@pytest.mark.parametrize("kind,outcome,code", [
    ("context_overflow", "RETRYABLE", "context_overflow"), ("target_fatal", "TARGET_FATAL", "rate_limit"),
])
def test_matching_retry_code_wins_over_fresh_session_and_fallback(kind: str, outcome: str, code: str) -> None:
    attempt = Attempt(outcome, kind, code, "", True)
    policy = RetryPolicy(1, (code,), ())
    kwargs = {"fresh_used": False, "target_remains": True, "cancelled": False}
    assert next_step(attempt, policy=policy, retries_done=0, **kwargs) == "retry"
    expected = "fresh_session" if kind == "context_overflow" else "fallback"
    assert next_step(attempt, policy=policy, retries_done=1, **kwargs) == expected
