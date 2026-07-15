from __future__ import annotations

import asyncio
import sqlite3
import sys
import subprocess
import threading
import time
from pathlib import Path

import pytest

from openmcp.config import DaemonConfig, RouteConfig, TargetConfig, load_config
from openmcp.backends._shell import ShellCommandCancelled, stream_shell_command_lines
from openmcp.database import Database
from openmcp.drivers import DriverResult
from openmcp.runtime import Runtime
from openmcp.workflows import load_workflow, parse_workflow, render_prompt


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.name", "OpenMCP Tests")
    _git(root, "config", "user.email", "openmcp@example.invalid")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "baseline")
    return root


def _config(home: Path, targets: tuple[TargetConfig, ...] | None = None) -> DaemonConfig:
    resolved_targets = targets or (
        TargetConfig(id="primary", backend="codex", capabilities=("code", "review")),
    )
    return DaemonConfig(
        home=home,
        max_jobs=2,
        targets=resolved_targets,
        routes=(
            RouteConfig(
                id="forge",
                targets=tuple(target.id for target in resolved_targets),
                max_attempts=len(resolved_targets),
            ),
        ),
        routing_profiles={"balanced": {"forge": "forge"}},
    )


class FakeDrivers:
    def __init__(self, outcomes: dict[str, str] | None = None, mutate: bool = False) -> None:
        self.outcomes = outcomes or {}
        self.mutate = mutate
        self.sessions: list[str] = []

    @staticmethod
    def available(target) -> bool:
        return True

    async def execute(self, *, target, cwd, session_id, **kwargs) -> DriverResult:
        self.sessions.append(session_id)
        outcome = self.outcomes.get(target.id, "SUCCESS")
        if outcome == "SUCCESS" and self.mutate:
            (cwd / "result.txt").write_text(f"created by {target.id}\n", encoding="utf-8")
        return DriverResult(
            outcome=outcome,
            session_id=session_id or f"session-{target.id}",
            text=f"response from {target.id}" if outcome == "SUCCESS" else "",
            error="" if outcome == "SUCCESS" else f"{target.id} failed",
            error_code="" if outcome == "SUCCESS" else "backend_failure",
        )


class BlockingDrivers(FakeDrivers):
    async def execute(self, *, cancel_event, **kwargs) -> DriverResult:
        while not cancel_event.is_set():
            await asyncio.sleep(0.01)
        return DriverResult(
            outcome="CANCELLED",
            session_id="",
            text="",
            error="cancelled",
            error_code="cancelled",
        )


class ChangingDrivers(FakeDrivers):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def execute(self, *, cwd, session_id, target, **kwargs) -> DriverResult:
        self.calls += 1
        (cwd / f"result-{self.calls}.txt").write_text("created\n", encoding="utf-8")
        return DriverResult(
            outcome="SUCCESS",
            session_id=session_id or f"session-{target.id}",
            text=f"response {self.calls}",
            error="",
            error_code="",
        )


def test_workflow_rejects_parallel_write_stages() -> None:
    with pytest.raises(ValueError, match="must be ordered"):
        parse_workflow(
            {
                "version": 1,
                "name": "invalid",
                "stages": {
                    "left": {"mode": "write", "route": "default", "prompt": "left"},
                    "right": {"mode": "write", "route": "default", "prompt": "right"},
                },
            },
            {"default"},
        )


def test_workflow_renders_dependency_outputs(tmp_path) -> None:
    workflow = parse_workflow(
        {
            "version": 1,
            "name": "review",
            "inputs": {"task": {"required": True}},
            "stages": {
                "implement": {
                    "mode": "write",
                    "route": "default",
                    "prompt": "${inputs.task}",
                },
                "review": {
                    "needs": ["implement"],
                    "mode": "read",
                    "route": "default",
                    "prompt": "Review ${stages.implement.text} in ${project.root}",
                },
            },
        },
        {"default"},
    )
    prompt = render_prompt(
        workflow.stages[1],
        inputs={"task": "build"},
        project_root=tmp_path,
        stage_results={"implement": [{"text": "done", "commit": "abc"}]},
    )
    assert prompt == f"Review done in {tmp_path.as_posix()}"


def test_owner_specific_workflows_use_dedicated_routes(tmp_path) -> None:
    routes = {"forge", "canvas", "sage", "sentinel"}

    assert load_workflow(tmp_path, "forge-write", routes).stages[0].route == "forge"
    assert load_workflow(tmp_path, "canvas-write", routes).stages[0].route == "canvas"
    assert load_workflow(tmp_path, "sage-read", routes).stages[0].route == "sage"
    assert load_workflow(tmp_path, "sentinel-read", routes).stages[0].route == "sentinel"


