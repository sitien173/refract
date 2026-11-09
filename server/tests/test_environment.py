from __future__ import annotations

from pathlib import Path

import pytest

from refract.config import (
    DaemonConfig,
    TargetConfig,
    load_config,
)

_PROFILES = """
[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
"""


def _base_config_toml() -> str:
    return """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
""" + _PROFILES


def _target_toml(env_line: str) -> str:
    return f"""[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
{env_line}
""" + _PROFILES


def _overlay(tmp_path: Path, global_text: str, project_text: str):
    from refract.config import load_project_config

    global_path = tmp_path / "config.toml"
    global_path.write_text(global_text, encoding="utf-8")
    base = load_config(global_path)
    project_root = tmp_path / "project"
    (project_root / ".refract").mkdir(parents=True)
    (project_root / ".refract" / "config.toml").write_text(project_text, encoding="utf-8")
    return base, (lambda: load_project_config(project_root, base))


def test_existing_config_loads_with_empty_environment_defaults(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_base_config_toml(), encoding="utf-8")

    catalog = load_config(path)

    assert catalog.targets[0].env == {}


@pytest.mark.parametrize(
    "env_line",
    [
        "env = { NUM = 123 }",
        "env = { BOOL = false }",
        'env = { ARRAY = ["a", "b"] }',
    ],
)
def test_environment_values_must_be_strings(tmp_path, env_line) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_target_toml(env_line), encoding="utf-8")
    with pytest.raises(ValueError, match="Environment values must be strings"):
        load_config(path)


@pytest.mark.parametrize(
    "key_repr",
    ['""', '"FOO=BAR"', '"FOO\\u0000BAR"'],
)
def test_environment_keys_cannot_be_empty_or_contain_equal_or_nul(tmp_path, key_repr) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_target_toml(f'env = {{ {key_repr} = "val" }}'), encoding="utf-8")
    with pytest.raises(ValueError, match="Environment key"):
        load_config(path)


def test_environment_keys_cannot_use_protected_ask_prefix(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_target_toml('env = { REFRACT_ASK_TOKEN = "stolen" }'), encoding="utf-8")
    with pytest.raises(ValueError, match="protected prefix"):
        load_config(path)


def test_environment_values_cannot_contain_nul(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_target_toml('env = { KEY = "val\\u0000with_nul" }'), encoding="utf-8")
    with pytest.raises(ValueError, match="NUL"):
        load_config(path)


def test_target_env_must_be_toml_table(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_target_toml('env = ["not", "a", "table"]'), encoding="utf-8")
    with pytest.raises(ValueError, match="env must be a TOML table"):
        load_config(path)


def test_env_values_are_literal_and_reject_references(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_target_toml('env = { HOME_COPY = "${HOME}" }'), encoding="utf-8")
    with pytest.raises(ValueError, match="has been removed"):
        load_config(path)
    path.write_text(_target_toml('env = { PRICE = "$5 and $$ stay" }'), encoding="utf-8")
    assert load_config(path).targets[0].env == {"PRICE": "$5 and $$ stay"}


def test_raw_declarations_kept_out_of_dataclass_reprs(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        _target_toml('env = { TARGET_SECRET = "super-secret-target-marker-67890" }'),
        encoding="utf-8",
    )
    catalog = load_config(path)
    target = catalog.targets[0]
    assert "super-secret-target-marker-67890" not in repr(catalog)
    assert "super-secret-target-marker-67890" not in repr(target)
    assert "TARGET_SECRET" not in repr(catalog)
    assert "TARGET_SECRET" not in repr(target)


def test_no_shared_mutable_defaults() -> None:
    t1 = TargetConfig(id="t1", backend="codex")
    t2 = TargetConfig(id="t2", backend="codex")
    assert t1.env is not t2.env
    t1.env["MUTATED"] = "leak"
    assert "MUTATED" not in t2.env


