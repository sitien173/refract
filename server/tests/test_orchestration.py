from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import subprocess
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import openmcp.processes as processes
from openmcp.config import (
    DaemonConfig,
    RouteConfig,
    TargetConfig,
    load_config,
    load_project_config,
    load_task_routes,
)
from openmcp.backends._shell import ShellCommandCancelled, stream_shell_command_lines
from openmcp.database import Database
from openmcp.drivers import DriverResult
from openmcp.models import JobView, StageView
from openmcp.overlays import OverlayError, load_overlay_rules
from openmcp.planning import execution_plan_data, parse_execution_plan, resolve_execution_plan
from openmcp.runtime import Runtime
from openmcp.workflows import (
    load_workflow,
    parse_workflow,
    render_prompt,
    validate_inputs,
)


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
        routing_profiles={"balanced": {"default": "forge", "forge": "forge"}},
    )


class FakeDrivers:
    def __init__(self, outcomes: dict[str, str] | None = None, mutate: bool = False) -> None:
        self.outcomes = outcomes or {}
        self.mutate = mutate
        self.sessions: list[str] = []
        self.backends: list[str] = []
        self.targets: list[TargetConfig] = []

    @staticmethod
    def available(target) -> bool:
        return True

    async def execute(self, *, target, cwd, session_id, **kwargs) -> DriverResult:
        self.sessions.append(session_id)
        self.backends.append(target.backend)
        self.targets.append(target)
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


class ExplodingDrivers(FakeDrivers):
    async def execute(self, **kwargs) -> DriverResult:
        raise RuntimeError("driver exploded")


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


class OverlayDrivers(FakeDrivers):
    async def execute(self, *, cwd, session_id, target, **kwargs) -> DriverResult:
        config = cwd / "config"
        theme = cwd / "themes" / "dark" / "palette.local.css"
        assert (
            config / "application.development.json"
        ).read_text(encoding="utf-8") == "original\n"
        assert (config / "remove.development.json").read_text(
            encoding="utf-8"
        ) == "remove\n"
        assert not (config / "private.development.json").exists()
        assert theme.read_text(encoding="utf-8") == "old theme\n"
        (config / "application.development.json").write_text(
            "updated\n",
            encoding="utf-8",
        )
        (config / "remove.development.json").unlink()
        (config / "created.development.json").write_text(
            "created\n",
            encoding="utf-8",
        )
        theme.write_text("new theme\n", encoding="utf-8")
        return DriverResult(
            outcome="SUCCESS",
            session_id=session_id or f"session-{target.id}",
            text="overlay updated",
            error="",
            error_code="",
        )


class ChainedOverlayDrivers(FakeDrivers):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def execute(self, *, cwd, session_id, target, **kwargs) -> DriverResult:
        self.calls += 1
        path = cwd / "config" / "application.development.json"
        expected = "original\n" if self.calls == 1 else "parent\n"
        assert path.read_text(encoding="utf-8") == expected
        path.write_text(
            "parent\n" if self.calls == 1 else "child\n",
            encoding="utf-8",
        )
        return DriverResult(
            outcome="SUCCESS",
            session_id=session_id or f"session-{target.id}",
            text=f"overlay update {self.calls}",
            error="",
            error_code="",
        )


class RetriedOverlayDrivers(FakeDrivers):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def execute(self, *, cwd, session_id, target, **kwargs) -> DriverResult:
        self.calls += 1
        path = cwd / "config" / "application.development.json"
        expected = {
            1: "original\n",
            2: "first\n",
            3: "original\n",
            4: "rerun\n",
        }[self.calls]
        assert path.read_text(encoding="utf-8") == expected
        path.write_text(
            {
                1: "first\n",
                2: "failed\n",
                3: "rerun\n",
                4: "final\n",
            }[self.calls],
            encoding="utf-8",
        )
        outcome = "TARGET_FATAL" if self.calls == 2 else "SUCCESS"
        return DriverResult(
            outcome=outcome,
            session_id=session_id or f"session-{target.id}",
            text="overlay retry" if outcome == "SUCCESS" else "",
            error="failed stage" if outcome != "SUCCESS" else "",
            error_code="backend_failure" if outcome != "SUCCESS" else "",
        )