def test_default_consultant_and_reviewer_are_isolated_pi_targets(tmp_path) -> None:
    config = load_config(tmp_path / "missing.toml")
    targets = {target.id: target for target in config.targets}
    routes = {route.id: route for route in config.routes}

    for target_id in ("sage-primary", "sentinel-primary"):
        target = targets[target_id]
        assert target.backend == "pi"
        assert target.model == "gpt-5.6-sol"
        assert target.isolated
        assert target.read_only
        assert target.system_prompt
    assert routes["sage"].targets == ("sage-primary",)
    assert routes["sentinel"].targets == ("sentinel-primary",)


def test_config_loads_routing_profile_overlays(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[daemon]
default_routing_profile = "quality"

[[targets]]
id = "premium"
backend = "codex"
capabilities = ["code"]

[[routes]]
id = "forge-quality"
targets = ["premium"]

[routing_profiles.quality]
forge = "forge-quality"
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.default_routing_profile == "quality"
    assert config.routing_profiles == {
        "quality": {"forge": "forge-quality"},
    }


def test_database_migrates_routing_profile_column(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    Database(path).close()
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE jobs DROP COLUMN routing_profile")
    connection.execute("DELETE FROM schema_migrations WHERE version=3")
    connection.commit()
    connection.close()

    database = Database(path)
    database.close()
    connection = sqlite3.connect(path)
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
    }
    migrations = {
        row[0]
        for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
    }
    connection.close()

    assert "routing_profile" in columns
    assert 3 in migrations


def test_database_marks_active_work_interrupted(tmp_path) -> None:
    database = Database(tmp_path / "openmcp.db")
    database.upsert_project(
        project_id="project",
        alias="project",
        root="/project",
        head_commit="abc",
        clean=True,
    )
    database.create_job(
        job_id="job",
        project_id="project",
        workflow="single-read",
        routing_profile="balanced",
        workflow_json="{}",
        inputs={},
        context_key="test",
        parent_job_id="",
        base_commit="abc",
        integration_base="abc",
        branch="openmcp/job",
        worktree="/worktree",
        stages=[("execute", 0, "read")],
    )
    database.set_job_state("job", "running")
    database.set_stage_state("job", "execute", "running")

    database.interrupt_active_jobs()

    job = database.job("job")
    assert job is not None
    assert job.state == "interrupted"
    assert job.stages[0].state == "interrupted"
    database.close()


def test_shell_command_cancellation_terminates_process_group() -> None:
    cancelled = threading.Event()
    timer = threading.Timer(0.2, cancelled.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(ShellCommandCancelled):
            list(
                stream_shell_command_lines(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    executable_name=sys.executable,
                    line_transform=str.strip,
                    terminate_wait_s=1,
                    cancel_event=cancelled,
                )
            )
    finally:
        timer.cancel()
    assert time.monotonic() - started < 3


@pytest.mark.asyncio
async def test_mcp_exposes_clean_daemon_contract() -> None:
    from openmcp.server import mcp

    tools = {tool.name: tool for tool in await mcp.list_tools()}
    resources = {str(resource.uri) for resource in await mcp.list_resources()}
    templates = {
        template.uriTemplate
        for template in await mcp.list_resource_templates()
    }

    assert set(tools) == {
        "project_register",
        "job_submit",
        "job_wait",
        "job_cancel",
        "job_retry",
        "job_integrate",
    }
    assert "parent_job_id" in tools["job_submit"].inputSchema["properties"]
    assert "routing_profile" in tools["job_submit"].inputSchema["properties"]
    assert resources == {
        "openmcp://projects",
        "openmcp://models",
        "openmcp://routing-profiles",
    }
    assert "openmcp://projects/{project_id}/jobs" in templates


@pytest.mark.asyncio
async def test_write_job_isolated_then_integrated(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root), "sample")
        submission = await runtime.submit(
            project.id,
            "single-write",
            {"prompt": "create result"},
            "feature",
        )
        job = await runtime.wait(submission.job_id, 10)

        assert job.state == "succeeded"
        assert job.result.commit != job.base_commit
        assert not (root / "result.txt").exists()

        integrated = runtime.integrate(job.id)
        assert integrated.success
        assert integrated.state == "integrated"
        assert (root / "result.txt").read_text(encoding="utf-8") == "created by primary\n"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_read_job_discards_filesystem_changes(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "single-read",
            {"prompt": "inspect"},
        )
        job = await runtime.wait(submission.job_id, 10)

        assert job.state == "succeeded"
        assert job.result.commit == job.base_commit
        assert not (root / "result.txt").exists()
        record = runtime.database.job_record(job.id)
        assert record is not None
        assert not (Path(record["worktree"]) / "result.txt").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_route_fails_over_and_preserves_context_session(tmp_path) -> None:
    root = _repository(tmp_path)
    targets = (
        TargetConfig(id="broken", backend="agy"),
        TargetConfig(id="healthy", backend="codex"),
    )
    runtime = Runtime(_config(tmp_path / "home", targets))
    drivers = FakeDrivers(outcomes={"broken": "TARGET_FATAL"})
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        first = await runtime.submit(
            project.id,
            "single-read",
            {"prompt": "first"},
            "shared",
        )
        first_job = await runtime.wait(first.job_id, 10)
        assert first_job.state == "succeeded"
        assert first_job.stages[0].target_id == "healthy"

        second = await runtime.submit(
            project.id,
            "single-read",
            {"prompt": "second"},
            "shared",
        )
        second_job = await runtime.wait(second.job_id, 10)
        assert second_job.state == "succeeded"
        assert drivers.sessions[-1] == "session-healthy"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_job_selects_configured_routing_profile(tmp_path) -> None:
    root = _repository(tmp_path)
    targets = (
        TargetConfig(id="economy", backend="codex"),
        TargetConfig(id="premium", backend="codex"),
    )
    config = DaemonConfig(
        home=tmp_path / "home",
        targets=targets,
        routes=(
            RouteConfig(id="forge-economy", targets=("economy",)),
            RouteConfig(id="forge-quality", targets=("premium",)),
        ),
        routing_profiles={
            "cost": {"forge": "forge-economy"},
            "quality": {"forge": "forge-quality"},
        },
        default_routing_profile="cost",
    )
    runtime = Runtime(config)
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "single-read",
            {"prompt": "inspect"},
            routing_profile="quality",
        )
        job = await runtime.wait(submission.job_id, 10)

        assert job.routing_profile == "quality"
        assert job.stages[0].target_id == "premium"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_integration_rejects_advanced_project_head(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "single-write",
            {"prompt": "create result"},
        )
        job = await runtime.wait(submission.job_id, 10)
        (root / "other.txt").write_text("advanced\n", encoding="utf-8")
        _git(root, "add", "other.txt")
        _git(root, "commit", "-m", "advance")

        integrated = runtime.integrate(job.id)

        assert not integrated.success
        assert integrated.state == "integration_conflict"
        assert not (root / "result.txt").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_failed_job_can_retry_explicitly(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    drivers = FakeDrivers(outcomes={"primary": "RETRYABLE"})
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "single-read",
            {"prompt": "inspect"},
        )
        failed = await runtime.wait(submission.job_id, 10)
        assert failed.state == "failed"

        drivers.outcomes.clear()
        retried = await runtime.retry(failed.id)
        succeeded = await runtime.wait(retried.job_id, 10)

        assert succeeded.state == "succeeded"
        assert succeeded.stages[0].attempts == 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_daemon_shutdown_marks_running_job_interrupted(tmp_path) -> None:
    root = _repository(tmp_path)
    home = tmp_path / "home"
    runtime = Runtime(_config(home))
    runtime.drivers = BlockingDrivers()
    await runtime.start()
    project = runtime.register_project(str(root))
    submission = await runtime.submit(
        project.id,
        "single-read",
        {"prompt": "wait"},
    )
    for _ in range(100):
        job = runtime.database.job(submission.job_id)
        if job is not None and job.state == "running":
            break
        await asyncio.sleep(0.01)
    await runtime.close()

    database = Database(home / "openmcp.db")
    interrupted = database.job(submission.job_id)
    assert interrupted is not None
    assert interrupted.state == "interrupted"
    database.close()


