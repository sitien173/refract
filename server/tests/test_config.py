from __future__ import annotations

import json

import pytest

from openmcp.config import TargetConfig, load_config, load_project_config, load_task_guide, validate_target_args
from openmcp.planning import resolve_execution_plan
from openmcp.workflows import get_workflow
from tests.orchestration_helpers import config


def _explicit_config() -> str:
    return """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
capabilities = ["code", "review", "consult"]

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
"""


def test_task_guide_prefers_project_then_global(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "task_guide.json").write_text(json.dumps({"scope": "global"}), encoding="utf-8")
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    (root / ".openmcp" / "task_guide.json").write_text(json.dumps({"scope": "project"}), encoding="utf-8")
    assert load_task_guide(home, root) == {"scope": "project"}
    assert load_task_guide(home) == {"scope": "global"}


def test_default_builtins_resolve_capable_targets(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    for name in ("implement", "review", "consult"):
        assert resolve_execution_plan(get_workflow(name), catalog, "balanced").selection.targets == ("primary",)


def test_explicit_other_profile_mapping_loads(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config().replace('consult = "primary"', 'consult = "primary"\nother = "primary"'), encoding="utf-8")

    catalog = load_config(path)

    assert resolve_execution_plan(get_workflow("other"), catalog, "balanced").selection.targets == ("primary",)


def test_missing_config_file_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="Missing config file"):
        load_config(tmp_path / "config.toml")


@pytest.mark.parametrize(
    ("section", "config"),
    [
        ("targets", '[daemon]\ndefault_profile = "balanced"\n[profiles.balanced]\nimplement = "primary"\nreview = "primary"\nconsult = "primary"\n'),
        ("profiles", '[daemon]\ndefault_profile = "balanced"\n[[targets]]\nid = "primary"\nbackend = "codex"\n'),
    ],
)
def test_required_config_sections_must_be_present(tmp_path, section, config) -> None:
    path = tmp_path / "config.toml"
    path.write_text(config, encoding="utf-8")

    with pytest.raises(ValueError, match=section):
        load_config(path)


@pytest.mark.parametrize(
    ("section", "config"),
    [
        (
            "targets",
            '[daemon]\ndefault_profile = "balanced"\n[targets]\n[profiles.balanced]\nimplement = "primary"\nreview = "primary"\nconsult = "primary"\n',
        ),
        (
            "profiles",
            '[daemon]\ndefault_profile = "balanced"\n[[targets]]\nid = "primary"\nbackend = "codex"\n[profiles]\n',
        ),
    ],
)
def test_required_config_sections_must_not_be_empty(tmp_path, section, config) -> None:
    path = tmp_path / "config.toml"
    path.write_text(config, encoding="utf-8")

    with pytest.raises(ValueError, match=section):
        load_config(path)


@pytest.mark.parametrize(
    "daemon", ["[daemon]", '[daemon]\ndefault_profile = "missing"'],
)
def test_default_profile_must_be_explicit_and_known(tmp_path, daemon) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config().replace('[daemon]\ndefault_profile = "balanced"', daemon), encoding="utf-8")

    with pytest.raises(ValueError, match="default_profile"):
        load_config(path)


def test_removed_global_profile_aliases_are_rejected(tmp_path) -> None:
    legacy_profiles = "routing_" + "profiles"
    legacy_default = "default_" + "routing_" + "profile"
    path = tmp_path / "config.toml"
    path.write_text(
        f"[{legacy_profiles}.balanced]\n"
        f"{legacy_default} = \"balanced\"\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported"):
        load_config(path)