def test_project_target_overlay_precedence_and_replacement(tmp_path) -> None:
    base, load = _overlay(
        tmp_path,
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
args = ["--default-arg"]
env = { KEY_1 = "g1", KEY_2 = "g2" }
""" + _PROFILES,
        """[[targets]]
id = "primary"
env = { KEY_2 = "p2", KEY_3 = "p3" }
""",
    )
    target = load().targets[0]
    assert target.env == {"KEY_1": "g1", "KEY_2": "p2", "KEY_3": "p3"}
    # Unrelated target policy preserved
    assert target.backend == "codex"
    assert target.args == ("--default-arg",)
    # Base target unchanged
    assert base.targets[0].env == {"KEY_1": "g1", "KEY_2": "g2"}


def test_project_target_empty_local_env_does_not_delete_inherited(tmp_path) -> None:
    _base, load = _overlay(
        tmp_path,
        _target_toml('env = { KEEP_ME = "val" }'),
        """[[targets]]
id = "primary"
env = {}
""",
    )
    assert load().targets[0].env == {"KEEP_ME": "val"}


def test_project_target_rejects_unknown_target_id(tmp_path) -> None:
    _base, load = _overlay(
        tmp_path,
        _base_config_toml(),
        """[[targets]]
id = "nonexistent_target"
env = { KEY = "val" }
""",
    )
    with pytest.raises(ValueError, match="Project config cannot add targets"):
        load()


def test_project_target_rejects_duplicate_target_overrides(tmp_path) -> None:
    _base, load = _overlay(
        tmp_path,
        _base_config_toml(),
        """[[targets]]
id = "primary"
env = { A = "1" }

[[targets]]
id = "primary"
env = { B = "2" }
""",
    )
    with pytest.raises(ValueError, match="Duplicate project target override"):
        load()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("backend", '"pi"'),
        ("model", '"gpt-4"'),
        ("args", '["--some-arg"]'),
        ("isolated", "true"),
        ("read_only", "true"),
        ("max_concurrency", "5"),
        ("retry", "{ attempts = 2 }"),
    ],
)
def test_project_target_rejects_non_environment_fields(tmp_path, field, value) -> None:
    _base, load = _overlay(
        tmp_path,
        _base_config_toml(),
        f"""[[targets]]
id = "primary"
{field} = {value}
""",
    )
    with pytest.raises(ValueError, match="Unsupported project target settings"):
        load()


def test_independent_project_catalogs_and_global_isolation(tmp_path) -> None:
    from refract.config import load_project_config

    global_path = tmp_path / "config.toml"
    global_path.write_text(_target_toml('env = { LOC = "global_loc" }'), encoding="utf-8")
    base = load_config(global_path)
    roots = {}
    for name in ("proj1", "proj2"):
        root = tmp_path / name
        (root / ".refract").mkdir(parents=True)
        (root / ".refract" / "config.toml").write_text(
            f'[[targets]]\nid = "primary"\nenv = {{ LOC = "{name}_loc" }}\n', encoding="utf-8"
        )
        roots[name] = root

    p1 = load_project_config(roots["proj1"], base)
    p2 = load_project_config(roots["proj2"], base)

    assert base.targets[0].env["LOC"] == "global_loc"
    assert p1.targets[0].env["LOC"] == "proj1_loc"
    assert p2.targets[0].env["LOC"] == "proj2_loc"


def test_resolve_target_environment_returns_only_configured_literals() -> None:
    from refract.config import resolve_target_environment

    target = TargetConfig(
        id="target1",
        backend="codex",
        env={"COMMON": "from_target", "LOCAL": "local_val"},
    )
    catalog = DaemonConfig(home=Path("/tmp"), targets=(target,))
    resolved = resolve_target_environment(catalog, target)
    assert resolved == {"COMMON": "from_target", "LOCAL": "local_val"}
    resolved["LOCAL"] = "mutated"
    assert target.env["LOCAL"] == "local_val"


def test_resolve_target_environment_never_mutates_os_environ() -> None:
    import os

    from refract.config import resolve_target_environment

    snapshot_items = dict(os.environ)
    target = TargetConfig(id="t", backend="codex", env={"TEST_RESOLVER_NEW_KEY": "val"})
    catalog = DaemonConfig(home=Path("/tmp"), targets=(target,))

    resolved = resolve_target_environment(catalog, target)

    assert resolved == {"TEST_RESOLVER_NEW_KEY": "val"}
    assert "PATH" not in resolved
    assert dict(os.environ) == snapshot_items
