from __future__ import annotations

import pytest

from openmcp.config import load_config
from openmcp.planning import execution_plan_data, parse_execution_plan, resolve_execution_plan
from openmcp.workflows import get_workflow
from tests.orchestration_helpers import config


def test_plan_snapshots_one_workflow_selection(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    data = execution_plan_data(plan)
    assert data["profile"] == "balanced"
    assert data["workflow"] == "implement"
    assert data["selection"] == {"targets": ["primary"], "max_attempts": 1, "timeout_s": 0}
    assert "capabilities" not in data["targets"][0]
    assert parse_execution_plan(data) == plan


def test_other_plan_snapshot_round_trips(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    plan = resolve_execution_plan(get_workflow("other"), catalog, "balanced")
    data = execution_plan_data(plan)

    assert data["workflow"] == "other"
    assert parse_execution_plan(data) == plan


def test_legacy_plan_target_capabilities_still_parse(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    data = execution_plan_data(plan)
    data["targets"][0]["capabilities"] = ["code"]

    assert parse_execution_plan(data) == plan


def test_plan_rejects_legacy_multi_workflow_shape(tmp_path) -> None:
    data = execution_plan_data(resolve_execution_plan(get_workflow("review"), config(tmp_path / "home"), "balanced"))
    data.pop("selection")
    data["workflows"] = {"review": "primary"}
    with pytest.raises(ValueError, match="selection"):
        parse_execution_plan(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("backend", "unknown"),
        ("max_concurrency", 0),
        ("isolated", "false"),
        ("args", [1]),
    ],
)
def test_plan_rejects_invalid_persisted_targets(tmp_path, field, value) -> None:
    data = execution_plan_data(
        resolve_execution_plan(get_workflow("review"), config(tmp_path / "home"), "balanced")
    )
    data["targets"][0][field] = value

    with pytest.raises(ValueError, match="invalid target"):
        parse_execution_plan(data)


def test_plan_rejects_duplicate_target_identifiers(tmp_path) -> None:
    data = execution_plan_data(
        resolve_execution_plan(get_workflow("review"), config(tmp_path / "home"), "balanced")
    )
    data["targets"].append(dict(data["targets"][0]))

    with pytest.raises(ValueError, match="unique"):
        parse_execution_plan(data)


def test_partial_profile_rejects_only_unmapped_workflow_at_plan_resolution(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "consult-only"

[[targets]]
id = "primary"
backend = "codex"
capabilities = ["code", "review", "consult"]

[profiles.consult-only]
consult = "primary"
""",
        encoding="utf-8",
    )
    catalog = load_config(path)

    assert resolve_execution_plan(get_workflow("consult"), catalog, "consult-only")
    with pytest.raises(ValueError, match="does not map workflow 'implement'"):
        resolve_execution_plan(get_workflow("implement"), catalog, "consult-only")
    with pytest.raises(ValueError, match="does not map workflow 'other'"):
        resolve_execution_plan(get_workflow("other"), catalog, "consult-only")


def test_native_pi_verified_read_only_capability_is_narrow() -> None:
    from openmcp.config import TargetConfig
    from openmcp.drivers import DriverRegistry

    assert DriverRegistry.supports_verified_read_only(
        TargetConfig(id="safe", backend="pi", isolated=True, read_only=True)
    )
    unsafe_targets = (
        TargetConfig(id="writable", backend="pi", isolated=True),
        TargetConfig(id="unisolated", backend="pi", read_only=True),
        TargetConfig(id="advisory", backend="codex", isolated=True, read_only=True),
        TargetConfig(id="unknown", backend="unknown", isolated=True, read_only=True),
        TargetConfig(id="custom-arg", backend="pi", isolated=True, read_only=True, args=("--verbose",)),
        TargetConfig(id="custom-arg-pair", backend="pi", isolated=True, read_only=True, args=("--tools", "read")),
        TargetConfig(id="custom-system-prompt", backend="pi", isolated=True, read_only=True, args=("--system-prompt", "read only")),
        TargetConfig(id="custom-explicit-extension", backend="pi", isolated=True, read_only=True, args=("--extension", "ignored.ts")),
    )
    assert all(not DriverRegistry.supports_verified_read_only(target) for target in unsafe_targets)


@pytest.mark.parametrize("workflow", ["consult", "review", "implement", "other"])
def test_access_mode_requires_every_saved_fallback_target_regardless_of_workflow(workflow: str) -> None:
    from openmcp.config import TargetConfig, TargetSelection
    from openmcp.planning import ExecutionPlan, derive_access_mode
    from openmcp.workflows import get_workflow

    safe = TargetConfig(id="safe", backend="pi", isolated=True, read_only=True)
    unsafe = TargetConfig(id="unsafe", backend="pi", isolated=True, read_only=True, args=("--verbose",))
    plan = ExecutionPlan(
        profile="balanced",
        workflow=get_workflow(workflow),
        selection=TargetSelection(("safe", "unsafe"), max_attempts=1),
        targets=(safe, unsafe),
    )

    assert derive_access_mode(plan) == "exclusive"


def test_access_mode_with_all_qualified_fallbacks_is_parallel_read() -> None:
    from openmcp.config import TargetConfig, TargetSelection
    from openmcp.planning import ExecutionPlan, derive_access_mode
    from openmcp.workflows import get_workflow

    targets = (
        TargetConfig(id="primary", backend="pi", isolated=True, read_only=True),
        TargetConfig(id="fallback", backend="pi", isolated=True, read_only=True),
    )
    plan = ExecutionPlan(
        profile="balanced",
        workflow=get_workflow("review"),
        selection=TargetSelection(("primary", "fallback"), max_attempts=1),
        targets=targets,
    )

    assert derive_access_mode(plan) == "parallel_read"


def test_unsafe_primary_target_derives_exclusive() -> None:
    from openmcp.config import TargetConfig, TargetSelection
    from openmcp.planning import ExecutionPlan, derive_access_mode
    from openmcp.workflows import get_workflow

    targets = (
        TargetConfig(id="primary", backend="pi", isolated=True, read_only=True, args=("--verbose",)),
        TargetConfig(id="fallback", backend="pi", isolated=True, read_only=True),
    )
    plan = ExecutionPlan(
        profile="balanced",
        workflow=get_workflow("consult"),
        selection=TargetSelection(("primary", "fallback"), max_attempts=1),
        targets=targets,
    )

    assert derive_access_mode(plan) == "exclusive"


def test_access_mode_uses_immutable_snapshot_targets_and_round_trips(tmp_path) -> None:
    from dataclasses import replace

    from openmcp.config import TargetConfig, TargetSelection
    from openmcp.planning import ExecutionPlan, derive_access_mode
    from openmcp.workflows import get_workflow

    plan = ExecutionPlan(
        profile="balanced",
        workflow=get_workflow("review"),
        selection=TargetSelection(("primary",), max_attempts=1),
        targets=(TargetConfig(id="primary", backend="pi", isolated=True, read_only=True),),
    )
    snapshot = parse_execution_plan(execution_plan_data(plan))
    replacement_catalog_target = replace(snapshot.target("primary"), read_only=False)
    replacement_catalog_plan = replace(snapshot, targets=(replacement_catalog_target,))

    assert replacement_catalog_target.read_only is False
    assert derive_access_mode(snapshot) == "parallel_read"
    assert derive_access_mode(replacement_catalog_plan) == "exclusive"
    assert parse_execution_plan(execution_plan_data(snapshot)) == snapshot


def test_otherwise_valid_custom_args_round_trip_and_remain_exclusive() -> None:
    from openmcp.config import TargetConfig, TargetSelection
    from openmcp.planning import ExecutionPlan, derive_access_mode
    from openmcp.workflows import get_workflow

    target = TargetConfig(
        id="native-with-custom-args",
        backend="pi",
        isolated=True,
        read_only=True,
        args=("--verbose", "--system-prompt", "advisory only"),
    )
    plan = ExecutionPlan(
        profile="balanced",
        workflow=get_workflow("review"),
        selection=TargetSelection((target.id,), max_attempts=1),
        targets=(target,),
    )
    restored = parse_execution_plan(execution_plan_data(plan))

    assert restored.target(target.id).args == target.args
    assert derive_access_mode(restored) == "exclusive"


@pytest.mark.parametrize(
    "native_args",
    [
        ("--export", "export.html"),
        ("install", "example-source"),
        ("--tools", "read,bash,edit,write"),
    ],
)
def test_pi_eager_write_and_raw_tool_args_round_trip_as_exclusive(native_args: tuple[str, ...]) -> None:
    from openmcp.config import TargetConfig, TargetSelection
    from openmcp.planning import ExecutionPlan, derive_access_mode
    from openmcp.workflows import get_workflow

    target = TargetConfig(
        id="pi-with-native-args",
        backend="pi",
        isolated=True,
        read_only=True,
        args=native_args,
    )
    plan = ExecutionPlan(
        profile="balanced",
        workflow=get_workflow("review"),
        selection=TargetSelection((target.id,), max_attempts=1),
        targets=(target,),
    )
    restored = parse_execution_plan(execution_plan_data(plan))

    assert restored.target(target.id).args == native_args
    assert derive_access_mode(restored) == "exclusive"


def test_empty_programmatic_selection_derives_exclusive() -> None:
    from openmcp.config import TargetSelection
    from openmcp.planning import ExecutionPlan, derive_access_mode
    from openmcp.workflows import get_workflow

    plan = ExecutionPlan(
        profile="balanced",
        workflow=get_workflow("consult"),
        selection=TargetSelection((), max_attempts=1),
        targets=(),
    )

    assert derive_access_mode(plan) == "exclusive"
