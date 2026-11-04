from __future__ import annotations

import pytest

from refract.config import load_config
from refract.planning import execution_plan_data, parse_execution_plan, resolve_execution_plan
from refract.workflows import get_workflow
from tests.orchestration_helpers import config


def test_plan_snapshots_one_workflow_selection(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    data = execution_plan_data(plan)
    assert data["profile"] == "balanced"
    assert data["workflow"] == "implement"
    assert data["selection"] == {"targets": ["primary"], "timeout_s": 0}
    assert "capabilities" not in data["targets"][0]
    assert parse_execution_plan(data) == plan


def test_plan_context_window_persists_without_affecting_identity(tmp_path) -> None:
    from dataclasses import replace
    from refract.planning import target_execution_key
    catalog = config(tmp_path / "home")
    original = catalog.targets[0]
    configured = replace(original, context_window=200000)
    catalog = replace(catalog, targets=(configured,))
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    stored = execution_plan_data(plan)
    assert stored["targets"][0]["context_window"] == 200000
    assert parse_execution_plan(stored).targets[0].context_window == 200000
    assert target_execution_key(original) == target_execution_key(configured)
    stored["targets"][0].pop("context_window")
    assert parse_execution_plan(stored).targets[0].context_window is None


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "200000"])
def test_plan_rejects_invalid_persisted_context_window_values(tmp_path, value) -> None:
    catalog = config(tmp_path / "home")
    data = execution_plan_data(resolve_execution_plan(get_workflow("implement"), catalog, "balanced"))
    data["targets"][0]["context_window"] = value
    with pytest.raises(ValueError, match="invalid target"):
        parse_execution_plan(data)


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


def test_plan_environment_marker_is_structural_and_legacy_absence_is_empty(tmp_path) -> None:
    from dataclasses import replace

    catalog = config(tmp_path / "home")
    target = replace(catalog.targets[0], env={"LOCAL": "SYNTHETIC_TEMPLATE"})
    catalog = replace(catalog, targets=(target,))
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    data = execution_plan_data(plan)

    assert data["environment_targets"] == [target.id]
    assert "SYNTHETIC_TEMPLATE" not in str(data)
    restored = parse_execution_plan(data)
    assert restored.environment_targets == (target.id,)
    assert not restored.target(target.id).env
    data.pop("environment_targets")
    assert parse_execution_plan(data).environment_targets == ()


@pytest.mark.parametrize("marker", ["primary", ["primary", "primary"], ["unknown"], [1]])
def test_plan_rejects_invalid_environment_marker(tmp_path, marker) -> None:
    data = execution_plan_data(resolve_execution_plan(get_workflow("review"), config(tmp_path / "home"), "balanced"))
    data["environment_targets"] = marker
    with pytest.raises(ValueError, match="environment metadata"):
        parse_execution_plan(data)


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


def test_custom_target_args_round_trip_in_plan() -> None:
    from refract.config import TargetConfig, TargetSelection
    from refract.planning import ExecutionPlan

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
        selection=TargetSelection((target.id,)),
        targets=(target,),
    )
    restored = parse_execution_plan(execution_plan_data(plan))
    assert restored.target(target.id).args == target.args


@pytest.mark.parametrize(
    "native_args",
    [
        ("--export", "export.html"),
        ("install", "example-source"),
        ("--tools", "read,bash,edit,write"),
    ],
)
def test_pi_native_args_round_trip_in_plan(native_args: tuple[str, ...]) -> None:
    from refract.config import TargetConfig, TargetSelection
    from refract.planning import ExecutionPlan

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
        selection=TargetSelection((target.id,)),
        targets=(target,),
    )
    restored = parse_execution_plan(execution_plan_data(plan))
    assert restored.target(target.id).args == native_args


def test_plan_snapshots_retry_policy_and_survives_config_edits(tmp_path) -> None:
    from refract.config import RetryPolicy
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
retry = { attempts = 2, codes = ["rate_limit"], patterns = ["temporarily unavailable"] }

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    catalog = load_config(path)
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    policy = plan.target("primary").retry
    assert policy == RetryPolicy(2, ("rate_limit",), ("temporarily unavailable",))

    # Round trip serialization
    data = execution_plan_data(plan)
    assert data["targets"][0]["retry"] == {
        "attempts": 2,
        "codes": ["rate_limit"],
        "patterns": ["temporarily unavailable"],
    }
    restored = parse_execution_plan(data)
    assert restored == plan
    assert restored.target("primary").retry == policy

    # Config edits do not affect existing plan snapshot
    path.write_text(path.read_text(encoding="utf-8").replace("attempts = 2", "attempts = 5"), encoding="utf-8")
    assert load_config(path).targets[0].retry.attempts == 5
    assert plan.target("primary").retry == policy
    assert restored.target("primary").retry == policy


def test_plan_without_retry_defaults_to_no_retry(tmp_path) -> None:
    from refract.config import RetryPolicy
    catalog = config(tmp_path / "home")
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    data = execution_plan_data(plan)
    data["targets"][0].pop("retry", None)

    restored = parse_execution_plan(data)
    assert restored.target("primary").retry == RetryPolicy(attempts=0, codes=(), patterns=())


@pytest.mark.parametrize(
    ("mutate"),
    [
        lambda d: d["targets"][0].update(retry="not a dict"),
        lambda d: d["targets"][0].update(retry=2),
        lambda d: d["targets"][0]["retry"].update(attempts=-1),
        lambda d: d["targets"][0]["retry"].update(attempts="2"),
        lambda d: d["targets"][0]["retry"].update(attempts=True),
        lambda d: d["targets"][0]["retry"].update(codes="not a list"),
        lambda d: d["targets"][0]["retry"].update(codes=[123]),
        lambda d: d["targets"][0]["retry"].update(codes=[""]),
        lambda d: d["targets"][0]["retry"].update(patterns=[False]),
        lambda d: d["targets"][0]["retry"].update(patterns=[""]),
        lambda d: d["targets"][0]["retry"].update(unknown_field="boom"),
    ],
)
def test_plan_rejects_malformed_persisted_retry_data(tmp_path, mutate) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
retry = { attempts = 2, codes = ["rate_limit"] }

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    catalog = load_config(path)
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    data = execution_plan_data(plan)
    mutate(data)
    with pytest.raises(ValueError):
        parse_execution_plan(data)