def _overlay_repository(tmp_path: Path) -> Path:
    root = _repository(tmp_path)
    (root / ".gitignore").write_text(
        "\n".join(
            [
                ".openmcp.local.toml",
                "config/*.development.json",
                "themes/**/*.local.css",
                "",
            ]
        ),
        encoding="utf-8",
    )
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-m", "ignore development files")
    config = root / "config"
    theme = root / "themes" / "dark"
    config.mkdir()
    theme.mkdir(parents=True)
    (config / "application.development.json").write_text(
        "original\n",
        encoding="utf-8",
    )
    (config / "remove.development.json").write_text(
        "remove\n",
        encoding="utf-8",
    )
    (config / "private.development.json").write_text(
        "private\n",
        encoding="utf-8",
    )
    (theme / "palette.local.css").write_text("old theme\n", encoding="utf-8")
    (root / ".openmcp.local.toml").write_text(
        """[[overlays]]
include = ["config/*.development.json", "themes/**/*.local.css"]
exclude = ["config/private.development.json"]
workflows = ["write"]
""",
        encoding="utf-8",
    )
    return root


def test_overlay_patterns_reject_platform_specific_paths(tmp_path) -> None:
    config = tmp_path / ".openmcp.local.toml"
    for pattern in ("C:/secrets/**", "config\\secrets\\**", "config/file:stream"):
        config.write_text(
            "[[overlays]]\n"
            f"include = [{pattern!r}]\n"
            "workflows = [\"write\"]\n",
            encoding="utf-8",
        )
        with pytest.raises(OverlayError):
            load_overlay_rules(tmp_path, "write")


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


def test_workflow_requires_result_for_multiple_terminal_stages() -> None:
    data = {
        "version": 1,
        "name": "parallel-review",
        "stages": {
            "quality": {"route": "review", "prompt": "quality"},
            "tests": {"route": "review", "prompt": "tests"},
        },
    }

    with pytest.raises(ValueError, match="require result_stage"):
        parse_workflow(data)

    data["result_stage"] = "quality"
    workflow = parse_workflow(data)
    assert workflow.result_stage == "quality"


def test_workflow_validates_types_and_dependency_references() -> None:
    workflow = parse_workflow(
        {
            "version": 1,
            "name": "typed",
            "inputs": {
                "count": {"type": "integer", "required": True},
                "note": {"type": "string"},
            },
            "stages": {
                "execute": {
                    "route": "forge",
                    "prompt": "${inputs.count}:${inputs.note}",
                },
            },
        }
    )

    with pytest.raises(ValueError, match="invalid types"):
        validate_inputs(workflow, {"count": True})
    validate_inputs(workflow, {"count": 2})
    assert render_prompt(
        workflow.stages[0],
        inputs={"count": 2},
        project_root=Path("/project"),
        stage_results={},
    ) == "2:"

    with pytest.raises(ValueError, match="non-dependency"):
        parse_workflow(
            {
                "version": 1,
                "name": "bad-reference",
                "result_stage": "second",
                "stages": {
                    "first": {"route": "forge", "prompt": "first"},
                    "second": {
                        "route": "forge",
                        "prompt": "${stages.first.text}",
                    },
                },
            }
        )


def test_builtin_workflows_are_permissions(tmp_path) -> None:
    read = load_workflow(tmp_path, "read", {"default"})
    write = load_workflow(tmp_path, "write", {"default"})

    assert (read.stages[0].mode, read.stages[0].route) == ("read", "default")
    assert (write.stages[0].mode, write.stages[0].route) == ("write", "default")


def test_new_role_resolves_without_workflow_parser_changes(tmp_path) -> None:
    workflow = parse_workflow(
        {
            "version": 1,
            "name": "analyst",
            "stages": {
                "execute": {
                    "mode": "read",
                    "route": "analyst",
                    "prompt": "analyze",
                },
            },
        }
    )
    config = DaemonConfig(
        home=tmp_path,
        targets=(
            TargetConfig(
                id="analyst-primary",
                backend="pi",
                args=("--provider", "openai", "--offline"),
            ),
        ),
        routes=(RouteConfig(id="analysis", targets=("analyst-primary",)),),
        routing_profiles={"balanced": {"analyst": "analysis"}},
    )

    plan = resolve_execution_plan(workflow, config, "balanced")

    assert plan.route("analyst").id == "analysis"
    assert plan.target("analyst-primary").backend == "pi"
    restored = parse_execution_plan(execution_plan_data(plan))
    assert restored.target("analyst-primary").args == (
        "--provider", "openai", "--offline",
    )


