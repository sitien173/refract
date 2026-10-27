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
    target = replace(catalog.targets[0], envs_vars=("shared",), envs={"LOCAL": "SYNTHETIC_TEMPLATE"})
    catalog = replace(catalog, targets=(target,))
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    data = execution_plan_data(plan)

    assert data["environment_targets"] == [target.id]
    assert "SYNTHETIC_TEMPLATE" not in str(data)
    restored = parse_execution_plan(data)
    assert restored.environment_targets == (target.id,)
    assert not restored.target(target.id).envs
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

[retryPolicies.transient]
retryAttempt = 2
errorCodes = ["rate_limit"]
errorPatterns = ["temporarily unavailable"]

[[targets]]
id = "primary"
backend = "codex"
retryPolicy = "transient"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    catalog = load_config(path)
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    assert "transient" in plan.retry_policies
    policy = plan.retry_policy("primary")
    assert policy.retry_attempt == 2
    assert policy.error_codes == ("rate_limit",)
    assert policy.error_patterns == ("temporarily unavailable",)

    # Round trip serialization
    data = execution_plan_data(plan)
    assert "retry_policies" in data
    assert data["retry_policies"]["transient"]["retry_attempt"] == 2
    restored = parse_execution_plan(data)
    assert restored == plan
    assert restored.retry_policy("primary") == policy

    # Catalog edits do not affect existing plan snapshot
    catalog.retry_policies.clear()
    assert plan.retry_policy("primary") == policy
    assert restored.retry_policy("primary") == policy


def test_legacy_plan_without_retry_policies_defaults_to_no_retry(tmp_path) -> None:
    from refract.config import RetryPolicy
    catalog = config(tmp_path / "home")
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    data = execution_plan_data(plan)
    data.pop("retry_policies", None)
    if "retry_policy" in data["targets"][0]:
        del data["targets"][0]["retry_policy"]

    restored = parse_execution_plan(data)
    assert restored.retry_policy("primary") == RetryPolicy(retry_attempt=0, error_codes=(), error_patterns=())


@pytest.mark.parametrize(
    ("mutate"),
    [
        lambda d: d.update(retry_policies="not a dict"),
        lambda d: d.update(retry_policies=None),
        lambda d: d.update(retry_policies={"transient": "not a dict"}),
        lambda d: d["retry_policies"]["transient"].update(retry_attempt=-1),
        lambda d: d["retry_policies"]["transient"].update(retry_attempt="2"),
        lambda d: d["retry_policies"]["transient"].update(retry_attempt=True),
        lambda d: d["retry_policies"]["transient"].update(retryAttempt=-1),
        lambda d: d["retry_policies"]["transient"].update(retryAttempt=99),
        lambda d: d["retry_policies"]["transient"].update(error_codes="not a list"),
        lambda d: d["retry_policies"]["transient"].update(error_codes=[123]),
        lambda d: d["retry_policies"]["transient"].update(error_codes=[""]),
        lambda d: d["retry_policies"]["transient"].update(errorCodes=["rate_limit"]),
        lambda d: d["retry_policies"]["transient"].update(error_patterns=[False]),
        lambda d: d["retry_policies"]["transient"].update(error_patterns=[""]),
        lambda d: d["retry_policies"]["transient"].update(errorPatterns=["pattern"]),
        lambda d: d["retry_policies"]["transient"].update(unknown_field="boom"),
        lambda d: d["targets"][0].update(retry_policy="dangling_policy"),
        lambda d: d["targets"][0].update(retry=2),
        lambda d: d["targets"][0].update(retryAttempt=2),
        lambda d: d["targets"][0].update(retryPolicy="transient"),
    ],
)
def test_plan_rejects_malformed_persisted_retry_data(tmp_path, mutate) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[retryPolicies.transient]
retryAttempt = 2
errorCodes = ["rate_limit"]

[[targets]]
id = "primary"
backend = "codex"
retryPolicy = "transient"

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


def test_execution_plan_retry_policies_is_immutable_and_isolated() -> None:
    from refract.config import RetryPolicy, TargetConfig, TargetSelection
    from refract.planning import ExecutionPlan

    target = TargetConfig(id="primary", backend="codex", retry_policy="transient")
    policy = RetryPolicy(2, ("rate_limit",), ())
    source = {"transient": policy}
    plan = ExecutionPlan(
        profile="balanced",
        workflow=get_workflow("implement"),
        selection=TargetSelection((target.id,)),
        targets=(target,),
        retry_policies=source,
    )
    with pytest.raises(TypeError):
        plan.retry_policies["transient"] = RetryPolicy(99)

    source["transient"] = RetryPolicy(99)
    assert plan.retry_policies["transient"].retry_attempt == 2
    assert plan.retry_policy("primary").retry_attempt == 2


def test_plan_rejects_explicit_null_retry_policies(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    data = execution_plan_data(resolve_execution_plan(get_workflow("implement"), catalog, "balanced"))
    data["retry_policies"] = None
    with pytest.raises(ValueError, match="mapping"):
        parse_execution_plan(data)


def test_plan_rejects_missing_retry_policies_when_target_references_policy(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[retryPolicies.transient]
retryAttempt = 2
errorCodes = ["rate_limit"]

[[targets]]
id = "primary"
backend = "codex"
retryPolicy = "transient"

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
    del data["retry_policies"]
    with pytest.raises(ValueError, match="unknown retry policy"):
        parse_execution_plan(data)


def test_retry_policy_accessor_rejects_dangling_reference() -> None:
    from refract.config import TargetConfig, TargetSelection
    from refract.planning import ExecutionPlan

    target = TargetConfig(id="primary", backend="codex", retry_policy="transient")
    plan = ExecutionPlan(
        profile="balanced",
        workflow=get_workflow("implement"),
        selection=TargetSelection((target.id,)),
        targets=(target,),
        retry_policies={},
    )
    with pytest.raises(ValueError, match="unknown retry policy"):
        plan.retry_policy("primary")


def test_resolve_execution_plan_rejects_dangling_reference() -> None:
    from pathlib import Path
    from refract.config import DaemonConfig, TargetConfig, TargetSelection
    from refract.planning import resolve_execution_plan

    target = TargetConfig(id="primary", backend="codex", retry_policy="missing_policy")
    cfg = DaemonConfig(
        home=Path("/tmp"),
        default_profile="balanced",
        targets=(target,),
        profiles={"balanced": {"implement": TargetSelection((target.id,))}},
        retry_policies={},
    )
    with pytest.raises(ValueError, match="unknown retry policy"):
        resolve_execution_plan("implement", cfg, "balanced")