def test_removed_project_profile_aliases_are_rejected(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    legacy_profiles = "routing_" + "profiles"
    (root / ".openmcp" / "config.toml").write_text(
        f"[{legacy_profiles}.quality]\nimplement = \"primary\"\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported"):
        load_project_config(root, config(tmp_path / "home"))


def test_project_config_overlays_profiles(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    (root / ".openmcp" / "config.toml").write_text("""[project]
default_profile = "quality"
[profiles.quality]
implement = "primary"
review = "primary"
consult = "primary"
""", encoding="utf-8")
    catalog = config(tmp_path / "home")
    resolved = load_project_config(root, catalog)
    assert resolved.default_profile == "quality"
    assert resolve_execution_plan(get_workflow("implement"), resolved, "quality").selection.targets == ("primary",)


def _profile_chain_config(profiles: str) -> str:
    return f"""[daemon]
default_profile = "child"

[[targets]]
id = "primary"
backend = "codex"
capabilities = ["code", "review", "consult"]

{profiles}
"""


def _deep_profile_config(count: int, *, cycle: bool = False) -> str:
    declarations: list[str] = []
    indices = range(count - 1, -1, -1) if not cycle else range(count)
    for index in indices:
        declarations.append(f"[profiles.p{index}]")
        if cycle:
            declarations.append(
                f'extends = "p{0 if index == count - 1 else index + 1}"'
            )
        elif index:
            declarations.append(f'extends = "p{index - 1}"')
        else:
            declarations.append('consult = "primary"')
        declarations.append("")
    return _profile_chain_config("\n".join(declarations)).replace(
        'default_profile = "child"',
        f'default_profile = "p{count - 1 if not cycle else 0}"',
    )


def test_profiles_resolve_chains_without_declaration_order(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _profile_chain_config(
            """[profiles.child]
extends = "middle"
consult = "primary"

[profiles.middle]
extends = "base"
review = "primary"

[profiles.base]
implement = "primary"
"""
        ),
        encoding="utf-8",
    )

    catalog = load_config(path)

    assert set(catalog.profiles["child"]) == {"implement", "review", "consult"}
    assert catalog.profile_declarations["child"].extends == "middle"
    assert set(catalog.profile_declarations["child"].workflows) == {"consult"}


def test_deep_valid_profile_chain_does_not_use_recursion(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_deep_profile_config(1100), encoding="utf-8")

    catalog = load_config(path)

    assert set(catalog.profiles["p1099"]) == {"consult"}


def test_deep_profile_cycle_reports_ordered_closed_cycle(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_deep_profile_config(1100, cycle=True), encoding="utf-8")

    with pytest.raises(ValueError) as raised:
        load_config(path)

    message = str(raised.value)
    assert message.startswith("Profile inheritance cycle: p0 -> p1")
    assert message.endswith("p1099 -> p0")


def test_extends_only_profile_loads(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _profile_chain_config(
            """[profiles.base]
implement = "primary"

[profiles.child]
extends = "base"
"""
        ),
        encoding="utf-8",
    )

    catalog = load_config(path)

    assert catalog.profiles["child"] == catalog.profiles["base"]


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        ("extends = \"\"\nconsult = \"primary\"", "non-empty string"),
        ("extends = 1\nconsult = \"primary\"", "non-empty string"),
    ],
)
def test_extends_must_be_non_empty_string(tmp_path, profile, expected) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_profile_chain_config(f"[profiles.child]\n{profile}\n"), encoding="utf-8")

    with pytest.raises(ValueError, match=expected):
        load_config(path)


def test_empty_no_parent_profile_is_rejected(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_profile_chain_config("[profiles.child]\n"), encoding="utf-8")

    with pytest.raises(ValueError, match="declare extends or a workflow"):
        load_config(path)