def test_task_route_template_prefers_project_then_global(tmp_path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    (project / ".openmcp").mkdir(parents=True)
    global_path = home / "task_routes.json"
    project_path = project / ".openmcp" / "task_routes.json"
    global_path.write_text(
        '{"version": 1, "routes": [{"recommend": "Forge"}]}',
        encoding="utf-8",
    )
    project_path.write_text(
        '{"version": 1, "routes": [{"recommend": "Builder"}]}',
        encoding="utf-8",
    )

    project_routes = load_task_routes(home, project)
    project_path.unlink()
    global_routes = load_task_routes(home, project)

    assert project_routes["routes"][0]["recommend"] == "Builder"
    assert global_routes["routes"][0]["recommend"] == "Forge"


def test_task_route_template_requires_nonempty_json_object(tmp_path) -> None:
    with pytest.raises(ValueError, match="Missing task route template"):
        load_task_routes(tmp_path)

    (tmp_path / "task_routes.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty JSON object"):
        load_task_routes(tmp_path)


@pytest.mark.asyncio
async def test_task_route_tool_uses_registered_project_template(tmp_path) -> None:
    from openmcp.server import task_route

    root = _repository(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    (home / "task_routes.json").write_text(
        '{"routes": [{"recommend": "Forge"}]}',
        encoding="utf-8",
    )
    directory = root / ".openmcp"
    directory.mkdir()
    (directory / "task_routes.json").write_text(
        '{"routes": [{"recommend": "Builder"}]}',
        encoding="utf-8",
    )
    _git(root, "add", ".openmcp/task_routes.json")
    _git(root, "commit", "-m", "add task routes")
    runtime = Runtime(_config(home))
    try:
        project = runtime.register_project(str(root))
        ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=runtime)
        )

        result = await task_route("Implement feature", ctx, project.id)

        assert result.template["routes"][0]["recommend"] == "Builder"
    finally:
        runtime.database.close()


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
args = ["--ephemeral", "--color", "never"]
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
    assert config.targets[0].args == ("--ephemeral", "--color", "never")
    assert config.routing_profiles == {
        "quality": {"forge": "forge-quality"},
    }


@pytest.mark.parametrize(
    ("backend", "arg", "error"),
    [
        ("agy", "--", "reserved '--' token"),
        ("pi", "--", "reserved '--' token"),
        ("codex", "--cd", "workspace root"),
        ("codex", "--cd=D:/other", "workspace root"),
        ("codex", "-C", "workspace root"),
        ("codex", "-CD:/other", "workspace root"),
    ],
)
def test_config_rejects_reserved_target_args(tmp_path, backend, arg, error) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        f'''\n[[targets]]\nid = "unsafe"\nbackend = "{backend}"\nargs = ["{arg}"]\n''',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=error):
        load_config(path)