@pytest.mark.asyncio
async def test_review_job_can_chain_before_integration(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        implementation = await runtime.submit(
            project.id,
            "single-write",
            {
                "prompt": "implement",
                "commit_message": "feat: add result",
            },
            "phase/implementer",
        )
        implementation_job = await runtime.wait(implementation.job_id, 10)
        review = await runtime.submit(
            project.id,
            "single-read",
            {"prompt": "review"},
            "phase/reviewer",
            implementation_job.id,
        )
        review_job = await runtime.wait(review.job_id, 10)

        assert review_job.base_commit == implementation_job.result.commit
        assert review_job.integration_base == implementation_job.integration_base
        assert _git(Path(runtime.database.job_record(implementation_job.id)["worktree"]), "log", "-1", "--format=%s") == "feat: add result"
        assert not (root / "result.txt").exists()

        integrated = runtime.integrate(implementation_job.id)
        assert integrated.success
        assert (root / "result.txt").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_integrating_fix_chain_cleans_all_write_jobs(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = ChangingDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        implementation = await runtime.submit(
            project.id,
            "single-write",
            {"prompt": "implement"},
        )
        implementation_job = await runtime.wait(implementation.job_id, 10)
        fix = await runtime.submit(
            project.id,
            "single-write",
            {"prompt": "fix"},
            parent_job_id=implementation_job.id,
        )
        fix_job = await runtime.wait(fix.job_id, 10)
        implementation_record = runtime.database.job_record(implementation_job.id)
        fix_record = runtime.database.job_record(fix_job.id)

        integrated = runtime.integrate(fix_job.id)

        assert integrated.success
        assert runtime.database.job(implementation_job.id).state == "integrated"
        assert runtime.database.job(fix_job.id).state == "integrated"
        assert not Path(implementation_record["worktree"]).exists()
        assert not Path(fix_record["worktree"]).exists()
        assert (root / "result-1.txt").exists()
        assert (root / "result-2.txt").exists()
    finally:
        await runtime.close()