def test_unknown_profile_parent_names_child_and_parent(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _profile_chain_config("[profiles.child]\nextends = \"missing\"\n"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="child.*missing"):
        load_config(path)


def test_unknown_profile_workflow_key_is_rejected(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _profile_chain_config(
            "[profiles.balanced]\nunknown = \"primary\"\n"
        ).replace('default_profile = "child"', 'default_profile = "balanced"'),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown workflow 'unknown'"):
        load_config(path)


def test_profile_inheritance_cycle_names_ordered_closed_cycle(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _profile_chain_config(
            """[profiles.a]
extends = "b"
consult = "primary"

[profiles.b]
extends = "c"

[profiles.c]
extends = "a"
"""
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="a -> b -> c -> a"):
        load_config(path)


def _layered_base_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        _profile_chain_config(
            """[profiles.base]
implement = "primary"
review = "primary"

[profiles.shadow]
consult = "primary"
"""
        ).replace('default_profile = "child"', 'default_profile = "base"'),
        encoding="utf-8",
    )
    return load_config(path)


def test_consult_only_profile_is_partial(tmp_path) -> None:
    catalog = _layered_base_config(tmp_path)

    assert set(catalog.profiles["shadow"]) == {"consult"}


def test_project_profile_replaces_same_name_base_profile(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    (root / ".openmcp" / "config.toml").write_text(
        """[profiles.shadow]
review = "primary"
""",
        encoding="utf-8",
    )
    base = _layered_base_config(tmp_path)

    resolved = load_project_config(root, base)

    assert set(resolved.profiles["shadow"]) == {"review"}
    assert set(base.profiles["shadow"]) == {"consult"}


def test_project_profile_extends_base_profile_across_layers(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    (root / ".openmcp" / "config.toml").write_text(
        """[profiles.child]
extends = "base"
consult = "primary"
""",
        encoding="utf-8",
    )
    base = _layered_base_config(tmp_path)

    resolved = load_project_config(root, base)

    assert set(resolved.profiles["child"]) == {"implement", "review", "consult"}


def test_project_self_extends_uses_shadowed_base_snapshot(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    (root / ".openmcp" / "config.toml").write_text(
        """[profiles.base]
extends = "base"
consult = "primary"
""",
        encoding="utf-8",
    )
    base = _layered_base_config(tmp_path)

    resolved = load_project_config(root, base)

    assert set(resolved.profiles["base"]) == {"implement", "review", "consult"}


def test_project_self_extends_without_base_parent_is_unknown(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    (root / ".openmcp" / "config.toml").write_text(
        """[profiles.missing]
extends = "missing"
consult = "primary"
""",
        encoding="utf-8",
    )
    base = _layered_base_config(tmp_path)

    with pytest.raises(ValueError, match="missing.*extends unknown parent 'missing'"):
        load_project_config(root, base)


def test_project_child_inherits_project_shadow_not_base_snapshot(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    (root / ".openmcp" / "config.toml").write_text(
        """[profiles.base]
consult = "primary"

[profiles.child]
extends = "base"
review = "primary"
""",
        encoding="utf-8",
    )
    base = _layered_base_config(tmp_path)

    resolved = load_project_config(root, base)

    assert set(resolved.profiles["child"]) == {"consult", "review"}


def test_child_workflow_override_replaces_selection_policy(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _profile_chain_config(
            """[profiles.base]
implement = { targets = ["primary"], max_attempts = 2, timeout_s = 10 }

[profiles.child]
extends = "base"
implement = { targets = ["primary"], max_attempts = 1, timeout_s = 3 }
"""
        ),
        encoding="utf-8",
    )

    catalog = load_config(path)

    assert catalog.profiles["child"]["implement"].max_attempts == 1
    assert catalog.profiles["child"]["implement"].timeout_s == 3


def test_global_self_extends_remains_a_cycle(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _profile_chain_config(
            """[profiles.self]
extends = "self"
consult = "primary"
"""
        ).replace('default_profile = "child"', 'default_profile = "self"'),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="self -> self"):
        load_config(path)


def test_project_cycles_remain_cycles_with_base_snapshots(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    (root / ".openmcp" / "config.toml").write_text(
        """[profiles.a]
extends = "b"

[profiles.b]
extends = "a"
""",
        encoding="utf-8",
    )
    base = _layered_base_config(tmp_path)

    with pytest.raises(ValueError, match="a -> b -> a"):
        load_project_config(root, base)


def test_project_load_does_not_mutate_base_declarations(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".openmcp").mkdir(parents=True)
    (root / ".openmcp" / "config.toml").write_text(
        """[profiles.child]
extends = "base"
""",
        encoding="utf-8",
    )
    base = _layered_base_config(tmp_path)
    base_profiles = {name: dict(mapping) for name, mapping in base.profiles.items()}
    base_declarations = dict(base.profile_declarations)

    load_project_config(root, base)

    assert base.profiles == base_profiles
    assert base.profile_declarations == base_declarations


@pytest.mark.parametrize("backend,args", [("agy", ("--",)), ("codex", ("--cd", "/other")), ("pi", ("--extension", "unsafe.ts"))])
def test_config_rejects_reserved_target_args(backend, args) -> None:
    with pytest.raises(ValueError):
        validate_target_args("unsafe", backend, args, isolated=backend == "pi")


def test_custom_target_defaults_support_all_semantic_workflows(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("""[[targets]]
id = "primary"
backend = "codex"
[daemon]
default_profile = "balanced"
[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
other = "primary"
""", encoding="utf-8")
    monkeypatch.setenv("OPENMCP_HOME", str(home))
    catalog = load_config(home / "config.toml")
    assert not hasattr(TargetConfig(id="primary", backend="codex"), "capabilities")
    assert all(resolve_execution_plan(get_workflow(name), catalog, "balanced").selection.targets == ("primary",) for name in ("implement", "review", "consult", "other"))


@pytest.mark.parametrize(
    ("setting", "value", "expected"),
    [
        ("isolated", '"false"', "true or false"),
        ("read_only", "1", "true or false"),
        ("max_concurrency", "0", "positive integer"),
        ("backend_profile", "false", "must be a string"),
    ],
)
def test_target_policy_types_are_strict(tmp_path, setting, value, expected) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _explicit_config().replace(
            'backend = "codex"',
            f'backend = "codex"\n{setting} = {value}',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=expected):
        load_config(path)


@pytest.mark.parametrize(
    ("setting", "value", "expected"),
    [
        ("port", "65536", "must not exceed"),
        ("max_jobs", '"4"', "positive integer"),
        ("history_turns", "false", "positive integer"),
    ],
)
def test_daemon_integer_types_are_strict(tmp_path, setting, value, expected) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _explicit_config().replace(
            'default_profile = "balanced"',
            f'default_profile = "balanced"\n{setting} = {value}',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=expected):
        load_config(path)
