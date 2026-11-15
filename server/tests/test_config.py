from __future__ import annotations

import json

import pytest

from refract.config import (
    NotificationsConfig,
    ProfileDeclaration,
    RetryPolicy,
    TargetConfig,
    TargetSelection,
    load_config,
    load_project_config,
    load_guidance,
    validate_target_args,
)
from refract.config.load import ProfileResolutionError, _resolve_profile_maps
from refract.runner.planning import resolve_execution_plan
from refract.workflows import get_workflow
from tests.orchestration_helpers import Raised, config, outcome, plain


def _explicit_config() -> str:
    return """schema_version = 1

[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

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
    (root / ".refract").mkdir(parents=True)
    (root / ".refract" / "task_guide.json").write_text(json.dumps({"scope": "project"}), encoding="utf-8")
    assert load_guidance(home, root) == {"scope": "project"}
    assert load_guidance(home) == {"scope": "global"}


def test_default_builtins_resolve_capable_targets(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    for name in ("implement", "review", "consult"):
        assert resolve_execution_plan(get_workflow(name), catalog, "balanced").selection.targets == ("primary",)


def test_explicit_other_profile_mapping_loads(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config().replace('consult = "primary"', 'consult = "primary"\nother = "primary"'), encoding="utf-8")

    catalog = load_config(path)

    assert resolve_execution_plan(get_workflow("other"), catalog, "balanced").selection.targets == ("primary",)


def test_target_context_window_is_rejected(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config().replace('backend = "codex"', 'backend = "codex"\ncontext_window = 200000'), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported target settings"):
        load_config(path)


def test_missing_config_file_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="Missing config file"):
        load_config(tmp_path / "config.toml")


@pytest.mark.parametrize(
    ("section", "config"),
    [
        ("targets", 'schema_version = 1\n\n[daemon]\ndefault_profile = "balanced"\n[profiles.balanced]\nimplement = "primary"\nreview = "primary"\nconsult = "primary"\n'),
        ("profiles", 'schema_version = 1\n\n[daemon]\ndefault_profile = "balanced"\n[[targets]]\nid = "primary"\nbackend = "codex"\n'),
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
            'schema_version = 1\n\n[daemon]\ndefault_profile = "balanced"\n[targets]\n[profiles.balanced]\nimplement = "primary"\nreview = "primary"\nconsult = "primary"\n',
        ),
        (
            "profiles",
            'schema_version = 1\n\n[daemon]\ndefault_profile = "balanced"\n[[targets]]\nid = "primary"\nbackend = "codex"\n[profiles]\n',
        ),
    ],
)
def test_required_config_sections_must_not_be_empty(tmp_path, section, config) -> None:
    path = tmp_path / "config.toml"
    path.write_text(config, encoding="utf-8")

    with pytest.raises(ValueError, match=section):
        load_config(path)


@pytest.mark.parametrize(
    "daemon", ["[daemon]", 'schema_version = 1\n\n[daemon]\ndefault_profile = "missing"'],
)
def test_default_profile_must_be_explicit_and_known(tmp_path, daemon) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config().replace('schema_version = 1\n\n[daemon]\ndefault_profile = "balanced"', daemon), encoding="utf-8")

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
    (root / ".refract").mkdir(parents=True)
    legacy_profiles = "routing_" + "profiles"
    (root / ".refract" / "config.toml").write_text(
        f"[{legacy_profiles}.quality]\nimplement = \"primary\"\n",
        encoding="utf-8",
    )

    catalog = config(tmp_path / "home")
    with pytest.raises(ValueError, match="Unsupported"):
        load_project_config(root, catalog)


def test_project_config_overlays_profiles(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".refract").mkdir(parents=True)
    (root / ".refract" / "config.toml").write_text("""[profiles.quality]
