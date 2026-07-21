from __future__ import annotations

import asyncio
import json
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
    TargetConfig,
    TargetSelection,
    load_config,
    load_project_config,
    load_task_guide,
)
from openmcp.backends._shell import ShellCommandCancelled, stream_shell_command_lines
from openmcp.database import Database
from openmcp.drivers import DriverResult
from openmcp.models import JobView, StageView
from openmcp.overlays import OverlayError, load_overlay_rules
from openmcp.planning import (
    parse_execution_plan,
    resolve_execution_plan,
    target_execution_key,
)
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
    selection = TargetSelection(
        targets=tuple(target.id for target in resolved_targets),
        max_attempts=len(resolved_targets),
    )
    return DaemonConfig(
        home=home,
        max_jobs=2,
        targets=resolved_targets,
        profiles={
            "balanced": {
                "implement": selection,
                "review": selection,
                "consult": selection,
            }
        },
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
workflows = ["implement"]
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
                    "left": {"mode": "write", "role": "implement", "prompt": "left"},
                    "right": {"mode": "write", "role": "implement", "prompt": "right"},
                },
            }
        )


def test_workflow_renders_dependency_outputs(tmp_path) -> None:
    workflow = parse_workflow(
        {
            "version": 1,
            "name": "implementation-review",
            "inputs": {"task": {"required": True}},
            "stages": {
                "implement": {
                    "mode": "write",
                    "role": "implement",
                    "prompt": "${inputs.task}",
                },
                "review": {
                    "needs": ["implement"],
                    "mode": "read",
                    "role": "review",
                    "prompt": "Review ${stages.implement.text} in ${project.root}",
                },
            },
        }
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
            "quality": {"mode": "read", "role": "review", "prompt": "quality"},
            "tests": {"mode": "read", "role": "review", "prompt": "tests"},
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
                    "mode": "read",
                    "role": "forge",
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
                    "first": {"mode": "read", "role": "forge", "prompt": "first"},
                    "second": {
                        "mode": "read",
                        "role": "forge",
                        "prompt": "${stages.first.text}",
                    },
                },
            }
        )


def test_builtin_workflows_express_intent() -> None:
    implement = load_workflow("implement")
    review = load_workflow("review")
    consult = load_workflow("consult")

    assert (implement.stages[0].mode, implement.stages[0].role) == (
        "write",
        "implement",
    )
    assert (review.stages[0].mode, review.stages[0].role) == ("read", "review")
    assert (consult.stages[0].mode, consult.stages[0].role) == (
        "read",
        "consult",
    )
    assert set(implement.inputs) == {"prompt", "commit_message"}
    assert set(review.inputs) == {"prompt"}
    assert set(consult.inputs) == {"prompt"}


def test_only_builtin_workflows_are_available() -> None:
    for name in ("read", "write", "custom"):
        with pytest.raises(ValueError, match="Unknown workflow"):
            load_workflow(name)


def test_workflow_stage_requires_explicit_role() -> None:
    with pytest.raises(ValueError, match="requires a role"):
        parse_workflow(
            {
                "version": 1,
                "name": "invalid",
                "stages": {"execute": {"mode": "read", "prompt": "inspect"}},
            }
        )


def test_workflow_reads_saved_route_field() -> None:
    workflow = parse_workflow(
        {
            "version": 1,
            "name": "review",
            "stages": {
                "execute": {
                    "mode": "read",
                    "route": "review",
                    "prompt": "inspect",
                }
            },
        }
    )

    assert workflow.stages[0].role == "review"


def test_workflow_stage_requires_explicit_mode() -> None:
    with pytest.raises(ValueError, match="requires a mode"):
        parse_workflow(
            {
                "version": 1,
                "name": "invalid",
                "stages": {"execute": {"role": "consult", "prompt": "inspect"}},
            }
        )


def test_task_guide_prefers_project_then_global(tmp_path) -> None:
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    (project / ".openmcp").mkdir(parents=True)
    global_path = home / "task_guide.json"
    project_path = project / ".openmcp" / "task_guide.json"
    global_path.write_text(
        '{"version": 1, "recommendations": [{"profile": "balanced"}]}',
        encoding="utf-8",
    )
    project_path.write_text(
        '{"version": 1, "recommendations": [{"profile": "quality"}]}',
        encoding="utf-8",
    )

    project_guide = load_task_guide(home, project)
    project_path.unlink()
    global_guide = load_task_guide(home, project)

    assert project_guide["recommendations"][0]["profile"] == "quality"
    assert global_guide["recommendations"][0]["profile"] == "balanced"


