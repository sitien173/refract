"""Every attempt owns the half-open probe it runs under."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from refract.config import RetryPolicy, TargetSelection
from refract.runner.planning import target_execution_key
from refract.runtime import Runtime
from tests.orchestration_helpers import config, register_project, repository
from tests.runner.support import FATAL, OK, TRANSIENT, ScriptedDrivers, run_job, target

RETRY = RetryPolicy(1, ("rate_limit",), ())
PAST = "2000-01-01T00:00:00+00:00"


def _half_open(runtime, tgt) -> str:
    key = target_execution_key(tgt)
    with runtime.database._connection:
        runtime.database._connection.execute(
            "INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) "
            "VALUES (?, 1, ?, 60, '')", (key, PAST),
        )
    return key


def _claim(runtime, key: str, job_id: str) -> bool:
    return runtime.database.claim_target_probe(key, job_id, datetime.now(timezone.utc).isoformat())


class _Observing(ScriptedDrivers):
    """Records the probe owner and a rival claim during each attempt."""

    key = ""

    async def execute(self, **kwargs):
        health = self.runtime.database.target_health(self.key)
        self.owners = [*getattr(self, "owners", []), health["probe_job_id"]]
        self.rival = [*getattr(self, "rival", []), _claim(self.runtime, self.key, "rival-job")]
        return await super().execute(**kwargs)


@pytest.mark.asyncio
async def test_a_second_job_cannot_claim_the_probe_during_a_retry(tmp_path) -> None:
    a = target("a", retry=RETRY)
    drivers = _Observing(TRANSIENT, OK)
    drivers.key = target_execution_key(a)

    runtime, job, rows = await run_job(tmp_path, drivers, (a,), prepare=lambda rt, _p: _half_open(rt, a))
    try:
        assert job.state == "succeeded"
        assert [r[0] for r in rows] == ["initial", "retry"]
        assert drivers.owners == [job.id, job.id]
        assert drivers.rival == [False, False]
        assert runtime.database.target_health(drivers.key)["probe_job_id"] == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_is_not_run_when_another_job_took_the_probe_between_attempts(tmp_path) -> None:
    a, b = target("a", retry=RETRY), target("b")
    key = target_execution_key(a)

    drivers = ScriptedDrivers(TRANSIENT, OK)
    runtime, job, rows = await run_job(
        tmp_path, drivers, (a, b), prepare=lambda rt, _p: _steal_after_release(rt, key),
    )
    try:
        assert job.state == "succeeded"
        assert [(r[0], r[1]) for r in rows] == [("initial", "a"), ("fallback", "b")]
        assert [call[0] for call in drivers.calls] == ["a", "b"]
    finally:
        await runtime.close()


def _steal_after_release(runtime, tgt_key: str, rival: str = "rival-job") -> None:
    """Half-open the target, and hand the probe to a rival the moment the first attempt releases it."""
    with runtime.database._connection:
        runtime.database._connection.execute(
            "INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) "
            "VALUES (?, 1, ?, 60, '')", (tgt_key, PAST),
        )
    original = runtime.target_executor._release_probe

    async def release_then_steal(target_key: str, job_id: str) -> None:
        await original(target_key, job_id)
        if target_key == tgt_key and not getattr(release_then_steal, "done", False):
            release_then_steal.done = True
            assert _claim(runtime, tgt_key, rival)

    runtime.target_executor._release_probe = release_then_steal


@pytest.mark.asyncio
async def test_retry_with_no_fallback_finishes_when_the_probe_is_gone(tmp_path) -> None:
    a = target("a", retry=RETRY)
    key = target_execution_key(a)
    drivers = ScriptedDrivers(TRANSIENT, OK)
    runtime, job, rows = await run_job(tmp_path, drivers, (a,), prepare=lambda rt, _p: _steal_after_release(rt, key))
    try:
        assert job.state == "failed"
        assert [r[0] for r in rows] == ["initial"]
        assert len(drivers.calls) == 1
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_a_failed_readmission_keeps_the_probe_of_a_running_rival(tmp_path) -> None:
    a = target("a", retry=RETRY)
    key = target_execution_key(a)
    drivers = ScriptedDrivers(TRANSIENT, OK)
    runtime, job, rows = await run_job(tmp_path, drivers, (a,), prepare=lambda rt, _p: _steal_after_release(rt, key))
    try:
        # Rival B claimed the probe when A released it, and is still running: A has finished.
        assert job.state == "failed"
        assert [r[0] for r in rows] == ["initial"]
        assert runtime.database.target_health(key)["probe_job_id"] == "rival-job"
        assert not _claim(runtime, key, "job-c")
        assert runtime.target_executor.readmit_target(a, None, "job-c") == (False, False)
        assert runtime.database.target_health(key)["probe_job_id"] == "rival-job"
        runtime.database.release_target_probe(key, "rival-job")
        assert runtime.database.target_health(key)["probe_job_id"] == ""
    finally:
        await runtime.close()


class _Gated(ScriptedDrivers):
    """Call 1 (job A) and call 2 (job B) each wait on their own gate inside the driver."""

    def __init__(self, a_result, b_result) -> None:
        super().__init__()
        self.results = [a_result, b_result]
        self.entered = [asyncio.Event(), asyncio.Event()]
        self.gates = [asyncio.Event(), asyncio.Event()]

    async def execute(self, *, target, session_id, **kwargs):
        index = len(self.calls)
        self.calls.append((target.id, session_id))
        self.entered[index].set()
        await self.gates[index].wait()
        return self.results[index]


@pytest.mark.asyncio
async def test_a_running_rival_job_keeps_its_probe_when_the_other_job_fails(tmp_path) -> None:
    a = replace(target("a", retry=RETRY), max_concurrency=2)
    key = target_execution_key(a)
    drivers = _Gated(FATAL, OK)
    selection = TargetSelection((a.id,))
    catalog = replace(
        config(tmp_path / "home"), targets=(a,),
        profiles={"balanced": {name: selection for name in ("implement", "review", "consult", "other")}},
    )
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    drivers.database = runtime.database
    drivers.runtime = runtime
    await runtime.start()
    try:
        project = register_project(runtime, str(repository(tmp_path)))
        job_a = (await runtime.submit(project.id, "implement", "a", session="session-a")).job_id
        await asyncio.wait_for(drivers.entered[0].wait(), 10)

        # The circuit becomes half-open while A runs, so B takes the probe and A does not hold it.
        _half_open(runtime, a)
        job_b = (await runtime.submit(project.id, "implement", "b", session="session-b")).job_id
        await asyncio.wait_for(drivers.entered[1].wait(), 10)
        assert runtime.database.target_health(key)["probe_job_id"] == job_b

        drivers.gates[0].set()
        failed = await runtime.wait(job_a, 10)
        assert failed.state == "failed"
        health = runtime.database.target_health(key)
        assert health["circuit_open_until"] > datetime.now(timezone.utc).isoformat()
        assert health["probe_job_id"] == job_b
        assert runtime.database.job(job_b).state == "running"

        drivers.gates[1].set()
        assert (await runtime.wait(job_b, 10)).state == "succeeded"
        health = runtime.database.target_health(key)
        assert (health["probe_job_id"], health["circuit_open_until"]) == ("", "")
    finally:
        drivers.gates[0].set()
        drivers.gates[1].set()
        await runtime.close()