implement = "primary"
review = "primary"
consult = "primary"
""", encoding="utf-8")
    catalog = config(tmp_path / "home")
    resolved = load_project_config(root, catalog)
    assert resolve_execution_plan(get_workflow("implement"), resolved, "quality").selection.targets == ("primary",)


def _profile_chain_config(profiles: str) -> str:
    return f"""schema_version = 1

[daemon]
default_profile = "child"

[[targets]]
id = "primary"
backend = "codex"

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
    assert message == "Profile inheritance cycle"


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

    with pytest.raises(ValueError, match="Profile extends unknown parent"):
        load_config(path)


def test_unknown_profile_workflow_key_is_rejected(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _profile_chain_config(
            "[profiles.balanced]\nunknown = \"primary\"\n"
        ).replace('default_profile = "child"', 'default_profile = "balanced"'),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown workflow$"):
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

    with pytest.raises(ValueError, match="Profile inheritance cycle"):
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
    (root / ".refract").mkdir(parents=True)
    (root / ".refract" / "config.toml").write_text(
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
    (root / ".refract").mkdir(parents=True)
    (root / ".refract" / "config.toml").write_text(
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
    (root / ".refract").mkdir(parents=True)
    (root / ".refract" / "config.toml").write_text(
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
    (root / ".refract").mkdir(parents=True)
    (root / ".refract" / "config.toml").write_text(
        """[profiles.missing]
extends = "missing"
consult = "primary"
""",
        encoding="utf-8",
    )
    base = _layered_base_config(tmp_path)

    with pytest.raises(ValueError, match="Profile extends unknown parent"):
        load_project_config(root, base)


def test_project_child_inherits_project_shadow_not_base_snapshot(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".refract").mkdir(parents=True)
    (root / ".refract" / "config.toml").write_text(
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
implement = { targets = ["primary"], timeout_s = 10 }

[profiles.child]
extends = "base"
implement = { targets = ["primary"], timeout_s = 3 }
"""
        ),
        encoding="utf-8",
    )

    catalog = load_config(path)

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

    with pytest.raises(ValueError, match="Profile inheritance cycle"):
        load_config(path)


def test_project_cycles_remain_cycles_with_base_snapshots(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".refract").mkdir(parents=True)
    (root / ".refract" / "config.toml").write_text(
        """[profiles.a]
extends = "b"

[profiles.b]
extends = "a"
""",
        encoding="utf-8",
    )
    base = _layered_base_config(tmp_path)

    with pytest.raises(ValueError, match="Profile inheritance cycle"):
        load_project_config(root, base)


def test_project_load_does_not_mutate_base_declarations(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".refract").mkdir(parents=True)
    (root / ".refract" / "config.toml").write_text(
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


@pytest.mark.parametrize("backend,args", [("agy", ("--",)), ("codex", ("--cd", "/other")), ("pi", ("--",)), ("claude", ("--",))])
def test_config_rejects_reserved_target_args(backend, args) -> None:
    with pytest.raises(ValueError):
        validate_target_args("unsafe", backend, args)


def test_claude_target_loads_without_error(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config().replace('backend = "codex"', 'backend = "claude"'), encoding="utf-8")

    catalog = load_config(path)

    assert catalog.targets[0].backend == "claude"


def test_custom_target_defaults_support_all_semantic_workflows(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "config.toml").write_text("""schema_version = 1
[[targets]]
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
    monkeypatch.setenv("REFRACT_HOME", str(home))
    catalog = load_config(home / "config.toml")
    assert not hasattr(TargetConfig(id="primary", backend="codex"), "capabilities")
    assert all(resolve_execution_plan(get_workflow(name), catalog, "balanced").selection.targets == ("primary",) for name in ("implement", "review", "consult", "other"))


@pytest.mark.parametrize(
    ("setting", "value", "expected"),
    [
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


@pytest.mark.parametrize("setting", ["history_turns", "history_bytes"])
def test_removed_history_settings_fail_load(tmp_path, setting) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _explicit_config().replace(
            'default_profile = "balanced"',
            f'default_profile = "balanced"\n{setting} = 8',
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsupported daemon settings"):
        load_config(path)


def test_max_project_readers_is_unsupported_daemon_setting(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _explicit_config().replace(
            'default_profile = "balanced"',
            'default_profile = "balanced"\nmax_project_readers = 2',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unsupported daemon settings"):
        load_config(path)


def test_breaker_config_defaults(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config().replace('implement = "primary"', 'implement = { targets = ["primary"] }'), encoding="utf-8")
    catalog = load_config(path)
    assert catalog.breaker_failure_threshold == 3
    assert catalog.breaker_base_cooldown_s == 60
    assert catalog.breaker_max_cooldown_s == 900
    assert catalog.profiles["balanced"]["implement"].targets == ("primary",)


def test_breaker_max_cooldown_must_not_be_below_base(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config().replace('default_profile = "balanced"', 'default_profile = "balanced"\nbreaker_base_cooldown_s = 80\nbreaker_max_cooldown_s = 60'), encoding="utf-8")
    with pytest.raises(ValueError, match=r"breaker_max_cooldown_s must be >= breaker_base_cooldown_s"):
        load_config(path)


def test_notifications_config_defaults_disabled_when_absent(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config(), encoding="utf-8")

    catalog = load_config(path)

    assert catalog.notifications.enabled is False


def test_notifications_config_defaults_disabled_when_empty_table(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config() + "\n[notifications]\n", encoding="utf-8")

    catalog = load_config(path)

    assert catalog.notifications.enabled is False


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        ("enabled = true", True),
        ("enabled = false", False),
    ],
)
def test_notifications_config_parses_boolean_flag(tmp_path, setting, expected) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config() + f"\n[notifications]\n{setting}\n", encoding="utf-8")

    catalog = load_config(path)

    assert catalog.notifications.enabled is expected


@pytest.mark.parametrize(
    "content",
    [
        "[notifications]\nextra = 1\n",
        '[notifications]\nenabled = "yes"\n',
        "[notifications]\nenabled = 1\n",
        "notifications = 1\n",
    ],
)
def test_notifications_config_strict_validation(tmp_path, content) -> None:
    path = tmp_path / "config.toml"
    path.write_text(f"{content}\n{_explicit_config()}", encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(path)


def test_project_config_rejects_notifications(tmp_path) -> None:
    root = tmp_path / "project"
    (root / ".refract").mkdir(parents=True)
    (root / ".refract" / "config.toml").write_text(
        "[notifications]\nenabled = true\n",
        encoding="utf-8",
    )

    catalog = config(tmp_path / "home")
    with pytest.raises(ValueError, match="Unsupported project config sections"):
        load_project_config(root, catalog)


def test_notifications_config_dataclass_defaults_and_immutability() -> None:
    notif_config = NotificationsConfig()
    assert notif_config.enabled is False
    with pytest.raises(AttributeError):
        notif_config.enabled = True  # type: ignore[misc]


def test_ask_timeout_s_default_and_custom(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_explicit_config(), encoding="utf-8")
    cfg = load_config(path)
    assert cfg.ask_timeout_s == 300

    path.write_text(
        _explicit_config().replace(
            'default_profile = "balanced"',
            'default_profile = "balanced"\nask_timeout_s = 60',
        ),
        encoding="utf-8",
    )
    cfg2 = load_config(path)
    assert cfg2.ask_timeout_s == 60


@pytest.mark.parametrize(
    "invalid_val",
    ["false", "true", '"60"', "0", "-5", "3.14"],
)
def test_ask_timeout_s_invalid_values_rejected(tmp_path, invalid_val) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _explicit_config().replace(
            'default_profile = "balanced"',
            f'default_profile = "balanced"\nask_timeout_s = {invalid_val}',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="positive integer"):
        load_config(path)


def test_project_overlay_retains_global_retry_and_rejects_project_retry(tmp_path) -> None:
    global_path = tmp_path / "global_config.toml"
    global_path.write_text(
        _explicit_config().replace(
            'backend = "codex"',
            'backend = "codex"\nretry = { attempts = 2, codes = ["service_error"] }',
        ),
        encoding="utf-8",
    )
    base = load_config(global_path)
    assert base.targets[0].retry == RetryPolicy(2, ("service_error",), ())

    project_root = tmp_path / "project"
    (project_root / ".refract").mkdir(parents=True)
    project_config = project_root / ".refract" / "config.toml"
    project_config.write_text('[[targets]]\nid = "primary"\nenv = { A = "1" }\n', encoding="utf-8")
    overlaid = load_project_config(project_root, base)
    assert overlaid.targets[0].retry == base.targets[0].retry

    project_config.write_text('[[targets]]\nid = "primary"\nretry = { attempts = 5 }\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported project target settings"):
        load_project_config(project_root, base)
    project_config.write_text("[retry]\nattempts = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported project config sections"):
        load_project_config(project_root, base)


def test_target_rejects_retry_policy_alias(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _explicit_config().replace('backend = "codex"', 'backend = "codex"\nretry_policy = "transient"'),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Unsupported target settings"):
        load_config(path)


def test_environment_declarations_preserve_source_revision_metadata(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _explicit_config().replace('backend = "codex"', 'backend = "codex"\nenv = { LOCAL = "loc" }'),
        encoding="utf-8",
    )
    catalog = load_config(path)
    assert catalog.config_revision != ""
    assert catalog.revision == catalog.config_revision
    assert catalog.targets[0].env == {"LOCAL": "loc"}


def test_removed_tracing_config_section_fails_as_unsupported_section(tmp_path) -> None:
    path = tmp_path / "config.toml"
    removed_section = "[lang" "fuse]\nenabled = true\n"
    path.write_text(_explicit_config() + "\n" + removed_section, encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported config sections"):
        load_config(path)


# Characterization of private config helpers. Expected values were recorded from
# the implementation before the complexity refactor; every case pins the result
# or the exact error text, and the "*_before_*" cases pin which error wins.

def _sel(targets: tuple[str, ...], timeout_s: int = 0) -> TargetSelection:
    return TargetSelection(targets, timeout_s)


def _decl(extends: str | None = None, **workflows: str) -> ProfileDeclaration:
    return ProfileDeclaration(extends, {k: _sel((v,)) for k, v in workflows.items()})


def _selection_config(workflow_value: str, profiles_extra: str = "") -> str:
    return (
        "schema_version = 1\n\n"
        '[daemon]\ndefault_profile = "p"\n\n'
        '[[targets]]\nid = "a"\nbackend = "codex"\n\n'
        '[[targets]]\nid = "b"\nbackend = "pi"\n\n'
        f"[profiles.p]\n{workflow_value}\n{profiles_extra}"
    )


def _load_text(tmp_path, text: str):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return load_config(path)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('implement = "a"', _sel(("a",))),
        ('implement = " a "', _sel(("a",))),
        ('implement = ["a", "b"]', _sel(("a", "b"))),
        ('implement = { targets = "a" }', _sel(("a",))),
        ('implement = { targets = ["b"], timeout_s = 30 }', _sel(("b",), 30)),
    ],
)
def test_profile_selection_shapes_load(tmp_path, value, expected) -> None:
    assert _load_text(tmp_path, _selection_config(value)).profiles["p"]["implement"] == expected


@pytest.mark.parametrize(
    ("value", "code", "loc"),
    [
        ('implement = "zzz"', "unknown_target", ("profiles", "p", "implement", "targets", 0)),
        ('implement = ["a", "a"]', "duplicate_selection_target", ("profiles", "p", "implement", "targets", 1)),
        ('implement = ""', "unknown_target", ("profiles", "p", "implement", "targets", 0)),
        ("implement = []", "too_short", ("profiles", "p", "implement", "targets")),
        ("implement = { targets = [1] }", "string_type", ("profiles", "p", "implement", "targets", 0)),
        ('implement = { targets = ["a"], timeout_s = -1 }', "greater_than_equal", ("profiles", "p", "implement", "timeout_s")),
        ('implement = { targets = ["a"], extra = 1 }', "extra_forbidden", ("profiles", "p", "implement", "extra")),
        ("implement = 5", "model_type", ("profiles", "p", "implement")),
        ('implement = "a"\nbogus = "a"', "extra_forbidden", ("profiles", "p", "bogus")),
    ],
)
def test_profile_selection_errors_carry_code_and_loc(tmp_path, value, code, loc) -> None:
    with pytest.raises(ValueError) as caught:
        _load_text(tmp_path, _selection_config(value))
    assert [(issue.code, issue.loc) for issue in caught.value.issues] == [(code, loc)]


@pytest.mark.parametrize(
    ("body", "code", "loc"),
    [
        ("", "empty_profile", ("profiles", "q")),
        ('extends = ""', "empty_string", ("profiles", "q", "extends")),
        ("extends = 3", "string_type", ("profiles", "q", "extends")),
        ('extends = "missing"', "unknown_parent", ("profiles", "q", "extends")),
    ],
)
def test_profile_declaration_errors_carry_code_and_loc(tmp_path, body, code, loc) -> None:
    with pytest.raises(ValueError) as caught:
        _load_text(tmp_path, _selection_config('implement = "a"', f"\n[profiles.q]\n{body}\n"))
    assert [(issue.code, issue.loc) for issue in caught.value.issues] == [(code, loc)]


@pytest.mark.parametrize(
    ("env", "code"),
    [
        ('{ "" = "1" }', "env_key_empty"),
        ('{ "A=B" = "1" }', "env_key_equals"),
        ('{ "A\\u0000" = "1" }', "env_key_nul"),
        ('{ REFRACT_ASK_X = "1" }', "env_key_reserved"),
        ('{ A = "x\\u0000" }', "env_value_nul"),
        ('{ A = "${HOME}" }', "env_value_interpolation"),
        ("{ A = 1 }", "string_type"),
        ("{ A = true }", "string_type"),
    ],
)
def test_target_env_errors_carry_code(tmp_path, env, code) -> None:
    text = _selection_config('implement = "a"').replace(
        'id = "a"\nbackend = "codex"\n', f'id = "a"\nbackend = "codex"\nenv = {env}\n'
    )
    with pytest.raises(ValueError) as caught:
        _load_text(tmp_path, text)
    assert [issue.code for issue in caught.value.issues] == [code]
    assert all(issue.loc[:3] == ("targets", 0, "env") for issue in caught.value.issues)


def test_every_load_error_maps_to_config_invalid_payload(tmp_path) -> None:
    with pytest.raises(ValueError) as caught:
        _load_text(tmp_path, _selection_config('implement = "zzz"'))
    payload = caught.value.payload()
    assert payload["code"] == "config_invalid"
    assert all(set(entry) == {"code", "loc", "msg", "hint"} for entry in payload["errors"])
    assert [(entry["code"], entry["loc"]) for entry in payload["errors"]] == [
        ("unknown_target", ["profiles", "p", "implement", "targets", 0])
    ]


_RESOLVE_PROFILE_MAP_CASES = {
    "chain": (
        (
            {
                "a": ProfileDeclaration(
                    extends=None, workflows={"implement": TargetSelection(targets=("t1",), timeout_s=0)}
                ),
                "b": ProfileDeclaration(
                    extends="a", workflows={"review": TargetSelection(targets=("t2",), timeout_s=0)}
                ),
                "c": ProfileDeclaration(
                    extends="b", workflows={"consult": TargetSelection(targets=("t3",), timeout_s=0)}
                ),
            },
            None,
        ),
        {
            "a": {"implement": _sel(("t1",))},
            "b": {"implement": _sel(("t1",)), "review": _sel(("t2",))},
            "c": {"implement": _sel(("t1",)), "review": _sel(("t2",)), "consult": _sel(("t3",))},
        },
    ),
    "chain_child_first": (
        (
            {
                "c": ProfileDeclaration(
                    extends="b", workflows={"consult": TargetSelection(targets=("t3",), timeout_s=0)}
                ),
                "b": ProfileDeclaration(
                    extends="a", workflows={"review": TargetSelection(targets=("t2",), timeout_s=0)}
                ),
                "a": ProfileDeclaration(
                    extends=None, workflows={"implement": TargetSelection(targets=("t1",), timeout_s=0)}
                ),
            },
            None,
        ),
        {
            "a": {"implement": _sel(("t1",))},
            "b": {"implement": _sel(("t1",)), "review": _sel(("t2",))},
            "c": {"implement": _sel(("t1",)), "review": _sel(("t2",)), "consult": _sel(("t3",))},
        },
    ),
    "no_extends": (
        (
            {
                "a": ProfileDeclaration(
                    extends=None, workflows={"implement": TargetSelection(targets=("t1",), timeout_s=0)}
                )
            },
            None,
        ),
        {"a": {"implement": _sel(("t1",))}},
    ),
    "override": (
        (
            {
                "a": ProfileDeclaration(
                    extends=None,
                    workflows={
                        "implement": TargetSelection(targets=("t1",), timeout_s=0),
                        "review": TargetSelection(targets=("t1",), timeout_s=0),
                    },
                ),
                "b": ProfileDeclaration(
                    extends="a", workflows={"implement": TargetSelection(targets=("t2",), timeout_s=0)}
                ),
            },
            None,
        ),
        {
            "a": {"implement": _sel(("t1",)), "review": _sel(("t1",))},
            "b": {"implement": _sel(("t2",)), "review": _sel(("t1",))},
        },
    ),
    "shared_parent": (
        (
            {
                "a": ProfileDeclaration(
                    extends=None, workflows={"implement": TargetSelection(targets=("t1",), timeout_s=0)}
                ),
                "b": ProfileDeclaration(
                    extends="a", workflows={"review": TargetSelection(targets=("t2",), timeout_s=0)}
                ),
                "c": ProfileDeclaration(
                    extends="a", workflows={"review": TargetSelection(targets=("t3",), timeout_s=0)}
                ),
            },
            None,
        ),
        {
            "a": {"implement": _sel(("t1",))},
            "b": {"implement": _sel(("t1",)), "review": _sel(("t2",))},
            "c": {"implement": _sel(("t1",)), "review": _sel(("t3",))},
        },
    ),
    "self_extends_no_snapshots": (
        (
            {
                "a": ProfileDeclaration(
                    extends="a", workflows={"implement": TargetSelection(targets=("t1",), timeout_s=0)}
                )
            },
            None,
        ),
        Raised(ValueError, "Profile inheritance cycle: a -> a"),
    ),
    "self_extends_snapshot": (
        (
            {
                "a": ProfileDeclaration(
                    extends="a", workflows={"review": TargetSelection(targets=("t2",), timeout_s=0)}
                )
            },
            {"a": {"implement": TargetSelection(targets=("t1",), timeout_s=0)}},
        ),
        {"a": {"implement": _sel(("t1",)), "review": _sel(("t2",))}},
    ),
    "self_extends_snapshot_missing": (
        (
            {
                "a": ProfileDeclaration(
                    extends="a", workflows={"review": TargetSelection(targets=("t2",), timeout_s=0)}
                )
            },
            {"b": {}},
        ),
        Raised(ValueError, "Profile 'a' extends unknown parent 'a'"),
    ),
    "self_extends_empty_snapshots": (
        (
            {
                "a": ProfileDeclaration(
                    extends="a", workflows={"review": TargetSelection(targets=("t2",), timeout_s=0)}
                )
            },
            {},
        ),
        Raised(ValueError, "Profile 'a' extends unknown parent 'a'"),
    ),
    "parent_in_snapshots": (
        (
            {
                "a": ProfileDeclaration(
                    extends="base", workflows={"review": TargetSelection(targets=("t2",), timeout_s=0)}
                )
            },
            {"base": {"implement": TargetSelection(targets=("t1",), timeout_s=0)}},
        ),
        {"a": {"implement": _sel(("t1",)), "review": _sel(("t2",))}},
    ),
    "parent_unknown_no_snapshots": (
        (
            {
                "a": ProfileDeclaration(
                    extends="nope", workflows={"review": TargetSelection(targets=("t2",), timeout_s=0)}
                )
            },
            None,
        ),
        Raised(ValueError, "Profile 'a' extends unknown parent 'nope'"),
    ),
    "parent_unknown_with_snapshots": (
        (
            {
                "a": ProfileDeclaration(
                    extends="nope", workflows={"review": TargetSelection(targets=("t2",), timeout_s=0)}
                )
            },
            {"base": {}},
        ),
        Raised(ValueError, "Profile 'a' extends unknown parent 'nope'"),
    ),
    "parent_in_declarations_and_snapshots": (
        (
            {
                "a": ProfileDeclaration(
                    extends=None, workflows={"implement": TargetSelection(targets=("t1",), timeout_s=0)}
                ),
                "b": ProfileDeclaration(extends="a", workflows={}),
            },
            {"a": {"implement": TargetSelection(targets=("old",), timeout_s=0)}},
        ),
        {"a": {"implement": _sel(("t1",))}, "b": {"implement": _sel(("t1",))}},
    ),
    "two_cycle": (
        (
            {
                "a": ProfileDeclaration(extends="b", workflows={}),
                "b": ProfileDeclaration(extends="a", workflows={}),
            },
            None,
        ),
        Raised(ValueError, "Profile inheritance cycle: a -> b -> a"),
    ),
    "three_cycle": (
        (
            {
                "a": ProfileDeclaration(extends="b", workflows={}),
                "b": ProfileDeclaration(extends="c", workflows={}),
                "c": ProfileDeclaration(extends="a", workflows={}),
            },
            None,
        ),
        Raised(ValueError, "Profile inheritance cycle: a -> b -> c -> a"),
    ),
    "tail_into_cycle": (
        (
            {
                "x": ProfileDeclaration(extends="a", workflows={}),
                "a": ProfileDeclaration(extends="b", workflows={}),
                "b": ProfileDeclaration(extends="a", workflows={}),
            },
            None,
        ),
        Raised(ValueError, "Profile inheritance cycle: a -> b -> a"),
    ),
    "chain_ends_unknown": (
        (
            {
                "a": ProfileDeclaration(extends="b", workflows={}),
                "b": ProfileDeclaration(extends="nope", workflows={}),
            },
            None,
        ),
        Raised(ValueError, "Profile 'b' extends unknown parent 'nope'"),
    ),
    "chain_ends_in_snapshot": (
        (
            {
                "a": ProfileDeclaration(extends="b", workflows={}),
                "b": ProfileDeclaration(extends="snap", workflows={}),
            },
            {"snap": {"review": TargetSelection(targets=("t9",), timeout_s=0)}},
        ),
        {"b": {"review": _sel(("t9",))}, "a": {"review": _sel(("t9",))}},
    ),
    "empty": (({}, None), {}),
    "memo_after_error_order": (
        (
            {
                "a": ProfileDeclaration(
                    extends=None, workflows={"implement": TargetSelection(targets=("t1",), timeout_s=0)}
                ),
                "b": ProfileDeclaration(extends="nope", workflows={}),
                "c": ProfileDeclaration(extends="a", workflows={}),
            },
            None,
        ),
        Raised(ValueError, "Profile 'b' extends unknown parent 'nope'"),
    ),
    "snapshot_not_mutated_value": (
        (
            {
                "a": ProfileDeclaration(
                    extends="snap", workflows={"implement": TargetSelection(targets=("t2",), timeout_s=0)}
                )
            },
            {
                "snap": {
                    "implement": TargetSelection(targets=("t1",), timeout_s=0),
                    "review": TargetSelection(targets=("t1",), timeout_s=0),
                }
            },
        ),
        {"a": {"implement": _sel(("t2",)), "review": _sel(("t1",))}},
    ),
}


@pytest.mark.parametrize("case", list(_RESOLVE_PROFILE_MAP_CASES))
def test_resolve_profile_maps_characterization(case) -> None:
    (declarations, snapshots), expected = _RESOLVE_PROFILE_MAP_CASES[case]
    def call():
        try:
            return _resolve_profile_maps(declarations, snapshots=snapshots)
        except ProfileResolutionError as exc:
            raise ValueError(str(exc)) from exc

    assert outcome(call) == plain(expected)


def test_retry_code_literal_matches_library_codes() -> None:
    from typing import get_args

    from coding_agent_cli import ErrorCode
    from refract.config.models import RetryCode

    # Codes that never reach a retryable failure: limits and parser errors are target fatal, the rest are warnings.
    excluded = {
        "cancelled", "idle_timeout", "max_turns", "budget", "parser_error",
        "no_session_id", "line_too_long", "cleanup_incomplete",
    }
    assert set(ErrorCode) - excluded == set(get_args(RetryCode))


@pytest.mark.parametrize(
    ("backend", "arg"),
    [
        ("agy", '"--"'),
        ("codex", '"--"'),
        ("pi", '"a\\u0000b"'),
        ("codex", '"--cd", "x"'),
        ("codex", '"--cd=x"'),
        ("codex", '"-C", "x"'),
        ("codex", '"-Cx"'),
    ],
)
def test_load_config_rejects_unsafe_target_args(tmp_path, backend, arg) -> None:
    text = _selection_config("implement = \"a\"").replace(
        'id = "a"\nbackend = "codex"', f'id = "a"\nbackend = "{backend}"\nargs = [{arg}]'
    )
    with pytest.raises(ValueError) as caught:
        _load_text(tmp_path, text)
    assert [issue.loc for issue in caught.value.issues] == [("targets", 0, "args")]
    assert caught.value.payload()["code"] == "config_invalid"


def test_load_config_accepts_permitted_non_codex_args(tmp_path) -> None:
    text = _selection_config('implement = "a"').replace(
        'id = "a"\nbackend = "codex"', 'id = "a"\nbackend = "pi"\nargs = ["--cd", "x", "-C"]'
    )
    assert _load_text(tmp_path, text).targets[0].args == ("--cd", "x", "-C")


@pytest.mark.parametrize("timeout", ["true", "1.5", '"5"'])
def test_load_config_rejects_non_integer_workflow_timeouts(tmp_path, timeout) -> None:
    text = _selection_config(f'implement = {{ targets = ["a"], timeout_s = {timeout} }}')
    with pytest.raises(ValueError) as caught:
        _load_text(tmp_path, text)
    assert [issue.loc for issue in caught.value.issues] == [("profiles", "p", "implement", "timeout_s")]


def test_load_config_rejects_empty_target_list_in_table_form(tmp_path) -> None:
    with pytest.raises(ValueError) as caught:
        _load_text(tmp_path, _selection_config("implement = { targets = [] }"))
    assert [(i.code, i.loc) for i in caught.value.issues] == [
        ("too_short", ("profiles", "p", "implement", "targets"))
    ]