def test_task_guide_requires_nonempty_json_object(tmp_path) -> None:
    with pytest.raises(ValueError, match="Missing task guide"):
        load_task_guide(tmp_path)

    (tmp_path / "task_guide.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="non-empty JSON object"):
        load_task_guide(tmp_path)


def test_task_guide_normalizes_legacy_file(tmp_path) -> None:
    (tmp_path / "task_routes.json").write_text(
        """{
  "columns": ["workflow", "routing_profile"],
  "routes": [{"workflow": "review", "routing_profile": "quality"}]
}""",
        encoding="utf-8",
    )

    guide = load_task_guide(tmp_path)

    assert guide == {
        "columns": ["workflow", "profile"],
        "recommendations": [{"workflow": "review", "profile": "quality"}],
    }


@pytest.mark.asyncio
async def test_task_guide_tool_uses_registered_project_guide(tmp_path) -> None:
    from openmcp.server import task_guide

    root = _repository(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    (home / "task_guide.json").write_text(
        '{"recommendations": [{"profile": "balanced"}]}',
        encoding="utf-8",
    )
    directory = root / ".openmcp"
    directory.mkdir()
    (directory / "task_guide.json").write_text(
        '{"recommendations": [{"profile": "quality"}]}',
        encoding="utf-8",
    )
    _git(root, "add", ".openmcp/task_guide.json")
    _git(root, "commit", "-m", "add task guide")
    runtime = Runtime(_config(home))
    try:
        project = runtime.register_project(str(root))
        ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=runtime)
        )

        result = await task_guide("Implement feature", ctx, project.id)

        assert result.guide["recommendations"][0]["profile"] == "quality"
    finally:
        runtime.database.close()


@pytest.mark.parametrize(
    ("constraint", "message"),
    (
        ("projects.alias", "Project alias already exists"),
        ("projects.root", "Project root already registered"),
    ),
)
def test_register_project_reports_integrity_constraint(
    monkeypatch,
    tmp_path,
    constraint,
    message,
) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))

    def reject_project(**_kwargs) -> None:
        raise sqlite3.IntegrityError(f"UNIQUE constraint failed: {constraint}")

    monkeypatch.setattr(runtime.database, "upsert_project", reject_project)
    try:
        with pytest.raises(ValueError, match=message):
            runtime.register_project(str(root), "shared")
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_project_resources_expose_semantic_workflows(tmp_path) -> None:
    from openmcp.server import project_profiles_resource, workflows_resource

    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    try:
        project = runtime.register_project(str(root))
        custom_workflows = root / ".openmcp" / "workflows"
        custom_workflows.mkdir(parents=True)
        (custom_workflows / "custom.yaml").write_text(
            "name: custom\n",
            encoding="utf-8",
        )
        ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=runtime)
        )

        profiles = json.loads(
            await project_profiles_resource(project.id, ctx)
        )
        workflows = json.loads(await workflows_resource(project.id, ctx))

        assert profiles == {
            "default": "balanced",
            "available": ["balanced"],
        }
        assert workflows == ["consult", "implement", "review"]
    finally:
        runtime.database.close()


def test_default_consultant_and_reviewer_are_isolated_pi_targets(tmp_path) -> None:
    config = load_config(tmp_path / "missing.toml")
    targets = {target.id: target for target in config.targets}

    for target_id in ("sage-primary", "sentinel-primary"):
        target = targets[target_id]
        assert target.backend == "pi"
        assert target.model == "gpt-5.6-sol"
        assert target.isolated
        assert target.read_only
        assert target.system_prompt
    assert config.profiles["balanced"]["review"].targets == (
        "sentinel-primary",
    )
    assert config.profiles["balanced"]["consult"].targets == ("sage-primary",)


@pytest.mark.parametrize(
    ("workflow_name", "target_ids"),
    (
        ("implement", ("forge-primary", "canvas-primary")),
        ("review", ("sentinel-primary",)),
        ("consult", ("sage-primary",)),
    ),
)
def test_default_builtins_resolve_targets(
    tmp_path,
    workflow_name: str,
    target_ids: tuple[str, ...],
) -> None:
    config = load_config(tmp_path / "missing.toml")
    workflow = load_workflow(workflow_name)

    plan = resolve_execution_plan(workflow, config, "balanced")

    assert plan.selection(workflow_name).targets == target_ids