def test_config_rejects_resource_loading_args_for_isolated_pi(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[[targets]]
id = "unsafe-reviewer"
backend = "pi"
isolated = true
args = ["--extension", "reviewer.ts"]
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Isolated Pi target"):
        load_config(path)


def test_project_config_overlays_routes_and_profiles(tmp_path) -> None:
    project = tmp_path / "project"
    (project / ".openmcp").mkdir(parents=True)
    (project / ".openmcp" / "config.toml").write_text(
        """
[project]
default_routing_profile = "quality"

[[routes]]
id = "forge-project"
targets = ["premium"]

[routing_profiles.quality]
forge = "forge-project"
""",
        encoding="utf-8",
    )
    base = DaemonConfig(
        home=tmp_path / "home",
        targets=(
            TargetConfig(id="primary", backend="codex"),
            TargetConfig(id="premium", backend="agy"),
        ),
        routes=(RouteConfig(id="forge", targets=("primary",)),),
        routing_profiles={"balanced": {"forge": "forge"}},
    )

    project_config = load_project_config(project, base)

    assert project_config.default_routing_profile == "quality"
    assert project_config.routing_profiles["quality"] == {
        "forge": "forge-project",
    }
    assert project_config.routes[-1].targets == ("premium",)
    assert base.default_routing_profile == "balanced"


def test_project_config_rejects_daemon_and_target_overrides(tmp_path) -> None:
    project = tmp_path / "project"
    (project / ".openmcp").mkdir(parents=True)
    (project / ".openmcp" / "config.toml").write_text(
        "[daemon]\nmax_jobs = 1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported project config sections"):
        load_project_config(project, _config(tmp_path / "home"))


def test_project_init_creates_files_without_overwriting(tmp_path) -> None:
    root = _repository(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    (home / "task_routes.json").write_text(
        '{"version": 1, "routes": [{"recommend": "Forge"}]}',
        encoding="utf-8",
    )
    runtime = Runtime(_config(home))
    try:
        first = runtime.initialize_project(str(root))
        config_path = root / ".openmcp" / "config.toml"
        config_path.write_text("[project]\n", encoding="utf-8")
        second = runtime.initialize_project(str(root))

        assert first.created == [
            ".openmcp/config.toml",
            ".openmcp/task_routes.json",
        ]
        assert first.requires_commit
        assert second.created == []
        assert second.existing == first.created
        assert not second.requires_commit
        assert config_path.read_text(encoding="utf-8") == "[project]\n"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_submission_uses_project_route_override(tmp_path) -> None:
    root = _repository(tmp_path)
    directory = root / ".openmcp"
    directory.mkdir()
    (directory / "config.toml").write_text(
        """
[[routes]]
id = "forge"
targets = ["project-target"]
""",
        encoding="utf-8",
    )
    _git(root, "add", ".openmcp/config.toml")
    _git(root, "commit", "-m", "add project routing")
    targets = (
        TargetConfig(id="global-target", backend="codex"),
        TargetConfig(id="project-target", backend="agy"),
    )
    runtime = Runtime(
        DaemonConfig(
            home=tmp_path / "home",
            max_jobs=1,
            targets=targets,
            routes=(RouteConfig(id="forge", targets=("global-target",)),),
            routing_profiles={"balanced": {"default": "forge"}},
        )
    )
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "read",
            {"prompt": "inspect"},
        )
        job = await runtime.wait(submission.job_id, 10)

        assert job.state == "succeeded"
        assert job.result.text == "response from project-target"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_new_submissions_reload_backend_without_reusing_session(
    tmp_path,
    monkeypatch,
) -> None:
    root = _repository(tmp_path)
    home = tmp_path / "home"
    path = home / "config.toml"
    home.mkdir()
    monkeypatch.setenv("OPENMCP_HOME", str(home))

    def write_config(backend: str) -> None:
        path.write_text(
            f"""
[[targets]]
id = "primary"
backend = "{backend}"
capabilities = ["code"]

[[routes]]
id = "forge"
targets = ["primary"]

[routing_profiles.balanced]
default = "forge"
""",
            encoding="utf-8",
        )

    write_config("codex")
    runtime = Runtime(load_config(path))
    drivers = FakeDrivers()
    runtime.drivers = drivers
    project = runtime.register_project(str(root))
    first = await runtime.submit(
        project.id,
        "read",
        {"prompt": "first"},
        context_key="shared",
    )
    write_config("agy")
    await runtime.start()
    try:
        await runtime.wait(first.job_id, 10)

        second = await runtime.submit(
            project.id,
            "read",
            {"prompt": "second"},
            context_key="shared",
        )
        await runtime.wait(second.job_id, 10)

        assert drivers.backends == ["codex", "agy"]
        assert drivers.sessions == ["", ""]
        first_record = runtime.database.job_record(first.job_id)
        second_record = runtime.database.job_record(second.job_id)
        assert '"backend": "codex"' in first_record["execution_plan_json"]
        assert '"backend": "agy"' in second_record["execution_plan_json"]
    finally:
        await runtime.close()


def test_database_migrates_execution_state(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    Database(path).close()
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE jobs DROP COLUMN routing_profile")
    connection.execute("ALTER TABLE context_sessions RENAME TO context_sessions_new")
    connection.execute(
        """
        CREATE TABLE context_sessions (
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            context_key TEXT NOT NULL,
            role TEXT NOT NULL,
            target_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            PRIMARY KEY(project_id, context_key, role, target_id)
        )
        """
    )
    connection.execute("DROP TABLE context_sessions_new")
    connection.commit()
    connection.close()

    database = Database(path)
    database.close()
    connection = sqlite3.connect(path)
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
    }
    migration_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    session_columns = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(context_sessions)"
        ).fetchall()
    }
    connection.close()

    assert "routing_profile" in columns
    assert "execution_plan_json" in columns
    assert "result_stage" in columns
    assert "result_text" not in columns
    assert {"target_key", "lane", "updated_at"}.issubset(session_columns)
    assert migration_table is None


