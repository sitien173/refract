from __future__ import annotations

import json

import pytest

from openmcp.database import Database
from openmcp.drivers import DriverResult
from openmcp.planning import execution_plan_data, resolve_execution_plan
from openmcp.runtime import OrchestrationError, Runtime
from openmcp.workflows import get_workflow
from tests.orchestration_helpers import BlockingDrivers, FakeDrivers, config, git, repository


@pytest.mark.asyncio
async def test_implement_commits_directly(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(project.id, "implement", "create the result", commit_message="feat: add result")
        job = await runtime.wait(submission.job_id, 10)
        assert job.state == "succeeded"
        assert (root / "result.txt").exists()
        assert git(root, "log", "-1", "--format=%s") == "feat: add result"
        assert job.result.commit == git(root, "rev-parse", "HEAD")
        assert "stages" not in job.model_dump()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_implement_without_changes_keeps_head(tmp_path) -> None:
    root = repository(tmp_path)
    baseline = git(root, "rev-parse", "HEAD")
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect only")).job_id, 10)
        assert job.state == "succeeded" and job.result.commit == baseline
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow", ["review", "consult"])
async def test_read_workflows_leave_repository_unchanged(tmp_path, workflow) -> None:
    root = repository(tmp_path)
    baseline = git(root, "rev-parse", "HEAD")
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, workflow, "inspect")).job_id, 10)
        assert job.state == "succeeded" and job.result.commit == baseline
        assert git(root, "status", "--porcelain") == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_mutating_review_is_reset_and_failed(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "review", "review")).job_id, 10)
        assert job.state == "failed" and "modified the repository" in job.result.error
        assert not (root / "result.txt").exists()
    finally:
        await runtime.close()


class MutatingFailureDrivers(FakeDrivers):
    async def execute(self, *, cwd, **kwargs) -> DriverResult:
        (cwd / "README.md").write_text("agent change\n", encoding="utf-8")
        (cwd / "partial.txt").write_text("partial\n", encoding="utf-8")
        return DriverResult("RETRYABLE", "", "", "target failed", "backend_failure")


@pytest.mark.asyncio
async def test_failed_execution_resets_changes_and_preserves_dirty_preflight(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = MutatingFailureDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "implement", "change")).job_id, 10)
        assert job.state == "failed"
        assert (root / "README.md").read_text(encoding="utf-8") == "baseline\n"
        assert not (root / "partial.txt").exists()
        (root / "README.md").write_text("operator change\n", encoding="utf-8")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "change")).job_id, 10)
        assert job.state == "failed"
        assert (root / "README.md").read_text(encoding="utf-8") == "operator change\n"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_queued_and_running_cancellation(tmp_path) -> None:
    root = repository(tmp_path)
    drivers = BlockingDrivers()
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        first = await runtime.submit(project.id, "implement", "block")
        second = await runtime.submit(project.id, "review", "never run")
        await drivers.started.wait()
        assert runtime.cancel(second.job_id).state == "cancelled"
        assert runtime.cancel(first.job_id).state == "running"
        assert (await runtime.wait(first.job_id, 10)).state == "cancelled"
        assert (await runtime.wait(second.job_id, 10)).state == "cancelled"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_startup_recovers_persisted_running_job(tmp_path) -> None:
    root = repository(tmp_path)
    home = tmp_path / "home"
    catalog = config(home)
    database = Database(catalog.database_path)
    project = database.upsert_project(project_id="project", alias="project", root=root.as_posix(), head_commit=git(root, "rev-parse", "HEAD"), clean=True)
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    database.create_job(job_id="running", project_id=project.id, workflow="implement", profile="balanced", prompt="change", commit_message="", execution_plan_json=json.dumps(execution_plan_data(plan)), context_key="implement")
    database.start_job("running", git(root, "rev-parse", "HEAD"))
    (root / "partial.txt").write_text("partial\n", encoding="utf-8")
    database.close()
    runtime = Runtime(catalog)
    await runtime.start()
    try:
        recovered = runtime.database.job("running")
        assert recovered and recovered.state == "interrupted"
        assert not (root / "partial.txt").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_registration_and_execution_reject_detached_head(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    git(root, "checkout", "--detach")
    with pytest.raises(OrchestrationError, match="attached branch"):
        runtime.register_project(str(root))
    runtime.database.close()