def test_saved_execution_plan_uses_legacy_selection_keys() -> None:
    plan = parse_execution_plan(
        {
            "routing_profile": "balanced",
            "role_routes": {"review": "sentinel"},
            "routes": [
                {
                    "id": "sentinel",
                    "targets": ["reviewer"],
                }
            ],
            "targets": [
                {
                    "id": "reviewer",
                    "backend": "pi",
                    "profile": "legacy-backend-profile",
                }
            ],
        }
    )

    assert plan.profile == "balanced"
    assert plan.selection("review").targets == ("reviewer",)
    assert plan.target("reviewer").backend_profile == "legacy-backend-profile"


def test_custom_target_defaults_support_all_semantic_workflows(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[[targets]]
id = "primary"
backend = "codex"
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert set(config.targets[0].capabilities) >= {
        "code",
        "review",
        "consult",
    }
    for workflow_name in ("implement", "review", "consult"):
        plan = resolve_execution_plan(
            load_workflow(workflow_name),
            config,
            "balanced",
        )
        assert [target.id for target in plan.targets] == ["primary"]


def test_default_profile_requires_capable_targets(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[[targets]]
id = "implement-only"
backend = "codex"
capabilities = ["code"]
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Default profile workflow 'review' has no capable targets",
    ):
        load_config(path)


def test_config_loads_profile_overlays(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[daemon]
default_profile = "quality"

[[targets]]
id = "premium"
backend = "codex"
backend_profile = "mcp_execution"
args = ["--ephemeral", "--color", "never"]
capabilities = ["code", "review", "consult"]

[profiles.quality]
implement = "premium"
review = "premium"
consult = "premium"
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.default_profile == "quality"
    assert config.targets[0].backend_profile == "mcp_execution"
    assert config.targets[0].args == ("--ephemeral", "--color", "never")
    assert {
        workflow: selection.targets
        for workflow, selection in config.profiles["quality"].items()
    } == {
        "implement": ("premium",),
        "review": ("premium",),
        "consult": ("premium",),
    }


def test_profile_maps_workflows_directly_to_targets(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[[targets]]
id = "primary"
backend = "codex"

[[targets]]
id = "backup"
backend = "agy"

[profiles.balanced]
implement = ["primary", "backup"]
review = "primary"
consult = { targets = ["primary", "backup"], max_attempts = 1, timeout_s = 90 }
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.profiles["balanced"]["implement"] == TargetSelection(
        ("primary", "backup"),
        max_attempts=2,
    )
    assert config.profiles["balanced"]["review"] == TargetSelection(
        ("primary",),
        max_attempts=1,
    )
    assert config.profiles["balanced"]["consult"] == TargetSelection(
        ("primary", "backup"),
        max_attempts=1,
        timeout_s=90,
    )


def test_profile_rejects_target_without_workflow_capability(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[[targets]]
id = "implementer"
backend = "codex"
capabilities = ["code"]

[profiles.balanced]
implement = "implementer"
review = "implementer"
consult = "implementer"
""",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="workflow 'review' requires capability 'review'",
    ):
        load_config(path)


def test_config_reads_legacy_selection_names(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[daemon]
default_routing_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
profile = "legacy-backend-profile"

[[routes]]
id = "all"
targets = ["primary"]

[routing_profiles.balanced]
implement = "all"
review = "all"
consult = "all"
""",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.default_profile == "balanced"
    assert config.targets[0].backend_profile == "legacy-backend-profile"
    assert config.profiles["balanced"]["implement"].targets == ("primary",)


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


def test_config_requires_every_builtin_workflow(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """
[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not map built-in workflows"):
        load_config(path)


def test_project_config_rejects_unknown_profile_target(tmp_path) -> None:
    project = tmp_path / "project"
    (project / ".openmcp").mkdir(parents=True)
    (project / ".openmcp" / "config.toml").write_text(
        """
[profiles.balanced]
review = "missing"
""",
        encoding="utf-8",
    )
    selection = TargetSelection(("primary",), max_attempts=1)
    base = DaemonConfig(
        home=tmp_path / "home",
        targets=(TargetConfig(id="primary", backend="codex"),),
        profiles={
            "balanced": {
                "implement": selection,
                "review": selection,
                "consult": selection,
            }
        },
    )

    with pytest.raises(ValueError, match="workflow 'review' has invalid targets"):
        load_project_config(project, base)


def test_project_config_overlays_profiles(tmp_path) -> None:
    project = tmp_path / "project"
    (project / ".openmcp").mkdir(parents=True)
    (project / ".openmcp" / "config.toml").write_text(
        """
[project]
default_profile = "quality"

[profiles.quality]
review = "premium"
""",
        encoding="utf-8",
    )
    primary = TargetSelection(("primary",), max_attempts=1)
    base = DaemonConfig(
        home=tmp_path / "home",
        targets=(
            TargetConfig(id="primary", backend="codex"),
            TargetConfig(id="premium", backend="agy"),
        ),
        profiles={
            "balanced": {
                "implement": primary,
                "review": primary,
                "consult": primary,
            }
        },
    )

    project_config = load_project_config(project, base)

    assert project_config.default_profile == "quality"
    assert {
        workflow: selection.targets
        for workflow, selection in project_config.profiles["quality"].items()
    } == {
        "implement": ("primary",),
        "review": ("premium",),
        "consult": ("primary",),
    }
    assert base.default_profile == "balanced"


def test_project_legacy_profile_resolves_global_custom_route(
    tmp_path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("OPENMCP_HOME", str(home))
    global_path = home / "config.toml"
    global_path.write_text(
        """
[daemon]
default_profile = "quality"

[[targets]]
id = "primary"
backend = "codex"

[[targets]]
id = "strict-reviewer"
backend = "pi"
capabilities = ["review"]

[[routes]]
id = "strict-global"
targets = ["strict-reviewer"]

[profiles.quality]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    project = tmp_path / "project"
    (project / ".openmcp").mkdir(parents=True)
    (project / ".openmcp" / "config.toml").write_text(
        """
[routing_profiles.quality]
review = "strict-global"
""",
        encoding="utf-8",
    )

    config = load_project_config(project, load_config(global_path))

    assert config.profiles["quality"]["review"].targets == ("strict-reviewer",)
    assert config.profiles["quality"]["implement"].targets == ("primary",)
    assert config.profiles["quality"]["consult"].targets == ("primary",)


def test_project_config_rejects_daemon_and_target_overrides(tmp_path) -> None:
    project = tmp_path / "project"
    (project / ".openmcp").mkdir(parents=True)
    (project / ".openmcp" / "config.toml").write_text(
        "[daemon]\nmax_jobs = 1\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported project config sections"):
        load_project_config(project, _config(tmp_path / "home"))


@pytest.mark.asyncio
async def test_client_doctor_tool_is_read_only(tmp_path) -> None:
    from openmcp.server import doctor

    root = _repository(tmp_path)
    validation = await doctor(str(root))

    assert validation.root == root.as_posix()
    assert "without mutations" in validation.instructions
    assert "PASS or FAIL" in validation.instructions
    assert not (root / ".openmcp").exists()


@pytest.mark.asyncio
async def test_daemon_management_tools_delegate_to_runtime() -> None:
    from openmcp.models import DaemonReloadResult, DaemonStatusResult
    from openmcp.server import reload, status

    status_result = DaemonStatusResult(
        status="running",
        workers=2,
        active_jobs=1,
        queued_jobs=3,
    )
    reload_result = DaemonReloadResult(
        success=True,
        targets=4,
        profiles=2,
    )

    class RuntimeStub:
        def status(self) -> DaemonStatusResult:
            return status_result

        def reload(self) -> DaemonReloadResult:
            return reload_result

    ctx = SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=RuntimeStub()),
    )

    assert await status(ctx) is status_result
    assert await reload(ctx) is reload_result


@pytest.mark.asyncio
async def test_submission_uses_project_profile_override(tmp_path) -> None:
    root = _repository(tmp_path)
    directory = root / ".openmcp"
    directory.mkdir()
    (directory / "config.toml").write_text(
        """
[profiles.balanced]
consult = "project-target"
""",
        encoding="utf-8",
    )
    _git(root, "add", ".openmcp/config.toml")
    _git(root, "commit", "-m", "add project selection")
    targets = (
        TargetConfig(id="global-target", backend="codex"),
        TargetConfig(id="project-target", backend="agy"),
    )
    global_selection = TargetSelection(("global-target",), max_attempts=1)
    runtime = Runtime(
        DaemonConfig(
            home=tmp_path / "home",
            max_jobs=1,
            targets=targets,
            profiles={
                "balanced": {
                    "implement": global_selection,
                    "review": global_selection,
                    "consult": global_selection,
                }
            },
        )
    )
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "consult",
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
capabilities = ["code", "review", "consult"]

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
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
        "consult",
        {"prompt": "first"},
        context_key="shared",
    )
    write_config("agy")
    await runtime.start()
    try:
        await runtime.wait(first.job_id, 10)

        second = await runtime.submit(
            project.id,
            "consult",
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


def test_runtime_reload_refreshes_catalog_and_reports_restart_settings(
    tmp_path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    path = home / "config.toml"
    home.mkdir()
    monkeypatch.setenv("OPENMCP_HOME", str(home))
    path.write_text("[daemon]\nmax_jobs = 1\n", encoding="utf-8")
    runtime = Runtime(load_config(path))
    try:
        path.write_text(
            """[daemon]
max_jobs = 2

[[targets]]
id = "only"
backend = "pi"

[profiles.balanced]
implement = "only"
review = "only"
consult = "only"
""",
            encoding="utf-8",
        )

        first = runtime.reload()
        second = runtime.reload()

        assert first.success is True
        assert first.targets == 1
        assert "max_jobs" in first.restart_required
        assert second.restart_required == first.restart_required
        assert [target.id for target in runtime.catalog.targets] == ["only"]
        assert runtime.config.max_jobs == 1
    finally:
        runtime.database.close()


def test_database_migrates_execution_state(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    original = Database(path)
    original.upsert_project(
        project_id="project",
        alias="project",
        root="/project",
        head_commit="base",
        clean=True,
    )
    original.create_job(
        job_id="job",
        project_id="project",
        workflow="review",
        profile="quality",
        workflow_json="{}",
        inputs={},
        context_key="review",
        parent_job_id="",
        base_commit="base",
        integration_base="base",
        branch="openmcp/job",
        worktree="/worktree",
        stages=(("execute", 0, "read"),),
    )
    original.close()
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE jobs RENAME COLUMN profile TO routing_profile")
    connection.execute(
        "ALTER TABLE jobs ADD COLUMN result_text TEXT NOT NULL DEFAULT ''"
    )
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
    migrated = database.job_record("job")
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

    assert migrated is not None
    assert migrated["profile"] == "quality"
    assert {"profile", "routing_profile"}.issubset(columns)
    assert "execution_plan_json" in columns
    assert "result_stage" in columns
    assert "result_text" in columns
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
        workflow="consult",
        profile="balanced",
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
        profile="balanced",
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
    database.set_job_state("job", "succeeded")

    compact = database.job("job", include_stage_outputs=False)
    detailed = database.job("job", include_stage_outputs=True)

    assert compact is not None
    assert detailed is not None
    assert compact.result.text == "reviewed"
    assert detailed.result.text == "reviewed"
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
            workflow="consult",
            profile="balanced",
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
            self.wait_calls: list[tuple[str, int, bool]] = []

        async def wait(
            self,
            job_id: str,
            timeout_s: int,
            *,
            include_stage_outputs: bool,
        ) -> JobView:
            self.wait_calls.append((job_id, timeout_s, include_stage_outputs))
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
    assert runtime.wait_calls == [("job", 12, False)]
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
        "status",
        "reload",
        "doctor",
        "project_register",
        "task_guide",
        "job_submit",
        "job_wait",
        "job_cancel",
        "job_retry",
        "job_integrate",
    }
    assert "parent_job_id" in tools["job_submit"].inputSchema["properties"]
    assert "profile" in tools["job_submit"].inputSchema["properties"]
    assert "include_stage_outputs" in tools["job_wait"].inputSchema["properties"]
    assert set(tools["task_guide"].inputSchema["properties"]) == {
        "task",
        "project_id",
    }
    assert tools["status"].inputSchema["properties"] == {}
    assert tools["reload"].inputSchema["properties"] == {}
    assert set(tools["doctor"].inputSchema["properties"]) == {"path"}
    assert resources == {
        "openmcp://projects",
        "openmcp://targets",
        "openmcp://profiles",
    }
    assert "openmcp://projects/{project_id}/jobs" in templates
    assert "openmcp://projects/{project_id}/profiles" in templates


@pytest.mark.asyncio
async def test_implement_job_isolated_then_integrated(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root), "sample")
        submission = await runtime.submit(
            project.id,
            "implement",
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
async def test_review_job_succeeds_without_legacy_role_rewrite(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = FakeDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root), "sample")
        submission = await runtime.submit(
            project.id,
            "review",
            {"prompt": "review the change"},
        )
        job = await runtime.wait(submission.job_id, 10)

        assert job.state == "succeeded"
        assert job.result.error == ""
        assert job.result.text == "response from primary"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_implement_job_integrates_project_overlay_patterns(tmp_path) -> None:
    root = _overlay_repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = OverlayDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "implement",
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
            "implement",
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
            "implement",
            {"prompt": "first overlay update"},
        )
        parent = await runtime.wait(parent_submission.job_id, 10)
        child_submission = await runtime.submit(
            project.id,
            "implement",
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
workflows = ["implement"]
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
                "implement",
                {"prompt": "update development files"},
            )

        assert _git(root, "branch", "--list", "openmcp/*") == ""
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_consult_job_discards_filesystem_changes(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = FakeDrivers(mutate=True)
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "consult",
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


def test_target_selection_prefers_available_capacity(tmp_path) -> None:
    targets = (
        TargetConfig(id="primary", backend="codex", max_concurrency=1),
        TargetConfig(id="backup", backend="agy", max_concurrency=1),
    )
    runtime = Runtime(_config(tmp_path / "home", targets))
    runtime.drivers = FakeDrivers()
    plan = resolve_execution_plan(load_workflow("consult"), runtime.config, "balanced")
    runtime._target_active[target_execution_key(targets[0])] = 1

    selected = runtime._select_target(
        plan.selection("consult").targets,
        plan,
        set(),
    )

    assert selected == targets[1]

    runtime._target_active[target_execution_key(targets[1])] = 1
    saturated = runtime._select_target(
        plan.selection("consult").targets,
        plan,
        set(),
    )

    assert saturated == targets[0]
    runtime.database.close()


@pytest.mark.asyncio
async def test_profile_targets_fail_over_and_preserve_context_session(tmp_path) -> None:
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
            "consult",
            {"prompt": "first"},
            "shared",
        )
        first_job = await runtime.wait(first.job_id, 10)
        assert first_job.state == "succeeded"
        assert first_job.stages[0].target_id == "healthy"

        second = await runtime.submit(
            project.id,
            "consult",
            {"prompt": "second"},
            "shared",
        )
        second_job = await runtime.wait(second.job_id, 10)
        assert second_job.state == "succeeded"
        assert drivers.sessions[-1] == "session-healthy"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_job_selects_configured_profile(tmp_path) -> None:
    root = _repository(tmp_path)
    targets = (
        TargetConfig(
            id="economy",
            backend="codex",
            model="economy-model",
            backend_profile="economy-profile",
            reasoning="low",
        ),
        TargetConfig(
            id="premium",
            backend="codex",
            model="quality-model",
            backend_profile="quality-profile",
            reasoning="high",
        ),
    )
    economy = TargetSelection(("economy",), max_attempts=1)
    quality = TargetSelection(("premium",), max_attempts=1)
    config = DaemonConfig(
        home=tmp_path / "home",
        targets=targets,
        profiles={
            "cost": {
                "implement": economy,
                "review": economy,
                "consult": economy,
            },
            "quality": {
                "implement": quality,
                "review": quality,
                "consult": quality,
            },
        },
        default_profile="cost",
    )
    runtime = Runtime(config)
    drivers = FakeDrivers()
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        submission = await runtime.submit(
            project.id,
            "consult",
            {"prompt": "inspect"},
            profile="quality",
        )
        job = await runtime.wait(submission.job_id, 10)

        assert job.profile == "quality"
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
            "implement",
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
            "consult",
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
            "implement",
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
        "consult",
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
        "consult",
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
        "consult",
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
            "implement",
            {
                "prompt": "implement",
                "commit_message": "feat: add result",
            },
            "phase/implementer",
        )
        implementation_job = await runtime.wait(implementation.job_id, 10)
        review = await runtime.submit(
            project.id,
            "review",
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
async def test_integrating_fix_chain_cleans_implementation_jobs(tmp_path) -> None:
    root = _repository(tmp_path)
    runtime = Runtime(_config(tmp_path / "home"))
    runtime.drivers = ChangingDrivers()
    await runtime.start()
    try:
        project = runtime.register_project(str(root))
        implementation = await runtime.submit(
            project.id,
            "implement",
            {"prompt": "implement"},
        )
        implementation_job = await runtime.wait(implementation.job_id, 10)
        fix = await runtime.submit(
            project.id,
            "implement",
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
