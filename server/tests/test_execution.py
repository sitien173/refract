from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import replace

import pytest

from openmcp.config import TargetSelection
from openmcp.database import Database
from openmcp.drivers import DriverResult
from openmcp.planning import execution_plan_data, resolve_execution_plan
from openmcp.runtime import OrchestrationError, Runtime
from openmcp.workflows import get_workflow
from tests.orchestration_helpers import BlockingDrivers, FakeDrivers, config, git, repository


@pytest.mark.asyncio
async def test_implement_succeeds_with_dirty_worktree_and_leaves_changes(tmp_path) -> None:
    root = repository(tmp_path)
    baseline = git(root, "rev-parse", "HEAD")
    (root / "README.md").write_text("dirty\n", encoding="utf-8")
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(project.id, "implement", "create the result", commit_message="ignored")
        job = await runtime.wait(submission.job_id, 10)
        assert job.state == "succeeded"
        assert (root / "result.txt").exists()
        assert (root / "README.md").read_text(encoding="utf-8") == "dirty\n"
        assert git(root, "rev-parse", "HEAD") == baseline
        assert job.base_commit == ""
        assert job.result.commit == ""
        assert "stages" not in job.model_dump()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_implement_without_changes_uses_empty_result_placeholder(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "implement", "inspect only")).job_id, 10)
        assert job.state == "succeeded" and job.result.commit == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow", ["review", "consult"])
async def test_read_workflows_store_empty_commit_placeholder(tmp_path, workflow) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, workflow, "inspect")).job_id, 10)
        assert job.state == "succeeded" and job.result.commit == ""
        assert git(root, "status", "--porcelain") == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_mutating_review_succeeds_and_leaves_changes(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "review", "review")).job_id, 10)
        assert job.state == "succeeded" and job.result.commit == ""
        assert (root / "result.txt").exists()
    finally:
        await runtime.close()


class MutatingFailureDrivers(FakeDrivers):
    async def execute(self, *, cwd, **kwargs) -> DriverResult:
        (cwd / "README.md").write_text("agent change\n", encoding="utf-8")
        (cwd / "partial.txt").write_text("partial\n", encoding="utf-8")
        return DriverResult("RETRYABLE", "", "", "target failed", "backend_failure")


class RetryDrivers(FakeDrivers):
    def __init__(self) -> None:
        super().__init__({"primary": "RETRYABLE"})
        self.started = asyncio.Event()
        self.calls = 0

    async def execute(self, **kwargs) -> DriverResult:
        self.calls += 1
        self.started.set()
        return DriverResult("RETRYABLE", "", "", "retry", "backend_failure")


@pytest.mark.asyncio
async def test_failed_execution_leaves_changes_and_preserves_dirty_preflight(tmp_path) -> None:
    root = repository(tmp_path)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = MutatingFailureDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "implement", "change")).job_id, 10)
        assert job.state == "failed"
        assert (root / "README.md").read_text(encoding="utf-8") == "agent change\n"
        assert (root / "partial.txt").exists()
        (root / "README.md").write_text("operator change\n", encoding="utf-8")
        job = await runtime.wait((await runtime.submit(project.id, "implement", "change")).job_id, 10)
        assert job.state == "failed"
        assert (root / "README.md").read_text(encoding="utf-8") == "agent change\n"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retries_reuse_targets_after_each_failover_pass(tmp_path, monkeypatch) -> None:
    root = repository(tmp_path)
    selection = TargetSelection(("primary",), 2)
    catalog = replace(
        config(tmp_path / "home"),
        profiles={
            "balanced": {
                "implement": selection,
                "review": selection,
                "consult": selection,
            }
        },
    )
    runtime = Runtime(catalog)
    runtime.drivers = RetryDrivers()
    monkeypatch.setattr("openmcp.execution.random.uniform", lambda _a, _b: 0)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait(
            (await runtime.submit(project.id, "implement", "retry")).job_id,
            10,
        )
        assert job.state == "failed"
        assert job.attempts == 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancellation_interrupts_retry_backoff(tmp_path) -> None:
    root = repository(tmp_path)
    selection = TargetSelection(("primary",), 2)
    catalog = replace(
        config(tmp_path / "home"),
        profiles={
            "balanced": {
                "implement": selection,
                "review": selection,
                "consult": selection,
            }
        },
    )
    drivers = RetryDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submitted = await runtime.submit(project.id, "implement", "retry")
        await drivers.started.wait()
        runtime.cancel(submitted.job_id)
        assert (await runtime.wait(submitted.job_id, 0.5)).state == "cancelled"
        assert drivers.calls == 1
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
async def test_shutdown_interrupts_active_job(tmp_path) -> None:
    root = repository(tmp_path)
    catalog = config(tmp_path / "home")
    drivers = BlockingDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    project = runtime.register_project(str(root))
    submitted = await runtime.submit(project.id, "implement", "block")
    await drivers.started.wait()

    await runtime.close()

    database = Database(catalog.database_path)
    try:
        job = database.job(submitted.job_id)
        assert job and job.state == "interrupted"
    finally:
        database.close()


@pytest.mark.asyncio
async def test_startup_interrupts_persisted_running_job_without_reset(tmp_path) -> None:
    root = repository(tmp_path)
    home = tmp_path / "home"
    catalog = config(home)
    database = Database(catalog.database_path)
    project = database.upsert_project(project_id="project", alias="project", root=root.as_posix(), head_commit="", clean=True)
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    database.create_job(job_id="running", project_id=project.id, workflow="implement", profile="balanced", prompt="change", commit_message="", execution_plan_json=json.dumps(execution_plan_data(plan)), context_key="implement")
    database.start_job("running", "")
    (root / "partial.txt").write_text("partial\n", encoding="utf-8")
    database.close()
    runtime = Runtime(catalog)
    await runtime.start()
    try:
        interrupted = runtime.database.job("running")
        assert interrupted and interrupted.state == "interrupted"
        assert interrupted.base_commit == ""
        assert (root / "partial.txt").read_text(encoding="utf-8") == "partial\n"
    finally:
        await runtime.close()


def test_registration_accepts_plain_directory_and_preserves_placeholders(tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()
    runtime = Runtime(config(tmp_path / "home"))
    try:
        project = runtime.register_project(str(root))
        assert project.root == root.resolve().as_posix()
        assert project.head_commit == ""
        assert project.clean is True
    finally:
        runtime.database.close()


@pytest.mark.parametrize("path_kind", ["missing", "file"])
def test_registration_rejects_missing_or_file_paths(tmp_path, path_kind) -> None:
    path = tmp_path / "project"
    if path_kind == "file":
        path.write_text("not a directory\n", encoding="utf-8")
    runtime = Runtime(config(tmp_path / f"home-{path_kind}"))
    try:
        with pytest.raises(OrchestrationError):
            runtime.register_project(str(path))
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_plain_directory_execution_spawns_no_git(monkeypatch, tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()

    original_run = subprocess.run

    def fail_git_spawn(command, *args, **kwargs):
        if command and command[0] == "git":
            raise AssertionError("OpenMCP spawned Git")
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fail_git_spawn)
    runtime = Runtime(config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        job = await runtime.wait((await runtime.submit(project.id, "consult", "inspect")).job_id, 10)
        assert job.state == "succeeded"
    finally:
        await runtime.close()
