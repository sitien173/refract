"""The session lock is held for a whole job, across targets."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from refract.config import TargetConfig
from refract.runner.drivers import DriverResult
from refract.runtime import Runtime
from tests.orchestration_helpers import FakeDrivers, config, register_project, repository


@pytest.mark.asyncio
async def test_same_session_jobs_serialize_across_targets_and_second_stays_queued(tmp_path):
    root = repository(tmp_path)
    targets = (TargetConfig(id="one", backend="codex"), TargetConfig(id="two", backend="codex"))
    catalog = replace(config(tmp_path / "home", targets), max_jobs=3)
    entered: list[tuple[str, str]] = []
    first_running = asyncio.Event()
    release = asyncio.Event()

    class GateDrivers(FakeDrivers):
        async def execute(self, *, target, prompt, **kwargs):
            entered.append((prompt, target.id))
            first_running.set()
            await release.wait()
            return DriverResult("SUCCESS", "sid", "done", "", "")

    runtime = Runtime(catalog)
    runtime.drivers = GateDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        first = await runtime.submit(project.id, "consult", "first", session="s")
        await asyncio.wait_for(first_running.wait(), 10)
        second = await runtime.submit(project.id, "consult", "second", session="s")
        await asyncio.sleep(0.3)
        record = runtime.database.job(second.job_id)
        assert record.state == "queued"
        assert [prompt for prompt, _ in entered] == ["first"]
        assert runtime.database.job_attempts(second.job_id) == []
        release.set()
        for submission in (first, second):
            assert (await runtime.wait(submission.job_id, 10)).state == "succeeded"
        assert [prompt for prompt, _ in entered] == ["first", "second"]
        assert runtime.target_executor._session_locks == {}
        assert runtime.target_executor._session_users == {}
    finally:
        release.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_of_job_waiting_on_session_terminates_and_frees_lock(tmp_path):
    root = repository(tmp_path)
    targets = (TargetConfig(id="one", backend="codex"), TargetConfig(id="two", backend="codex"))
    catalog = replace(config(tmp_path / "home", targets), max_jobs=3)
    first_running = asyncio.Event()
    release = asyncio.Event()

    class GateDrivers(FakeDrivers):
        async def execute(self, **kwargs):
            first_running.set()
            await release.wait()
            return DriverResult("SUCCESS", "sid", "done", "", "")

    runtime = Runtime(catalog)
    runtime.drivers = GateDrivers()
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        first = await runtime.submit(project.id, "consult", "first", session="s")
        await asyncio.wait_for(first_running.wait(), 10)
        second = await runtime.submit(project.id, "consult", "second", session="s")
        await asyncio.sleep(0.2)
        assert await runtime.cancel_job(second.job_id) == "terminated"
        assert runtime.database.job(second.job_id).state == "cancelled"
        release.set()
        assert (await runtime.wait(first.job_id, 10)).state == "succeeded"
        await asyncio.sleep(0.2)
        assert runtime.target_executor._session_users == {}
    finally:
        release.set()
        await runtime.close()
