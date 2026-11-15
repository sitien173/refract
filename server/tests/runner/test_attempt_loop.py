"""One test per row of the DESIGN.md attempt table, plus the loop invariants."""

from __future__ import annotations

import pytest

from refract.config import RetryPolicy
from tests.runner.support import FATAL, OK, OVERFLOW, TRANSIENT, ScriptedDrivers, Step, open_circuit, run_job, target

RETRY = RetryPolicy(2, ("rate_limit",), ())


async def _run(tmp_path, drivers, targets, **kwargs):
    runtime, job, rows = await run_job(tmp_path, drivers, targets, **kwargs)
    return runtime, job, rows


@pytest.mark.asyncio
async def test_row1_success_finishes_with_one_initial_attempt(tmp_path) -> None:
    runtime, job, rows = await _run(tmp_path, ScriptedDrivers(OK), (target("a"),))
    try:
        assert job.state == "succeeded"
        assert rows == [("initial", "a", "succeeded", None, 1)]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row2_retry_codes_match_runs_same_target_again(tmp_path) -> None:
    runtime, job, rows = await _run(tmp_path, ScriptedDrivers(TRANSIENT, OK), (target("a", retry=RETRY),))
    try:
        assert job.state == "succeeded"
        assert [(r[0], r[1], r[2]) for r in rows] == [("initial", "a", "failed"), ("retry", "a", "succeeded")]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row2_retry_stops_when_attempts_are_exhausted(tmp_path) -> None:
    drivers = ScriptedDrivers(TRANSIENT, TRANSIENT, TRANSIENT, OK)
    runtime, job, rows = await _run(tmp_path, drivers, (target("a", retry=RETRY),))
    try:
        assert job.state == "failed"
        assert [r[0] for r in rows] == ["initial", "retry", "retry"]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row2_empty_retry_policy_matches_nothing(tmp_path) -> None:
    runtime, job, rows = await _run(
        tmp_path, ScriptedDrivers(TRANSIENT, OK), (target("a", retry=RetryPolicy(2, (), ())), target("b")),
    )
    try:
        assert [(r[0], r[1]) for r in rows] == [("initial", "a"), ("fallback", "b")]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row3_context_overflow_starts_fresh_session(tmp_path) -> None:
    def prepare(runtime, project):
        from refract.runner.planning import target_execution_key
        runtime.database.store_session(
            project_id=project.id, session="s", workflow="implement",
            target_key=target_execution_key(runtime.config.targets[0]), backend_session_id="old",
        )

    drivers = ScriptedDrivers(OVERFLOW, OK)
    runtime, job, rows = await _run(tmp_path, drivers, (target("a"),), prepare=prepare, session="s")
    try:
        assert job.state == "succeeded"
        assert [(r[0], r[3]) for r in rows] == [("initial", "context_overflow"), ("fresh_session", None)]
        assert drivers.calls == [("a", "old"), ("a", "")]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row3_at_most_one_fresh_session_per_job(tmp_path) -> None:
    runtime, job, rows = await _run(tmp_path, ScriptedDrivers(OVERFLOW, OVERFLOW, OK), (target("a"), target("b")))
    try:
        assert job.state == "failed"
        assert [(r[0], r[1]) for r in rows] == [("initial", "a"), ("fresh_session", "a")]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row4_transient_falls_back_to_next_target(tmp_path) -> None:
    runtime, job, rows = await _run(tmp_path, ScriptedDrivers(TRANSIENT, OK), (target("a"), target("b")))
    try:
        assert job.state == "succeeded"
        assert [(r[0], r[1], r[2]) for r in rows] == [("initial", "a", "failed"), ("fallback", "b", "succeeded")]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row4_target_fatal_falls_back_to_next_target(tmp_path) -> None:
    runtime, job, rows = await _run(tmp_path, ScriptedDrivers(FATAL, OK), (target("a"), target("b")))
    try:
        assert [(r[0], r[1], r[3]) for r in rows] == [("initial", "a", "target_fatal"), ("fallback", "b", None)]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row4_fallback_skips_open_circuit_target(tmp_path) -> None:
    a, b, c = target("a"), target("b"), target("c")
    drivers = ScriptedDrivers(TRANSIENT, OK)
    runtime, job, rows = await run_job(tmp_path, drivers, (a, b, c), prepare=lambda rt, _p: open_circuit(rt, b))
    try:
        assert [(r[0], r[1]) for r in rows] == [("initial", "a"), ("fallback", "c")]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row4_never_revisits_a_failed_target(tmp_path) -> None:
    runtime, job, rows = await _run(
        tmp_path, ScriptedDrivers(TRANSIENT, TRANSIENT, TRANSIENT, OK), (target("a"), target("b")),
    )
    try:
        assert job.state == "failed"
        assert [(r[0], r[1]) for r in rows] == [("initial", "a"), ("fallback", "b")]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fresh_session_then_fallback_on_the_same_job(tmp_path) -> None:
    runtime, job, rows = await _run(
        tmp_path, ScriptedDrivers(OVERFLOW, TRANSIENT, OK), (target("a"), target("b")),
    )
    try:
        assert job.state == "succeeded"
        assert [(r[0], r[1]) for r in rows] == [("initial", "a"), ("fresh_session", "a"), ("fallback", "b")]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row5_failure_with_no_recovery_reports_next_target(tmp_path) -> None:
    a, b = target("a"), target("b")
    drivers = ScriptedDrivers(Step(TRANSIENT, tool=True))
    runtime, job, rows = await _run(tmp_path, drivers, (a, b))
    try:
        assert job.state == "failed"
        assert job.result.failure_kind == "transient"
        assert len(rows) == 1
        assert runtime.live_routing(job)["retry"]["next_target"] == "b"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row5_no_next_target_when_none_remains(tmp_path) -> None:
    runtime, job, rows = await _run(tmp_path, ScriptedDrivers(Step(TRANSIENT, tool=True)), (target("a"),))
    try:
        assert job.state == "failed"
        assert runtime.live_routing(job)["retry"]["next_target"] is None
    finally:
        await runtime.close()