def test_archive_patch_preserves_git_output_bytes(tmp_path) -> None:
    from openmcp.workspaces import WorkspaceManager

    root = _repository(tmp_path)
    base_commit = _git(root, "rev-parse", "HEAD")
    binary = root / "image.bin"
    binary.write_bytes(b"\x00\xff\x80\x00openmcp\n")
    _git(root, "add", "--intent-to-add", ".")
    expected = subprocess.run(
        ["git", "-C", str(root), "diff", "--binary", base_commit],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    destination = tmp_path / "archive" / "binary.patch"

    assert WorkspaceManager.archive_patch(root, destination, base_commit)
    assert destination.read_bytes() == expected


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
        workflow="read",
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


def test_job_views_return_result_stage_text_once(tmp_path) -> None:
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
        workflow="two-stage",
        routing_profile="balanced",
        workflow_json="{}",
        result_stage="review",
        inputs={},
        context_key="test",
        parent_job_id="",
        base_commit="abc",
        integration_base="abc",
        branch="openmcp/job",
        worktree="/worktree",
        stages=[("implement", 0, "write"), ("review", 1, "read")],
    )
    database.set_stage_state("job", "implement", "succeeded", text="implemented")
    database.set_stage_state("job", "review", "succeeded", text="reviewed")
    database.set_job_commit("job", "def")
    database.set_job_state("job", "succeeded")

    compact = database.job("job", include_stage_outputs=False)
    detailed = database.job("job", include_stage_outputs=True)

    assert compact is not None
    assert detailed is not None
    assert compact.result.text == "reviewed"
    assert [stage.text for stage in compact.stages] == ["", ""]
    assert [stage.text for stage in detailed.stages] == ["implemented", ""]
    database.close()


def test_windows_cleanup_attempts_tree_kill_after_launcher_exit(monkeypatch) -> None:
    calls: list[tuple[int, bool]] = []

    class ExitedProcess:
        pid = 12345

        @staticmethod
        def send_signal(_signal) -> None:
            return

        @staticmethod
        def wait(*, timeout) -> int:
            return 0

        @staticmethod
        def poll() -> int:
            return 0

    monkeypatch.setattr(
        processes,
        "_taskkill",
        lambda process_id, *, force, timeout_s: calls.append((process_id, force)),
    )

    processes._terminate_windows(ExitedProcess(), 1)

    assert calls == [(12345, False)]


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher behavior")
def test_shell_command_uses_safe_npm_powershell_shim(tmp_path) -> None:
    command = tmp_path / "agent.cmd"
    command.write_text("@echo unsafe & whoami\n", encoding="utf-8")
    command.with_suffix(".ps1").write_text(
        "$args | ForEach-Object { Write-Output $_ }\n",
        encoding="utf-8",
    )

    output = list(
        stream_shell_command_lines(
            [os.fspath(command), "hello&whoami", "100%PATH%"],
            executable_name=os.fspath(command),
            line_transform=lambda line: line.rstrip("\r\n"),
            terminate_wait_s=1,
        )
    )

    assert output == ["hello&whoami", "100%PATH%"]


def test_shell_command_cancellation_terminates_process_group(tmp_path) -> None:
    child_marker = tmp_path / "leaked-child.txt"
    child_code = (
        "import pathlib,time; time.sleep(1); "
        f"pathlib.Path({str(child_marker)!r}).write_text('leaked', encoding='utf-8')"
    )
    parent_code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(30)"
    )
    cancelled = threading.Event()
    timer = threading.Timer(0.2, cancelled.set)
    timer.start()
    started = time.monotonic()
    try:
        with pytest.raises(ShellCommandCancelled):
            list(
                stream_shell_command_lines(
                    [sys.executable, "-c", parent_code],
                    executable_name=sys.executable,
                    line_transform=str.strip,
                    terminate_wait_s=1,
                    cancel_event=cancelled,
                )
            )
    finally:
        timer.cancel()
    assert time.monotonic() - started < 3
    time.sleep(1)
    assert not child_marker.exists()


