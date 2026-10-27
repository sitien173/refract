from __future__ import annotations

from pathlib import Path

import pytest

from refract.config import (
    DaemonConfig,
    TargetConfig,
    load_config,
)


def _base_config_toml() -> str:
    return """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
"""


def test_readme_environment_examples_load_through_global_and_project_loaders(tmp_path) -> None:
    import re

    from refract.config import load_config_bytes, load_project_config

    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    global_match = re.search(r"## Target environments.*?```toml\n(.*?)\n```", readme, re.S)
    project_match = re.search(r"Project `\.refract/config\.toml`.*?```toml\n(.*?)\n```", readme, re.S)
    assert global_match and project_match
    config_path = tmp_path / "config.toml"
    base = load_config_bytes(global_match.group(1).encode(), config_path)
    root = tmp_path / "project"
    root.mkdir()
    merged = load_project_config(root, base, project_match.group(1).encode())
    target = merged.targets[0]
    assert target.envs_vars == ("service", "project_only")
    assert target.envs["TARGET_LABEL"] == "project-worker"
    assert merged.envs["service"]["BASE_URL"] == "https://project.example.invalid"


def test_existing_config_loads_with_empty_environment_defaults(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_base_config_toml(), encoding="utf-8")

    catalog = load_config(path)

    assert catalog.envs == {}
    assert catalog.targets[0].envs_vars == ()
    assert catalog.targets[0].envs == {}


def test_global_shared_sets_and_target_declarations_load(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[envs.shared_a]
VAR_A = "val_a"
EMPTY_VAL = ""

[envs.shared_b]
VAR_B = "val_b"

[[targets]]
id = "primary"
backend = "codex"
envs_vars = ["shared_a", "shared_b"]
envs = { TARGET_KEY = "target_val", EMPTY_LOCAL = "" }

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )

    catalog = load_config(path)

    assert catalog.envs == {
        "shared_a": {"VAR_A": "val_a", "EMPTY_VAL": ""},
        "shared_b": {"VAR_B": "val_b"},
    }
    target = catalog.targets[0]
    assert target.envs_vars == ("shared_a", "shared_b")
    assert target.envs == {"TARGET_KEY": "target_val", "EMPTY_LOCAL": ""}


