from __future__ import annotations

import pytest

from openmcp.config import load_config
from openmcp.planning import execution_plan_data, parse_execution_plan, resolve_execution_plan, target_execution_key
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


def test_plan_instruction_round_trips(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    plan = resolve_execution_plan(
        get_workflow("implement"), catalog, "balanced", instruction="follow the plan"
    )
    data = execution_plan_data(plan)
    assert data["instruction"] == "follow the plan"
    assert parse_execution_plan(data) == plan


def test_legacy_plan_without_instruction_defaults_to_empty(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    data = execution_plan_data(
        resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    )
    data.pop("instruction")

    assert parse_execution_plan(data).instruction == ""


@pytest.mark.parametrize("value", [1, None, ["x"], {"a": "b"}])
def test_plan_rejects_non_string_instruction(tmp_path, value) -> None:
    data = execution_plan_data(
        resolve_execution_plan(get_workflow("review"), config(tmp_path / "home"), "balanced")
    )
    data["instruction"] = value

    with pytest.raises(ValueError, match="instruction"):
        parse_execution_plan(data)


def test_target_execution_key_ignores_plan_instruction(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    plain = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    instructed = resolve_execution_plan(
        get_workflow("implement"), catalog, "balanced", instruction="follow the plan"
    )

    assert target_execution_key(plain.targets[0]) == target_execution_key(instructed.targets[0])


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