@pytest.mark.asyncio
async def test_job_wait_uses_runtime_completion_waiter() -> None:
    from openmcp.server import job_wait

    def view(state: str, stage_state: str) -> JobView:
        return JobView(
            id="job",
            project_id="project",
            workflow="read",
            routing_profile="balanced",
            state=state,
            context_key="test",
            parent_job_id="",
            base_commit="abc",
            integration_base="abc",
            branch="openmcp/job",
            created_at="now",
            updated_at="now",
            stages=[StageView(id="execute", state=stage_state, mode="read")],
        )

    running = view("running", "running")
    succeeded = view("succeeded", "succeeded")

    class DatabaseStub:
        def __init__(self) -> None:
            self.calls = 0

        def job(self, job_id: str, *, include_stage_outputs: bool) -> JobView:
            self.calls += 1
            return running if self.calls == 1 else succeeded

    class RuntimeStub:
        def __init__(self) -> None:
            self.database = DatabaseStub()
            self.wait_calls: list[tuple[str, int]] = []

        async def wait(self, job_id: str, timeout_s: int) -> JobView:
            self.wait_calls.append((job_id, timeout_s))
            return succeeded

    class ContextStub:
        def __init__(self, runtime: RuntimeStub) -> None:
            self.request_context = SimpleNamespace(lifespan_context=runtime)
            self.progress: list[tuple[float, float, str]] = []

        async def report_progress(
            self,
            *,
            progress: float,
            total: float,
            message: str,
        ) -> None:
            self.progress.append((progress, total, message))

    runtime = RuntimeStub()
    ctx = ContextStub(runtime)

    result = await job_wait("job", ctx, timeout_s=12)

    assert result is succeeded
    assert runtime.wait_calls == [("job", 12)]
    assert ctx.progress == [(0.0, 1.0, "running"), (1.0, 1.0, "succeeded")]


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
        "project_init",
        "project_register",
        "task_route",
        "job_submit",
        "job_wait",
        "job_cancel",
        "job_retry",
        "job_integrate",
    }
    assert "parent_job_id" in tools["job_submit"].inputSchema["properties"]
    assert "routing_profile" in tools["job_submit"].inputSchema["properties"]
    assert "include_stage_outputs" in tools["job_wait"].inputSchema["properties"]
    assert set(tools["task_route"].inputSchema["properties"]) == {
        "task",
        "project_id",
    }
    assert set(tools["project_init"].inputSchema["properties"]) == {"path"}
    assert resources == {
        "openmcp://projects",
        "openmcp://models",
        "openmcp://routing-profiles",
    }
    assert "openmcp://projects/{project_id}/jobs" in templates
    assert "openmcp://projects/{project_id}/routing-profiles" in templates


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
            "write",
            {"prompt": "create result"},
            "feature",
        )
        job = await runtime.wait(submission.job_id, 10)

        assert job.state == "succeeded"
        assert job.result.commit != job.base_commit
        assert job.result.text == "response from primary"
        assert job.stages[0].text == ""
        assert not (root / "result.txt").exists()
        assert not Path(runtime.database.job_record(job.id)["worktree"]).exists()

        integrated = runtime.integrate(job.id)
        assert integrated.success
        assert integrated.state == "integrated"
        assert (root / "result.txt").read_text(encoding="utf-8") == "created by primary\n"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_write_job_integrates_project_overlay_patterns(tmp_path) -> None:
    root = _overlay_repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = OverlayDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "write",
            {"prompt": "update development files"},
        )
        job = await runtime.wait(submission.job_id, 10)

        assert job.state == "succeeded"
        assert job.result.commit == job.base_commit
        assert (root / "config" / "application.development.json").read_text(
            encoding="utf-8"
        ) == "original\n"
        assert not (root / "config" / "created.development.json").exists()

        integrated = runtime.integrate(job.id)

        assert integrated.success
        assert (root / "config" / "application.development.json").read_text(
            encoding="utf-8"
        ) == "updated\n"
        assert not (root / "config" / "remove.development.json").exists()
        assert (root / "config" / "created.development.json").read_text(
            encoding="utf-8"
        ) == "created\n"
        assert (root / "config" / "private.development.json").read_text(
            encoding="utf-8"
        ) == "private\n"
        assert (root / "themes" / "dark" / "palette.local.css").read_text(
            encoding="utf-8"
        ) == "new theme\n"
        assert _git(root, "status", "--porcelain=v1") == ""
        assert _git(root, "ls-files", "config") == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_overlay_integration_detects_local_conflict(tmp_path) -> None:
    root = _overlay_repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = OverlayDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "write",
            {"prompt": "update development files"},
        )
        job = await runtime.wait(submission.job_id, 10)
        local = root / "config" / "application.development.json"
        local.write_text("changed locally\n", encoding="utf-8")

        integrated = runtime.integrate(job.id)

        assert not integrated.success
        assert integrated.state == "integration_conflict"
        assert integrated.error.endswith("config/application.development.json")
        assert local.read_text(encoding="utf-8") == "changed locally\n"
        assert not (root / "config" / "created.development.json").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_child_job_inherits_parent_overlay_changes(tmp_path) -> None:
    root = _overlay_repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = ChainedOverlayDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        parent_submission = await runtime.submit(
            project.id,
            "write",
            {"prompt": "first overlay update"},
        )
        parent = await runtime.wait(parent_submission.job_id, 10)
        child_submission = await runtime.submit(
            project.id,
            "write",
            {"prompt": "second overlay update"},
            parent_job_id=parent.id,
        )
        child = await runtime.wait(child_submission.job_id, 10)

        integrated = runtime.integrate(child.id)

        assert integrated.success
        assert runtime.database.job(parent.id).state == "integrated"
        assert runtime.database.job(child.id).state == "integrated"
        assert (root / "config" / "application.development.json").read_text(
            encoding="utf-8"
        ) == "child\n"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_rewinds_overlay_to_selected_stage(tmp_path) -> None:
    root = _overlay_repository(tmp_path)
    workflows = root / ".openmcp" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "overlay-retry.yaml").write_text(
        """version: 1
name: overlay-retry
stages:
  first:
    mode: write
    route: forge
    prompt: first
  second:
    needs: [first]
    mode: write
    route: forge
    prompt: second
""",
        encoding="utf-8",
    )
    _git(root, "add", ".openmcp/workflows/overlay-retry.yaml")
    _git(root, "commit", "-m", "add overlay retry workflow")
    (root / ".openmcp.local.toml").write_text(
        """[[overlays]]
include = ["config/*.development.json"]
workflows = ["overlay-retry"]
""",
        encoding="utf-8",
    )
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = RetriedOverlayDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "overlay-retry",
            {},
        )
        failed = await runtime.wait(submission.job_id, 10)

        assert failed.state == "failed"
        retried = await runtime.retry(failed.id, "first")
        succeeded = await runtime.wait(retried.job_id, 10)

        assert succeeded.state == "succeeded"
        assert runtime.integrate(succeeded.id).success
        assert (root / "config" / "application.development.json").read_text(
            encoding="utf-8"
        ) == "final\n"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_overlay_rejects_tracked_files(tmp_path) -> None:
    root = _repository(tmp_path)
    (root / ".gitignore").write_text(
        ".openmcp.local.toml\n",
        encoding="utf-8",
    )
    _git(root, "add", ".gitignore")
    _git(root, "commit", "-m", "ignore local overlay config")
    (root / ".openmcp.local.toml").write_text(
        """[[overlays]]
include = ["README.md"]
workflows = ["write"]
""",
        encoding="utf-8",
    )
    runtime = Runtime(_config(tmp_path / "home"))
    await runtime.start()
    try:
        project = runtime.register_project(str(root))

        with pytest.raises(ValueError, match="must be ignored by Git: README.md"):
            await runtime.submit(
                project.id,
                "write",
                {"prompt": "update development files"},
            )

        assert _git(root, "branch", "--list", "openmcp/*") == ""
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
            "read",
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
            "read",
            {"prompt": "first"},
            "shared",
        )
        first_job = await runtime.wait(first.job_id, 10)
        assert first_job.state == "succeeded"
        assert first_job.stages[0].target_id == "healthy"

        second = await runtime.submit(
            project.id,
            "read",
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
        TargetConfig(
            id="economy",
            backend="codex",
            model="economy-model",
            profile="economy-profile",
            reasoning="low",
        ),
        TargetConfig(
            id="premium",
            backend="codex",
            model="quality-model",
            profile="quality-profile",
            reasoning="high",
        ),
    )
    config = DaemonConfig(
        home=tmp_path / "home",
        targets=targets,
        routes=(
            RouteConfig(id="forge-economy", targets=("economy",)),
            RouteConfig(id="forge-quality", targets=("premium",)),
        ),
        routing_profiles={
            "cost": {"default": "forge-economy"},
            "quality": {"default": "forge-quality"},
        },
        default_routing_profile="cost",
    )
    runtime = Runtime(config)
    drivers = FakeDrivers()
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "read",
            {"prompt": "inspect"},
            routing_profile="quality",
        )
        job = await runtime.wait(submission.job_id, 10)

        assert job.routing_profile == "quality"
        assert job.stages[0].target_id == "premium"
        assert drivers.targets[-1] == targets[1]
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
            "write",
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
            "read",
            {"prompt": "inspect"},
        )
        failed = await runtime.wait(submission.job_id, 10)
        assert failed.state == "failed"
        record = runtime.database.job_record(failed.id)
        assert record is not None
        assert not Path(record["worktree"]).exists()

        drivers.outcomes.clear()
        retried = await runtime.retry(failed.id)
        succeeded = await runtime.wait(retried.job_id, 10)

        assert succeeded.state == "succeeded"
        assert succeeded.stages[0].attempts == 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_unexpected_driver_error_fails_stage_and_cleans_worktree(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = ExplodingDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "write",
            {"prompt": "explode"},
        )
        job = await runtime.wait(submission.job_id, 10)
        record = runtime.database.job_record(job.id)

        assert job.state == "failed"
        assert job.stages[0].state == "failed"
        assert job.result.error == "driver exploded"
        assert record is not None
        assert not Path(record["worktree"]).exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_queued_cancellation_cleans_and_remains_retryable(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    project = runtime.register_project(str(root))
    submission = await runtime.submit(
        project.id,
        "read",
        {"prompt": "inspect"},
    )
    record = runtime.database.job_record(submission.job_id)
    assert record is not None

    cancelled = runtime.cancel(submission.job_id)

    assert cancelled.state == "cancelled"
    assert not Path(record["worktree"]).exists()

    await runtime.start()
    try:
        retried = await runtime.retry(submission.job_id)
        succeeded = await runtime.wait(retried.job_id, 10)
        assert succeeded.state == "succeeded"
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
        "read",
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
async def test_startup_cleans_abandoned_running_worktree(tmp_path) -> None:
    root = _repository(tmp_path)
    home = tmp_path / "home"
    abandoned = Runtime(_config(home))
    project = abandoned.register_project(str(root))
    submission = await abandoned.submit(
        project.id,
        "read",
        {"prompt": "wait"},
    )
    record = abandoned.database.job_record(submission.job_id)
    assert record is not None
    abandoned.database.set_job_state(submission.job_id, "running")
    abandoned.database.set_stage_state(submission.job_id, "execute", "running")
    abandoned.database.close()

    runtime = Runtime(_config(home))
    await runtime.start()
    try:
        interrupted = runtime.database.job(submission.job_id)
        assert interrupted is not None
        assert interrupted.state == "interrupted"
        assert not Path(record["worktree"]).exists()
    finally:
        await runtime.close()


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
            "write",
            {
                "prompt": "implement",
                "commit_message": "feat: add result",
            },
            "phase/implementer",
        )
        implementation_job = await runtime.wait(implementation.job_id, 10)
        review = await runtime.submit(
            project.id,
            "read",
            {"prompt": "review"},
            "phase/reviewer",
            implementation_job.id,
        )
        review_job = await runtime.wait(review.job_id, 10)

        assert review_job.base_commit == implementation_job.result.commit
        assert review_job.integration_base == implementation_job.integration_base
        assert not Path(runtime.database.job_record(implementation_job.id)["worktree"]).exists()
        assert _git(root, "log", "-1", "--format=%s", implementation_job.result.commit) == "feat: add result"
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
            "write",
            {"prompt": "implement"},
        )
        implementation_job = await runtime.wait(implementation.job_id, 10)
        fix = await runtime.submit(
            project.id,
            "write",
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