def _make_b_sticky(runtime, project) -> None:
    from refract.store import sessions
    with runtime.database._connection:
        sessions.set_sticky_target(runtime.database._connection, project.id, "s", "implement", "b")


@pytest.mark.asyncio
async def test_row5_next_target_follows_the_sticky_routing_order(tmp_path) -> None:
    drivers = ScriptedDrivers(Step(TRANSIENT, tool=True))
    runtime, job, rows = await _run(
        tmp_path, drivers, (target("a"), target("b")), prepare=_make_b_sticky, session="s",
    )
    try:
        assert job.state == "failed"
        assert [(r[0], r[1]) for r in rows] == [("initial", "b")]
        assert job.result.next_target == "a"
        assert runtime.live_routing(job)["retry"]["next_target"] == "a"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_row5_reported_next_target_ignores_a_config_change_after_submission(tmp_path) -> None:
    from dataclasses import replace
    from refract.config import TargetSelection

    runtime, job, rows = await _run(
        tmp_path, ScriptedDrivers(Step(TRANSIENT, tool=True)), (target("a"), target("b")),
    )
    try:
        assert runtime.live_routing(job)["retry"]["next_target"] == "b"
        reordered = TargetSelection(("b", "a"))
        runtime.catalogs.current = replace(runtime.catalogs.current, profiles={"balanced": {
            name: reordered for name in ("implement", "review", "consult", "other")}})
        again = runtime.database.job(job.id)
        assert runtime.live_routing(again)["retry"]["next_target"] == "b"
        assert again.result.next_target == "b"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_each_attempt_releases_target_capacity_before_the_next(tmp_path) -> None:
    class Probe(ScriptedDrivers):
        active: list[int] = []

        async def execute(self, *, target, **kwargs):
            self.active.append(self.runtime.target_executor._target_active.get(target.id, 0))
            return await super().execute(target=target, **kwargs)

    drivers = Probe(TRANSIENT, OK)
    drivers.active = []
    runtime, job, rows = await _run(tmp_path, drivers, (target("a", retry=RETRY),))
    try:
        assert job.state == "succeeded"
        assert drivers.active == [1, 1]
        assert runtime.target_executor._target_active == {}
    finally:
        await runtime.close()
