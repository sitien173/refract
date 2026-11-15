"""Replay safety and the next-step table of the attempt loop.

An attempt is replay safe, so the server may run it again on its own, only when all three hold:

1. The target streams events, so the runner can see whether the worker ran a tool.
2. No `tool.started` event occurred.
3. The worker asked no question during the attempt. The `questions.attempt_id` column records which attempt
   asked, so the rule reads the DB instead of in-memory state.

Streaming is decided per attempt by the library capability probe (`DriverRegistry.supports_structured_streaming`),
never by backend name. A target whose probe fails is not consumed for events, so the runner cannot prove that no tool
ran, and it is never re-run automatically. The built-in drivers `claude`, `codex`, `pi`, and `agy` all pass the probe
when their CLI prints the markers the driver checks in `--help`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from refract.config import RetryPolicy

type Reason = Literal["retry", "fresh_session", "fallback"]


def replay_safe(*, streams: bool, tool_started: bool, asked_question: bool) -> bool:
    return streams and not tool_started and not asked_question


def matches_retry_policy(policy: RetryPolicy, error_code: str, error: str) -> bool:
    """A failure matches by `retry.codes` or by a `retry.patterns` substring; a policy with neither matches nothing."""
    if error_code and error_code in policy.codes:
        return True
    text = error.lower()
    return bool(text) and any(pattern.lower() in text for pattern in policy.patterns)


@dataclass(slots=True, frozen=True)
class Attempt:
    """The facts of a finished attempt that the next-step table reads."""

    outcome: str
    failure_kind: str | None
    error_code: str
    error: str
    replay_safe: bool


def next_step(
    attempt: Attempt, *, policy: RetryPolicy, retries_done: int, fresh_used: bool, target_remains: bool,
    cancelled: bool,
) -> Reason | None:
    """The first matching row of the DESIGN.md attempt table, or None to finish the job."""
    if cancelled or attempt.outcome == "SUCCESS" or not attempt.replay_safe:
        return None
    if retries_done < policy.attempts and matches_retry_policy(policy, attempt.error_code, attempt.error):
        return "retry"
    if attempt.failure_kind == "context_overflow" and not fresh_used:
        return "fresh_session"
    if attempt.failure_kind in {"transient", "target_fatal"} and target_remains:
        return "fallback"
    return None