def test_target_rejects_unknown_shared_set(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[envs.known]
KEY = "val"

[[targets]]
id = "primary"
backend = "codex"
envs_vars = ["known", "unknown_set"]

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown environment set"):
        load_config(path)


@pytest.mark.parametrize(
    ("section_header", "content"),
    [
        ("[envs.test]", 'NUMBER = 123'),
        ("[envs.test]", 'BOOL = true'),
        ("[envs.test]", 'ARRAY = ["a", "b"]'),
        ("[[targets]]\nid = 'primary'\nbackend = 'codex'\nenvs = { NUM = 123 }\n#", ""),
        ("[[targets]]\nid = 'primary'\nbackend = 'codex'\nenvs = { BOOL = false }\n#", ""),
    ],
)
def test_environment_values_must_be_strings(tmp_path, section_header, content) -> None:
    path = tmp_path / "config.toml"
    extra = f"{section_header}\n{content}\n"
    if "[[targets]]" in section_header:
        toml_text = f"""[daemon]
default_profile = "balanced"

{extra}

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
"""
    else:
        toml_text = f"""[daemon]
default_profile = "balanced"

{extra}

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
"""
    path.write_text(toml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="Environment values must be strings"):
        load_config(path)


@pytest.mark.parametrize(
    "invalid_key",
    ["", "FOO=BAR", "FOO\x00BAR"],
)
def test_environment_keys_cannot_be_empty_or_contain_equal_or_nul(tmp_path, invalid_key) -> None:
    path = tmp_path / "config.toml"
    # Write using raw formatting to test key
    if not invalid_key:
        key_repr = '""'
    elif "\x00" in invalid_key:
        key_repr = '"FOO\\u0000BAR"'
    else:
        key_repr = f'"{invalid_key}"'
    path.write_text(
        f"""[daemon]
default_profile = "balanced"

[envs.bad]
{key_repr} = "val"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Environment key"):
        load_config(path)


def test_environment_keys_cannot_use_protected_ask_prefix(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[envs.bad]
REFRACT_ASK_TOKEN = "stolen"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="protected prefix"):
        load_config(path)


def test_environment_values_cannot_contain_nul(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[envs.bad]
KEY = "val\\u0000with_nul"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="NUL"):
        load_config(path)


def test_target_envs_must_be_toml_table(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
envs = ["not", "a", "table"]

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="envs must be a TOML table"):
        load_config(path)


def test_target_envs_vars_must_be_list_of_strings(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
envs_vars = "not_a_list"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="envs_vars must be a list of strings"):
        load_config(path)


def test_raw_declarations_kept_out_of_dataclass_reprs(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        """[daemon]
default_profile = "balanced"

[envs.secret_set]
SECRET_API_KEY = "super-secret-marker-12345"

[[targets]]
id = "primary"
backend = "codex"
envs_vars = ["secret_set"]
envs = { TARGET_SECRET = "super-secret-target-marker-67890" }

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    catalog = load_config(path)
    target = catalog.targets[0]

    assert "super-secret-marker-12345" not in repr(catalog)
    assert "super-secret-target-marker-67890" not in repr(catalog)
    assert "super-secret-marker-12345" not in repr(target)
    assert "super-secret-target-marker-67890" not in repr(target)
    assert "secret_set" not in repr(target)
    assert "TARGET_SECRET" not in repr(target)
    assert "SECRET_API_KEY" not in repr(catalog)


def test_no_shared_mutable_defaults() -> None:
    t1 = TargetConfig(id="t1", backend="codex")
    t2 = TargetConfig(id="t2", backend="codex")
    assert t1.envs is not t2.envs
    t1.envs["MUTATED"] = "leak"
    assert "MUTATED" not in t2.envs



def test_project_shared_sets_merge_and_project_only_sets(tmp_path) -> None:
    from refract.config import load_project_config

    global_path = tmp_path / "config.toml"
    global_path.write_text(
        """[daemon]
default_profile = "balanced"

[envs.shared]
BASE_VAR = "base"
OVERRIDE_VAR = "base_val"

[[targets]]
id = "primary"
backend = "codex"
envs_vars = ["shared"]
envs = { LOCAL_A = "val_a" }

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    base = load_config(global_path)

    project_root = tmp_path / "project"
    (project_root / ".refract").mkdir(parents=True)
    project_config = project_root / ".refract" / "config.toml"
    project_config.write_text(
        """[envs.shared]
OVERRIDE_VAR = "project_val"
PROJECT_VAR = "project_added"

[envs.project_only]
SOLO = "solo_val"
""",
        encoding="utf-8",
    )

    overlaid = load_project_config(project_root, base)

    assert overlaid.envs["shared"] == {
        "BASE_VAR": "base",
        "OVERRIDE_VAR": "project_val",
        "PROJECT_VAR": "project_added",
    }
    assert overlaid.envs["project_only"] == {"SOLO": "solo_val"}
    # Base unchanged
    assert base.envs["shared"] == {
        "BASE_VAR": "base",
        "OVERRIDE_VAR": "base_val",
    }
    assert "project_only" not in base.envs


def test_project_target_overlay_precedence_and_replacement(tmp_path) -> None:
    from refract.config import load_project_config

    global_path = tmp_path / "config.toml"
    global_path.write_text(
        """[daemon]
default_profile = "balanced"

[envs.global_set]
VAR_G = "g"

[[targets]]
id = "primary"
backend = "codex"
args = ["--default-arg"]
envs_vars = ["global_set"]
envs = { KEY_1 = "g1", KEY_2 = "g2" }

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    base = load_config(global_path)

    project_root = tmp_path / "project"
    (project_root / ".refract").mkdir(parents=True)
    project_config = project_root / ".refract" / "config.toml"
    project_config.write_text(
        """[envs.project_set]
VAR_P = "p"

[[targets]]
id = "primary"
envs_vars = ["project_set"]
envs = { KEY_2 = "p2", KEY_3 = "p3" }
""",
        encoding="utf-8",
    )

    overlaid = load_project_config(project_root, base)
    target = overlaid.targets[0]

    assert target.envs_vars == ("project_set",)
    assert target.envs == {"KEY_1": "g1", "KEY_2": "p2", "KEY_3": "p3"}
    # Unrelated target policy preserved
    assert target.backend == "codex"
    assert target.args == ("--default-arg",)

    # Base target unchanged
    assert base.targets[0].envs_vars == ("global_set",)
    assert base.targets[0].envs == {"KEY_1": "g1", "KEY_2": "g2"}


def test_project_target_explicit_empty_envs_vars_clears_selection(tmp_path) -> None:
    from refract.config import load_project_config

    global_path = tmp_path / "config.toml"
    global_path.write_text(
        """[daemon]
default_profile = "balanced"

[envs.global_set]
VAR_G = "g"

[[targets]]
id = "primary"
backend = "codex"
envs_vars = ["global_set"]

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    base = load_config(global_path)

    project_root = tmp_path / "project"
    (project_root / ".refract").mkdir(parents=True)
    project_config = project_root / ".refract" / "config.toml"
    project_config.write_text(
        """[[targets]]
id = "primary"
envs_vars = []
""",
        encoding="utf-8",
    )

    overlaid = load_project_config(project_root, base)
    assert overlaid.targets[0].envs_vars == ()


def test_project_target_omitted_envs_vars_inherits(tmp_path) -> None:
    from refract.config import load_project_config

    global_path = tmp_path / "config.toml"
    global_path.write_text(
        """[daemon]
default_profile = "balanced"

[envs.global_set]
VAR_G = "g"

[[targets]]
id = "primary"
backend = "codex"
envs_vars = ["global_set"]
envs = { OLD = "val" }

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    base = load_config(global_path)

    project_root = tmp_path / "project"
    (project_root / ".refract").mkdir(parents=True)
    project_config = project_root / ".refract" / "config.toml"
    project_config.write_text(
        """[[targets]]
id = "primary"
envs = { NEW = "val" }
""",
        encoding="utf-8",
    )

    overlaid = load_project_config(project_root, base)
    assert overlaid.targets[0].envs_vars == ("global_set",)
    assert overlaid.targets[0].envs == {"OLD": "val", "NEW": "val"}


def test_project_target_empty_local_envs_does_not_delete_inherited(tmp_path) -> None:
    from refract.config import load_project_config

    global_path = tmp_path / "config.toml"
    global_path.write_text(
        """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
envs = { KEEP_ME = "val" }

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    base = load_config(global_path)

    project_root = tmp_path / "project"
    (project_root / ".refract").mkdir(parents=True)
    project_config = project_root / ".refract" / "config.toml"
    project_config.write_text(
        """[[targets]]
id = "primary"
envs = {}
""",
        encoding="utf-8",
    )

    overlaid = load_project_config(project_root, base)
    assert overlaid.targets[0].envs == {"KEEP_ME": "val"}


def test_project_target_rejects_unknown_target_id(tmp_path) -> None:
    from refract.config import load_project_config

    global_path = tmp_path / "config.toml"
    global_path.write_text(_base_config_toml(), encoding="utf-8")
    base = load_config(global_path)

    project_root = tmp_path / "project"
    (project_root / ".refract").mkdir(parents=True)
    project_config = project_root / ".refract" / "config.toml"
    project_config.write_text(
        """[[targets]]
id = "nonexistent_target"
envs = { KEY = "val" }
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown project target override"):
        load_project_config(project_root, base)


def test_project_target_rejects_duplicate_target_overrides(tmp_path) -> None:
    from refract.config import load_project_config

    global_path = tmp_path / "config.toml"
    global_path.write_text(_base_config_toml(), encoding="utf-8")
    base = load_config(global_path)

    project_root = tmp_path / "project"
    (project_root / ".refract").mkdir(parents=True)
    project_config = project_root / ".refract" / "config.toml"
    project_config.write_text(
        """[[targets]]
id = "primary"
envs = { A = "1" }

[[targets]]
id = "primary"
envs = { B = "2" }
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate project target override"):
        load_project_config(project_root, base)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("backend", '"pi"'),
        ("model", '"gpt-4"'),
        ("args", '["--some-arg"]'),
        ("isolated", "true"),
        ("read_only", "true"),
        ("max_concurrency", "5"),
        ("retry_policy", '"some_policy"'),
    ],
)
def test_project_target_rejects_non_environment_fields(tmp_path, field, value) -> None:
    from refract.config import load_project_config

    global_path = tmp_path / "config.toml"
    global_path.write_text(_base_config_toml(), encoding="utf-8")
    base = load_config(global_path)

    project_root = tmp_path / "project"
    (project_root / ".refract").mkdir(parents=True)
    project_config = project_root / ".refract" / "config.toml"
    project_config.write_text(
        f"""[[targets]]
id = "primary"
{field} = {value}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Project target override has unsupported settings"):
        load_project_config(project_root, base)


def test_independent_project_catalogs_and_global_isolation(tmp_path) -> None:
    from refract.config import load_project_config

    global_path = tmp_path / "config.toml"
    global_path.write_text(
        """[daemon]
default_profile = "balanced"

[envs.common]
VAR = "global"

[[targets]]
id = "primary"
backend = "codex"
envs_vars = ["common"]
envs = { LOC = "global_loc" }

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
        encoding="utf-8",
    )
    base = load_config(global_path)

    proj1_root = tmp_path / "proj1"
    (proj1_root / ".refract").mkdir(parents=True)
    (proj1_root / ".refract" / "config.toml").write_text(
        """[envs.common]
VAR = "proj1"

[[targets]]
id = "primary"
envs = { LOC = "proj1_loc" }
""",
        encoding="utf-8",
    )

    proj2_root = tmp_path / "proj2"
    (proj2_root / ".refract").mkdir(parents=True)
    (proj2_root / ".refract" / "config.toml").write_text(
        """[envs.common]
VAR = "proj2"

[[targets]]
id = "primary"
envs = { LOC = "proj2_loc" }
""",
        encoding="utf-8",
    )

    p1 = load_project_config(proj1_root, base)
    p2 = load_project_config(proj2_root, base)

    assert base.envs["common"]["VAR"] == "global"
    assert base.targets[0].envs["LOC"] == "global_loc"

    assert p1.envs["common"]["VAR"] == "proj1"
    assert p1.targets[0].envs["LOC"] == "proj1_loc"

    assert p2.envs["common"]["VAR"] == "proj2"
    assert p2.targets[0].envs["LOC"] == "proj2_loc"



def test_resolve_target_environment_precedence_and_returns_only_configured() -> None:
    from refract.config import resolve_target_environment

    catalog = DaemonConfig(
        home=Path("/tmp"),
        targets=(
            TargetConfig(
                id="target1",
                backend="codex",
                envs_vars=("set_a", "set_b"),
                envs={"COMMON": "from_target", "LOCAL": "local_val", "REF_COMMON": "${COMMON}"},
            ),
        ),
        envs={
            "set_a": {"COMMON": "from_set_a", "A_VAL": "a"},
            "set_b": {"COMMON": "from_set_b", "B_VAL": "b"},
        },
    )
    inherited = {"COMMON": "from_inherited", "INHERITED_ONLY": "inherited_literal"}

    resolved = resolve_target_environment(catalog, "target1", inherited=inherited)

    assert resolved == {
        "COMMON": "from_target",
        "A_VAL": "a",
        "B_VAL": "b",
        "LOCAL": "local_val",
        "REF_COMMON": "from_target",
    }
    assert "INHERITED_ONLY" not in resolved


def test_resolve_target_environment_forward_references() -> None:
    from refract.config import resolve_target_environment

    catalog = DaemonConfig(
        home=Path("/tmp"),
        targets=(
            TargetConfig(
                id="t",
                backend="codex",
                envs={"FIRST": "${SECOND}", "SECOND": "${THIRD}", "THIRD": "final_val"},
            ),
        ),
    )
    resolved = resolve_target_environment(catalog, "t", inherited={})
    assert resolved["FIRST"] == "final_val"
    assert resolved["SECOND"] == "final_val"
    assert resolved["THIRD"] == "final_val"


def test_resolve_target_environment_inherited_only_literal_never_expanded() -> None:
    from refract.config import resolve_target_environment

    catalog = DaemonConfig(
        home=Path("/tmp"),
        targets=(
            TargetConfig(
                id="t",
                backend="codex",
                envs={"USE_INHERITED": "${INHERITED_WITH_TEMPLATE}/suffix"},
            ),
        ),
    )
    inherited = {"INHERITED_WITH_TEMPLATE": "${NOT_A_TEMPLATE}"}

    resolved = resolve_target_environment(catalog, "t", inherited=inherited)
    assert resolved["USE_INHERITED"] == "${NOT_A_TEMPLATE}/suffix"


def test_resolve_target_environment_escaping_and_bare_dollar() -> None:
    from refract.config import resolve_target_environment

    catalog = DaemonConfig(
        home=Path("/tmp"),
        targets=(
            TargetConfig(
                id="t",
                backend="codex",
                envs={
                    "DOLLAR": "$$",
                    "ESCAPED_REF": "$${NOT_EXPANDED}",
                    "BARE": "$BARE_VAR",
                    "MIXED": "start$$mid$${ESCAPED}${REAL}end",
                    "REAL": "real_val",
                },
            ),
        ),
    )
    resolved = resolve_target_environment(catalog, "t", inherited={})
    assert resolved["DOLLAR"] == "$"
    assert resolved["ESCAPED_REF"] == "${NOT_EXPANDED}"
    assert resolved["BARE"] == "$BARE_VAR"
    assert resolved["MIXED"] == "start$mid${ESCAPED}real_valend"


def test_resolve_target_environment_missing_reference_fails() -> None:
    from refract.config import resolve_target_environment

    catalog = DaemonConfig(
        home=Path("/tmp"),
        targets=(
            TargetConfig(
                id="t",
                backend="codex",
                envs={"KEY": "${MISSING_VARIABLE}"},
            ),
        ),
    )
    with pytest.raises(ValueError, match="Missing environment reference"):
        resolve_target_environment(catalog, "t", inherited={})


def test_resolve_target_environment_direct_self_reference_cycle() -> None:
    from refract.config import resolve_target_environment

    catalog = DaemonConfig(
        home=Path("/tmp"),
        targets=(
            TargetConfig(
                id="t",
                backend="codex",
                envs={"SELF": "${SELF}"},
            ),
        ),
    )
    # Even if SELF exists in inherited environment!
    with pytest.raises(ValueError, match="Environment reference cycle detected"):
        resolve_target_environment(catalog, "t", inherited={"SELF": "existing"})


def test_resolve_target_environment_indirect_cycle() -> None:
    from refract.config import resolve_target_environment

    catalog = DaemonConfig(
        home=Path("/tmp"),
        targets=(
            TargetConfig(
                id="t",
                backend="codex",
                envs={"A": "${B}", "B": "${C}", "C": "${A}"},
            ),
        ),
    )
    with pytest.raises(ValueError, match="Environment reference cycle detected"):
        resolve_target_environment(catalog, "t", inherited={})


def test_resolve_target_environment_long_chain_no_recursion_limit() -> None:
    from refract.config import resolve_target_environment

    chain_length = 2000
    envs = {"V0": "base_val"}
    for i in range(1, chain_length + 1):
        envs[f"V{i}"] = f"${{V{i - 1}}}"

    catalog = DaemonConfig(
        home=Path("/tmp"),
        targets=(
            TargetConfig(
                id="t",
                backend="codex",
                envs=envs,
            ),
        ),
    )
    resolved = resolve_target_environment(catalog, "t", inherited={})
    assert resolved[f"V{chain_length}"] == "base_val"


def test_resolve_target_environment_rejects_unterminated_or_empty_ref() -> None:
    from refract.config import resolve_target_environment

    catalog1 = DaemonConfig(
        home=Path("/tmp"),
        targets=(TargetConfig(id="t", backend="codex", envs={"BAD": "${UNCLOSED"}),),
    )
    with pytest.raises(ValueError, match="Unterminated environment reference"):
        resolve_target_environment(catalog1, "t", inherited={})

    catalog2 = DaemonConfig(
        home=Path("/tmp"),
        targets=(TargetConfig(id="t", backend="codex", envs={"BAD": "${}"}),),
    )
    with pytest.raises(ValueError, match="Empty environment reference"):
        resolve_target_environment(catalog2, "t", inherited={})

    catalog3 = DaemonConfig(
        home=Path("/tmp"),
        targets=(TargetConfig(id="t", backend="codex", envs={"BAD": "${   }"}),),
    )
    with pytest.raises(ValueError, match="Empty environment reference"):
        resolve_target_environment(catalog3, "t", inherited={})


def test_resolve_target_environment_protected_ask_name_rejected_unless_escaped() -> None:
    from refract.config import resolve_target_environment

    catalog = DaemonConfig(
        home=Path("/tmp"),
        targets=(TargetConfig(id="t", backend="codex", envs={"BAD": "${REFRACT_ASK_TOKEN}"}),),
    )
    with pytest.raises(ValueError, match="Protected environment reference"):
        resolve_target_environment(catalog, "t", inherited={"REFRACT_ASK_TOKEN": "secret"})

    # Escaped reference produces literal and is NOT rejected
    catalog_escaped = DaemonConfig(
        home=Path("/tmp"),
        targets=(TargetConfig(id="t", backend="codex", envs={"OK": "$${REFRACT_ASK_TOKEN}"}),),
    )
    resolved = resolve_target_environment(catalog_escaped, "t", inherited={})
    assert resolved["OK"] == "${REFRACT_ASK_TOKEN}"


def test_resolve_target_environment_never_mutates_os_environ() -> None:
    import os
    from refract.config import resolve_target_environment

    snapshot_keys = set(os.environ.keys())
    snapshot_items = dict(os.environ)

    catalog = DaemonConfig(
        home=Path("/tmp"),
        targets=(
            TargetConfig(
                id="t",
                backend="codex",
                envs={"TEST_RESOLVER_NEW_KEY": "val", "CUSTOM_PATH": "${PATH}"},
            ),
        ),
    )
    # Default inherited (None) reads os.environ
    resolved = resolve_target_environment(catalog, "t")
    assert "TEST_RESOLVER_NEW_KEY" in resolved
    assert "CUSTOM_PATH" in resolved

    assert set(os.environ.keys()) == snapshot_keys
    assert dict(os.environ) == snapshot_items



def test_resolve_target_environment_errors_are_strictly_structural_without_markers() -> None:
    from refract.config import resolve_target_environment

    marker = "SYNTHETIC_PRIVATE_MARKER_98765"

    # Unknown target
    catalog_empty = DaemonConfig(home=Path("/tmp"), targets=())
    with pytest.raises(ValueError) as exc_info:
        resolve_target_environment(catalog_empty, f"unknown_target_{marker}")
    assert str(exc_info.value) == "Unknown target"
    assert marker not in str(exc_info.value)

    # Missing reference
    catalog_missing = DaemonConfig(
        home=Path("/tmp"),
        targets=(TargetConfig(id="t", backend="codex", envs={"K": f"${{REF_{marker}}}"}),),
    )
    with pytest.raises(ValueError) as exc_info:
        resolve_target_environment(catalog_missing, "t", inherited={})
    assert str(exc_info.value) == "Missing environment reference"
    assert marker not in str(exc_info.value)

    # Direct self-cycle
    catalog_cycle = DaemonConfig(
        home=Path("/tmp"),
        targets=(TargetConfig(id="t", backend="codex", envs={f"SELF_{marker}": f"${{SELF_{marker}}}"}),),
    )
    with pytest.raises(ValueError) as exc_info:
        resolve_target_environment(catalog_cycle, "t", inherited={})
    assert str(exc_info.value) == "Environment reference cycle detected"
    assert marker not in str(exc_info.value)

    # Protected REFRACT_ASK_* reference containing marker
    catalog_protected = DaemonConfig(
        home=Path("/tmp"),
        targets=(TargetConfig(id="t", backend="codex", envs={"K": f"${{REFRACT_ASK_{marker}}}"}),),
    )
    with pytest.raises(ValueError) as exc_info:
        resolve_target_environment(catalog_protected, "t", inherited={})
    assert str(exc_info.value) == "Protected environment reference"
    assert marker not in str(exc_info.value)
