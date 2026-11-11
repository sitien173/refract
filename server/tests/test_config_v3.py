from __future__ import annotations

import dataclasses
import re
from tomllib import TOMLDecodeError

import pytest

from refract.config import (
    DaemonConfig,
    LoggingConfig,
    ProfileDeclaration,
    RetryPolicy,
    TargetConfig,
    TargetSelection,
    load_config,
    load_project_config,
    resolve_target_environment,
    _load_project_config_values,
    _logging_config,
    _targets,
)
from refract.planning import resolve_execution_plan
from refract.workflows import get_workflow
from tests.orchestration_helpers import Raised, outcome, plain


_BASE = """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
{target_extra}

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
{profile_extra}
{sections}
"""


def _global(target_extra: str = "", profile_extra: str = "", sections: str = "") -> str:
    return _BASE.format(
        target_extra=target_extra, profile_extra=profile_extra, sections=sections
    )


def _load_global(tmp_path, text: str) -> DaemonConfig:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return load_config(path)


def _load_project(tmp_path, base: DaemonConfig, text: str) -> DaemonConfig:
    root = tmp_path / "project"
    (root / ".refract").mkdir(parents=True, exist_ok=True)
    (root / ".refract" / "config.toml").write_text(text, encoding="utf-8")
    return load_project_config(root, base)


# Split literals keep removed names out of repository-wide greps.
_LF = "lang" "fuse"
_HIST = "history" "_turns"
_HIST_BYTES = "history" "_bytes"
_POLICIES = "retry" "Policies"
_POLICY = "retry" "Policy"
_ENV_SETS = "envs" "_vars"
_WINDOW = "context" "Window"

# (removed key, replacement hint, layer, global text or project overlay text)
_REMOVED = [
    (f"[{_LF}]", "", "global", _global(sections=f"[{_LF}]\nenabled = true\n")),
    (f"[daemon].{_HIST}", "", "global", _global().replace(
        'default_profile = "balanced"', f'default_profile = "balanced"\n{_HIST} = 8')),
    (f"[daemon].{_HIST_BYTES}", "", "global", _global().replace(
        'default_profile = "balanced"', f'default_profile = "balanced"\n{_HIST_BYTES} = 8')),
    (f"[{_POLICIES}]", "use targets[].retry", "global",
     _global(sections=f"[{_POLICIES}.fast]\nretry_attempt = 1\n")),
    ("[envs]", "use targets[].env", "global", _global(sections="[envs.shared]\nA = \"1\"\n")),
    (f"targets[].{_POLICY}", "use targets[].retry", "global",
     _global(target_extra=f'{_POLICY} = "fast"')),
    (f"targets[].{_ENV_SETS}", "use targets[].env", "global",
     _global(target_extra=f'{_ENV_SETS} = ["shared"]')),
    ("targets[].envs", "use targets[].env", "global", _global(target_extra='envs = { A = "1" }')),
    (f"targets[].{_WINDOW}", "use targets[].context_window", "global",
     _global(target_extra=f"{_WINDOW} = 1000")),
    ("targets[].profile", "use targets[].backend_profile", "global",
     _global(target_extra='profile = "work"')),
    ("profiles workflow max_attempts", "use targets[].retry.attempts", "global",
     _global().replace('implement = "primary"',
                       'implement = { targets = ["primary"], max_attempts = 2 }')),
    ("${NAME} in targets[].env", "write the literal value", "global",
     _global(target_extra='env = { A = "${HOME}" }')),
    ("[logging].format", "", "global", _global(sections='[logging]\nformat = "json"\n')),
    ("[logging].console", "", "global", _global(sections="[logging]\nconsole = true\n")),
    ("[logging].capture_warnings", "", "global",
     _global(sections="[logging]\ncapture_warnings = true\n")),
    ("[project]", "pass profile on submit", "project", '[project]\ndefault_profile = "balanced"\n'),
    ("[envs]", "use targets[].env", "project", '[envs.shared]\nA = "1"\n'),
    (f"targets[].{_ENV_SETS}", "use targets[].env", "project",
     f'[[targets]]\nid = "primary"\n{_ENV_SETS} = ["shared"]\n'),
    ("targets[].envs", "use targets[].env", "project",
     '[[targets]]\nid = "primary"\nenvs = { A = "1" }\n'),
    ("${NAME} in targets[].env", "write the literal value", "project",
     '[[targets]]\nid = "primary"\nenv = { A = "${HOME}" }\n'),
]


@pytest.mark.parametrize(
    ("key", "hint", "layer", "text"),
    _REMOVED,
    ids=[f"{layer}:{key}" for key, _, layer, _ in _REMOVED],
)
def test_removed_key_fails_load_with_replacement_hint(tmp_path, key, hint, layer, text) -> None:
    expected = f"{key} has been removed" + (f"; {hint}" if hint else "")
    base = _load_global(tmp_path, _global()) if layer != "global" else None
    with pytest.raises(ValueError) as caught:
        if layer == "global":
            _load_global(tmp_path, text)
        else:
            _load_project(tmp_path, base, text)
    # The sanitizer must let the exact message through, not a generic error.
    assert re.search(re.escape(expected) + r"$", str(caught.value)), str(caught.value)


def test_target_config_has_exact_v3_fields() -> None:
    assert [field.name for field in dataclasses.fields(TargetConfig)] == [
        "id", "backend", "model", "backend_profile", "reasoning", "system_prompt",
        "isolated", "read_only", "args", "max_concurrency", "context_window",
        "retry", "env",
    ]
    assert [field.name for field in dataclasses.fields(RetryPolicy)] == [
        "attempts", "codes", "patterns",
    ]
    assert [field.name for field in dataclasses.fields(LoggingConfig)] == [
        "level", "file", "max_bytes", "backup_count",
    ]
    names = {field.name for field in dataclasses.fields(DaemonConfig)}
    assert not names & {"retry_policies", "envs", "project_profile_declarations"}


def test_inline_retry_context_window_and_literal_env_load(tmp_path) -> None:
    catalog = _load_global(tmp_path, _global(target_extra="""context_window = 200000
retry = { attempts = 2, codes = ["rate_limit"], patterns = ["overloaded"] }
env = { API_URL = "https://example.invalid", MODE = "$literal" }"""))

    target = catalog.targets[0]
    assert target.context_window == 200000
    assert target.retry == RetryPolicy(attempts=2, codes=("rate_limit",), patterns=("overloaded",))
    assert target.env == {"API_URL": "https://example.invalid", "MODE": "$literal"}
    assert resolve_target_environment(catalog, target) == target.env


def test_retry_defaults_to_no_retry(tmp_path) -> None:
    target = _load_global(tmp_path, _global()).targets[0]
    assert target.retry == RetryPolicy(attempts=0, codes=(), patterns=())
    assert target.env == {}


def test_empty_inline_retry_table_means_no_retry(tmp_path) -> None:
    target = _load_global(tmp_path, _global(target_extra="retry = {}")).targets[0]
    assert target.retry == RetryPolicy(attempts=0, codes=(), patterns=())


@pytest.mark.parametrize(
    "retry",
    [
        "{ attempts = -1 }",
        "{ attempts = true }",
        "{ attempts = false }",
        "{ attempts = 1.5 }",
        '{ attempts = "2" }',
        '{ codes = "rate_limit" }',
        "{ codes = [123] }",
        '{ codes = [""] }',
        '{ patterns = "temporarily unavailable" }',
        "{ patterns = [1] }",
        "{ patterns = [false] }",
        '{ patterns = [""] }',
        "{ unknown = 1 }",
        "2",
    ],
)
def test_malformed_inline_retry_is_rejected(tmp_path, retry) -> None:
    text = _global(target_extra=f"retry = {retry}")
    with pytest.raises(ValueError, match=r"Target has invalid retry settings"):
        _load_global(tmp_path, text)


def test_unknown_target_setting_is_rejected(tmp_path) -> None:
    text = _global(target_extra='capabilities = ["code"]')
    with pytest.raises(ValueError, match=r"Unsupported target settings"):
        _load_global(tmp_path, text)


def test_project_overlay_adds_profile_and_merges_existing_target_env(tmp_path) -> None:
    base = _load_global(tmp_path, _global(target_extra='env = { A = "global", B = "global" }'))
    resolved = _load_project(tmp_path, base, """[profiles.fast]
extends = "balanced"
review = "primary"

[[targets]]
id = "primary"
env = { B = "project", C = "project" }
""")

    assert resolve_execution_plan(get_workflow("implement"), resolved, "fast").selection.targets == ("primary",)
    assert resolved.targets[0].env == {"A": "global", "B": "project", "C": "project"}
    assert base.targets[0].env == {"A": "global", "B": "global"}


def test_project_overlay_cannot_add_targets(tmp_path) -> None:
    base = _load_global(tmp_path, _global())
    with pytest.raises(ValueError, match=r"Project config cannot add targets"):
        _load_project(tmp_path, base, '[[targets]]\nid = "local"\nenv = { A = "1" }\n')


def test_project_overlay_target_accepts_only_env(tmp_path) -> None:
    base = _load_global(tmp_path, _global())
    with pytest.raises(ValueError, match=r"Unsupported project target settings"):
        _load_project(tmp_path, base, '[[targets]]\nid = "primary"\nargs = ["--yolo"]\n')


def test_project_overlay_rejects_other_sections(tmp_path) -> None:
    base = _load_global(tmp_path, _global())
    with pytest.raises(ValueError, match=r"Unsupported project config sections"):
        _load_project(tmp_path, base, "[daemon]\nmax_jobs = 9\n")


def test_project_overlay_rejects_global_telemetry(tmp_path) -> None:
    base = _load_global(tmp_path, _global())
    with pytest.raises(ValueError, match=r"Unsupported project config sections"):
        _load_project(tmp_path, base, "[telemetry]\nenabled = true\n")


def test_telemetry_endpoint_is_ignored_and_recorded(tmp_path) -> None:
    config = _load_global(tmp_path, _global() + '\n[telemetry]\nendpoint = "x"\n')
    assert config.ignored_keys == ("telemetry.endpoint",)


def test_missing_telemetry_endpoint_has_no_ignored_keys(tmp_path) -> None:
    config = _load_global(tmp_path, _global())
    assert config.ignored_keys == ()


def test_leftover_pricing_section_loads_and_is_reported_as_ignored(tmp_path) -> None:
    config = _load_global(
        tmp_path,
        _global() + '\n[pricing]\ncurrency = "EUR"\n[pricing.models.m]\ninput = "bad"\n',
    )
    assert config.ignored_keys == ("pricing",)
    assert not hasattr(config, "pricing")


def test_leftover_pricing_and_telemetry_endpoint_are_both_ignored(tmp_path) -> None:
    config = _load_global(
        tmp_path, _global() + '\n[telemetry]\nendpoint = "x"\n[pricing]\ncurrency = "USD"\n',
    )
    assert config.ignored_keys == ("telemetry.endpoint", "pricing")


def test_project_overlay_rejects_global_pricing(tmp_path) -> None:
    base = _load_global(tmp_path, _global())
    with pytest.raises(ValueError, match=r"Unsupported project config sections"):
        _load_project(tmp_path, base, "[pricing]\ncurrency = 'USD'\n")


def test_example_v3_config_loads_and_covers_every_key(tmp_path, monkeypatch) -> None:
    import tomllib
    from pathlib import Path

    from refract.config import _TARGET_KEYS

    monkeypatch.setenv("REFRACT_HOME", str(tmp_path))
    path = Path(__file__).resolve().parents[1] / "config.v3.toml"
    config = load_config(path)
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    assert {target.backend for target in config.targets} == {"agy", "codex", "pi", "claude"}
    assert set().union(*(set(item) for item in raw["targets"])) == _TARGET_KEYS
    assert set(raw["daemon"]) == {
        "host", "port", "max_jobs", "default_profile", "breaker_failure_threshold",
        "breaker_base_cooldown_s", "breaker_max_cooldown_s", "ask_timeout_s",
    }
    assert set(raw["logging"]) == {"level", "file", "max_bytes", "backup_count"}
    assert set(raw["notifications"]) == {"enabled"}
    assert set(raw["telemetry"]) == {"enabled"}
    assert config.telemetry.enabled is False
    assert config.ignored_keys == ()
    assert "pricing" not in raw
    assert not hasattr(config, "pricing")
    profiles = raw["profiles"].values()
    assert any("extends" in profile for profile in profiles)
    workflow_values = [
        value for profile in profiles for key, value in profile.items() if key != "extends"
    ]
    assert any(isinstance(value, str) for value in workflow_values)
    assert any(isinstance(value, list) for value in workflow_values)
    assert any(isinstance(value, dict) and "timeout_s" in value for value in workflow_values)
    env_values = [value for target in config.targets for value in target.env.values()]
    assert env_values
    assert all("example" in value or "replace-me" in value for value in env_values)


# Characterization of private config helpers. Expected values were recorded from
# the implementation before the complexity refactor; every case pins the result
# or the exact error text, and the "*_before_*" cases pin which error wins.

_TARGETS_CASES = {
    "dict_empty": ({}, Raised(ValueError, "[targets] must contain at least one target")),
    "dict_nonempty": ({"a": 1}, Raised(ValueError, "[targets] must be a TOML array of tables")),
    "str": ("x", Raised(ValueError, "[targets] must be a TOML array of tables")),
    "none": (None, Raised(ValueError, "[targets] must be a TOML array of tables")),
    "tuple": ((), Raised(ValueError, "[targets] must be a TOML array of tables")),
    "list_empty": ([], Raised(ValueError, "[targets] must contain at least one target")),
    "item_not_dict": (["x"], Raised(ValueError, "Each target must be a TOML table")),
    "item_none": ([None], Raised(ValueError, "Each target must be a TOML table")),
    "missing_id": ([{"backend": "codex"}], Raised(ValueError, "Invalid target declaration")),
    "blank_id": ([{"id": "  ", "backend": "codex"}], Raised(ValueError, "Invalid target declaration")),
    "int_id": ([{"id": 5, "backend": "codex"}], Raised(ValueError, "Invalid target declaration")),
    "missing_backend": ([{"id": "t"}], Raised(ValueError, "Invalid target declaration")),
    "bad_backend": ([{"id": "t", "backend": "nope"}], Raised(ValueError, "Invalid target declaration")),
    "int_backend": ([{"id": "t", "backend": 1}], Raised(ValueError, "Invalid target declaration")),
    "padded_ok": ([{"id": " t ", "backend": " pi "}], [TargetConfig("t", "pi")]),
    "all_backends": (
        [
            {"id": "a", "backend": "agy"},
            {"id": "b", "backend": "codex"},
            {"id": "c", "backend": "pi"},
            {"id": "d", "backend": "claude"},
        ],
        [
            TargetConfig("a", "agy"),
            TargetConfig("b", "codex"),
            TargetConfig("c", "pi"),
            TargetConfig("d", "claude"),
        ],
    ),
    "removed_key": (
        [{"id": "t", "backend": "codex", "profile": "x"}],
        Raised(ValueError, "targets[].profile has been removed; use targets[].backend_profile"),
    ),
    "removed_key_envs": (
        [{"id": "t", "backend": "codex", "envs": {}}],
        Raised(ValueError, "targets[].envs has been removed; use targets[].env"),
    ),
    "unknown_key": (
        [{"id": "t", "backend": "codex", "zzz": 1, "yyy": 2}],
        Raised(ValueError, "Unsupported target settings: ['yyy', 'zzz']"),
    ),
    "removed_before_unknown": (
        [{"id": "t", "backend": "codex", "zzz": 1, "profile": "x"}],
        Raised(ValueError, "targets[].profile has been removed; use targets[].backend_profile"),
    ),
    "args_not_list": (
        [{"id": "t", "backend": "codex", "args": "--x"}],
        Raised(ValueError, "Target 't' args must be a list of strings"),
    ),
    "args_nonstring": (
        [{"id": "t", "backend": "codex", "args": ["--x", 1]}],
        Raised(ValueError, "Target 't' args must be a list of strings"),
    ),
    "args_ok": (
        [{"id": "t", "backend": "codex", "args": ["--x", "y"]}],
        [TargetConfig("t", "codex", args=("--x", "y"))],
    ),
    "isolated_bad": (
        [{"id": "t", "backend": "codex", "isolated": "yes"}],
        Raised(ValueError, "Target 't' isolated must be true or false"),
    ),
    "read_only_bad": (
        [{"id": "t", "backend": "codex", "read_only": 1}],
        Raised(ValueError, "Target 't' read_only must be true or false"),
    ),
    "flags_ok": (
        [{"id": "t", "backend": "pi", "isolated": True, "read_only": True}],
        [TargetConfig("t", "pi", isolated=True, read_only=True)],
    ),
    "model_int": (
        [{"id": "t", "backend": "codex", "model": 1}],
        Raised(ValueError, "Target 't' settings must be strings: ['model']"),
    ),
    "reasoning_int": (
        [{"id": "t", "backend": "codex", "reasoning": 2}],
        Raised(ValueError, "Target 't' settings must be strings: ['reasoning']"),
    ),
    "system_prompt_int": (
        [{"id": "t", "backend": "codex", "system_prompt": 3}],
        Raised(ValueError, "Target 't' settings must be strings: ['system_prompt']"),
    ),
    "two_text_bad": (
        [{"id": "t", "backend": "codex", "model": 1, "system_prompt": 3}],
        Raised(ValueError, "Target 't' settings must be strings: ['model', 'system_prompt']"),
    ),
    "text_ok": (
        [{"id": "t", "backend": "codex", "model": "m", "reasoning": "r", "system_prompt": "s"}],
        [TargetConfig("t", "codex", model="m", reasoning="r", system_prompt="s")],
    ),
    "backend_profile_int": (
        [{"id": "t", "backend": "codex", "backend_profile": 3}],
        Raised(ValueError, "Target 't' backend_profile must be a string"),
    ),
    "backend_profile_ok": (
        [{"id": "t", "backend": "codex", "backend_profile": "bp"}],
        [TargetConfig("t", "codex", backend_profile="bp")],
    ),
    "backend_profile_none": (
        [{"id": "t", "backend": "codex", "backend_profile": None}],
        [TargetConfig("t", "codex")],
    ),
    "codex_cd": (
        [{"id": "t", "backend": "codex", "args": ["--cd", "/x"]}],
        Raised(ValueError, "Codex target 't' args cannot override the workspace root"),
    ),
    "pi_isolated_ext": (
        [{"id": "t", "backend": "pi", "isolated": True, "args": ["-e", "x"]}],
        Raised(
            ValueError,
            "Isolated Pi target 't' cannot explicitly load extensions, skills, or prompt templates",
        ),
    ),
    "pi_not_isolated_ext": (
        [{"id": "t", "backend": "pi", "args": ["-e", "x"]}],
        [TargetConfig("t", "pi", args=("-e", "x"))],
    ),
    "dashdash": (
        [{"id": "t", "backend": "codex", "args": ["--"]}],
        Raised(ValueError, "Target 't' args cannot contain the reserved '--' token"),
    ),
    "nul_arg": (
        [{"id": "t", "backend": "codex", "args": ["a\x00"]}],
        Raised(ValueError, "Target 't' args cannot contain NUL bytes"),
    ),
    "max_concurrency_ok": (
        [{"id": "t", "backend": "codex", "max_concurrency": 3}],
        [TargetConfig("t", "codex", max_concurrency=3)],
    ),
    "max_concurrency_zero": (
        [{"id": "t", "backend": "codex", "max_concurrency": 0}],
        Raised(ValueError, "Target 't' max_concurrency must be a positive integer"),
    ),
    "context_window_ok": (
        [{"id": "t", "backend": "codex", "context_window": 1000}],
        [TargetConfig("t", "codex", context_window=1000)],
    ),
    "context_window_zero": (
        [{"id": "t", "backend": "codex", "context_window": 0}],
        Raised(ValueError, "Target 't' context_window must be a positive integer"),
    ),
    "retry_ok": (
        [{"id": "t", "backend": "codex", "retry": {"attempts": 2, "codes": ["x"], "patterns": ["y"]}}],
        [TargetConfig("t", "codex", retry=RetryPolicy(2, ("x",), ("y",)))],
    ),
    "retry_bad": (
        [{"id": "t", "backend": "codex", "retry": []}],
        Raised(ValueError, "Target 't' has invalid retry settings"),
    ),
    "env_ok": (
        [{"id": "t", "backend": "codex", "env": {"A": "1"}}],
        [TargetConfig("t", "codex", env={"A": "1"})],
    ),
    "env_bad_type": (
        [{"id": "t", "backend": "codex", "env": []}],
        Raised(ValueError, "Target 't' env must be a TOML table"),
    ),
    "env_bad_key": (
        [{"id": "t", "backend": "codex", "env": {"": "x"}}],
        Raised(ValueError, "Environment key cannot be empty in Target 't' env"),
    ),
    "dup_ids": (
        [{"id": "a", "backend": "codex"}, {"id": "a", "backend": "pi"}],
        Raised(ValueError, "Target identifiers must be unique"),
    ),
    "args_before_isolated": (
        [{"id": "t", "backend": "codex", "args": "x", "isolated": "y"}],
        Raised(ValueError, "Target 't' args must be a list of strings"),
    ),
    "isolated_before_read_only": (
        [{"id": "t", "backend": "codex", "isolated": "y", "read_only": "z"}],
        Raised(ValueError, "Target 't' isolated must be true or false"),
    ),
    "read_only_before_text": (
        [{"id": "t", "backend": "codex", "read_only": "z", "model": 1}],
        Raised(ValueError, "Target 't' read_only must be true or false"),
    ),
    "text_before_backend_profile": (
        [{"id": "t", "backend": "codex", "model": 1, "backend_profile": 2}],
        Raised(ValueError, "Target 't' settings must be strings: ['model']"),
    ),
    "backend_profile_before_validate": (
        [{"id": "t", "backend": "codex", "backend_profile": 2, "args": ["--"]}],
        Raised(ValueError, "Target 't' backend_profile must be a string"),
    ),
    "validate_before_max_concurrency": (
        [{"id": "t", "backend": "codex", "args": ["--"], "max_concurrency": 0}],
        Raised(ValueError, "Target 't' args cannot contain the reserved '--' token"),
    ),
    "max_concurrency_before_context_window": (
        [{"id": "t", "backend": "codex", "max_concurrency": 0, "context_window": 0}],
        Raised(ValueError, "Target 't' max_concurrency must be a positive integer"),
    ),
    "context_window_before_retry": (
        [{"id": "t", "backend": "codex", "context_window": 0, "retry": []}],
        Raised(ValueError, "Target 't' context_window must be a positive integer"),
    ),
    "retry_before_env": (
        [{"id": "t", "backend": "codex", "retry": [], "env": []}],
        Raised(ValueError, "Target 't' has invalid retry settings"),
    ),
    "invalid_decl_before_removed": (
        [{"id": "", "backend": "codex", "profile": "x"}],
        Raised(ValueError, "Invalid target declaration"),
    ),
    "removed_before_args": (
        [{"id": "t", "backend": "codex", "profile": "x", "args": "y"}],
        Raised(ValueError, "targets[].profile has been removed; use targets[].backend_profile"),
    ),
    "unknown_before_args": (
        [{"id": "t", "backend": "codex", "zzz": 1, "args": "y"}],
        Raised(ValueError, "Unsupported target settings: ['zzz']"),
    ),
    "second_item_error_before_dup": (
        [{"id": "a", "backend": "codex"}, {"id": "a", "backend": "codex", "model": 1}],
        Raised(ValueError, "Target 'a' settings must be strings: ['model']"),
    ),
    "first_item_error_wins": (
        [{"id": "t", "backend": "codex", "model": 1}, {"id": "t", "backend": "nope"}],
        Raised(ValueError, "Target 't' settings must be strings: ['model']"),
    ),
    "second_item_bad": (
        [{"id": "a", "backend": "codex"}, "x"],
        Raised(ValueError, "Each target must be a TOML table"),
    ),
}


@pytest.mark.parametrize("case", list(_TARGETS_CASES))
def test_targets_characterization(case) -> None:
    raw, expected = _TARGETS_CASES[case]
    assert outcome(lambda: list(_targets(raw))) == plain(expected)


_LOGGING_CASES = {
    "none": (None, ("INFO", "refract.log", 10485760, 5)),
    "empty": ({}, ("INFO", "refract.log", 10485760, 5)),
    "not_dict": ([], Raised(ValueError, "[logging] must be a TOML table")),
    "str": ("x", Raised(ValueError, "[logging] must be a TOML table")),
    "removed_format": ({"format": "json"}, Raised(ValueError, "[logging].format has been removed")),
    "removed_console": ({"console": True}, Raised(ValueError, "[logging].console has been removed")),
    "removed_capture": (
        {"capture_warnings": 1},
        Raised(ValueError, "[logging].capture_warnings has been removed"),
    ),
    "unknown": ({"zzz": 1, "yyy": 2}, Raised(ValueError, "Unsupported logging settings: ['yyy', 'zzz']")),
    "removed_before_unknown": (
        {"zzz": 1, "format": 1},
        Raised(ValueError, "[logging].format has been removed"),
    ),
    "level_lower": ({"level": " debug "}, ("DEBUG", "refract.log", 10485760, 5)),
    "level_invalid": ({"level": "loud"}, Raised(ValueError, "Invalid logging level: 'LOUD'")),
    "level_int": ({"level": 5}, Raised(ValueError, "Invalid logging level: '5'")),
    "level_each": ({"level": "critical"}, ("CRITICAL", "refract.log", 10485760, 5)),
    "file_none": ({"file": None}, ("INFO", None, 10485760, 5)),
    "file_false": ({"file": False}, ("INFO", None, 10485760, 5)),
    "file_empty": ({"file": ""}, ("INFO", None, 10485760, 5)),
    "file_blank": ({"file": "  "}, ("INFO", None, 10485760, 5)),
    "file_none_str": ({"file": "None"}, ("INFO", None, 10485760, 5)),
    "file_off": ({"file": "OFF"}, ("INFO", None, 10485760, 5)),
    "file_int": ({"file": 5}, Raised(ValueError, "logging.file must be a path string or false")),
    "file_true": ({"file": True}, Raised(ValueError, "logging.file must be a path string or false")),
    "file_list": ({"file": ["x"]}, Raised(ValueError, "logging.file must be a path string or false")),
    "file_relative": ({"file": "logs/x.log"}, ("INFO", "logs/x.log", 10485760, 5)),
    "file_absolute": ({"file": "ABS"}, ("INFO", "<ABS>", 10485760, 5)),
    "file_default": ({}, ("INFO", "refract.log", 10485760, 5)),
    "level_before_file": ({"level": "bad", "file": 5}, Raised(ValueError, "Invalid logging level: 'BAD'")),
    "file_before_retention": (
        {"file": 5, "max_bytes": "x"},
        Raised(ValueError, "logging.file must be a path string or false"),
    ),
    "unknown_before_level": (
        {"zzz": 1, "level": "bad"},
        Raised(ValueError, "Unsupported logging settings: ['zzz']"),
    ),
    "max_bytes_str_num": ({"max_bytes": "5"}, ("INFO", "refract.log", 5, 5)),
    "max_bytes_float": ({"max_bytes": 1.9}, ("INFO", "refract.log", 1, 5)),
    "max_bytes_text": (
        {"max_bytes": "abc"},
        Raised(ValueError, "Logging retention settings must be integers"),
    ),
    "max_bytes_none": (
        {"max_bytes": None},
        Raised(ValueError, "Logging retention settings must be integers"),
    ),
    "max_bytes_bool": ({"max_bytes": True}, Raised(ValueError, "logging.max_bytes must be at least 1")),
    "max_bytes_zero": ({"max_bytes": 0}, Raised(ValueError, "logging.max_bytes must be at least 1")),
    "max_bytes_neg": ({"max_bytes": -5}, Raised(ValueError, "logging.max_bytes must be at least 1")),
    "backup_zero": ({"backup_count": 0}, ("INFO", "refract.log", 10485760, 0)),
    "backup_bool": ({"backup_count": True}, Raised(ValueError, "logging.backup_count must be at least 0")),
    "backup_neg": ({"backup_count": -1}, Raised(ValueError, "logging.backup_count must be at least 0")),
    "backup_text": ({"backup_count": "x"}, Raised(ValueError, "Logging retention settings must be integers")),
    "backup_none": (
        {"backup_count": None},
        Raised(ValueError, "Logging retention settings must be integers"),
    ),
    "backup_float": ({"backup_count": 2.7}, ("INFO", "refract.log", 10485760, 2)),
    "int_error_before_range": (
        {"max_bytes": 0, "backup_count": "x"},
        Raised(ValueError, "Logging retention settings must be integers"),
    ),
    "max_range_before_backup_range": (
        {"max_bytes": 0, "backup_count": -1},
        Raised(ValueError, "logging.max_bytes must be at least 1"),
    ),
    "max_bool_before_backup_bool": (
        {"max_bytes": True, "backup_count": True},
        Raised(ValueError, "logging.max_bytes must be at least 1"),
    ),
    "backup_bool_after_max_ok": (
        {"max_bytes": 7, "backup_count": False},
        Raised(ValueError, "logging.backup_count must be at least 0"),
    ),
    "all_set": (
        {"level": "WARNING", "file": "x.log", "max_bytes": 10, "backup_count": 2},
        ("WARNING", "x.log", 10, 2),
    ),
}


@pytest.mark.parametrize("case", list(_LOGGING_CASES))
def test_logging_config_characterization(tmp_path, case) -> None:
    raw, expected = _LOGGING_CASES[case]
    absolute = tmp_path / "abs.log"
    if isinstance(raw, dict) and raw.get("file") == "ABS":
        raw = {**raw, "file": str(absolute)}

    def call():
        config = _logging_config(raw, tmp_path)
        if config.file is None:
            shown = None
        elif config.file == absolute:
            shown = "<ABS>"
        else:
            shown = config.file.relative_to(tmp_path).as_posix()
        return (config.level, shown, config.max_bytes, config.backup_count)

    assert outcome(call) == plain(expected)


_PROJECT_BASE = """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
env = { KEEP = "1", OVER = "base" }

[[targets]]
id = "second"
backend = "pi"

[profiles.balanced]
implement = "primary"
review = "second"
consult = "primary"

[profiles.other]
extends = "balanced"
review = "primary"
"""

_PRIMARY = TargetConfig("primary", "codex", env={"KEEP": "1", "OVER": "base"})
_SECOND = TargetConfig("second", "pi")
_BASE_PROFILES = {
    "balanced": {
        "implement": TargetSelection(("primary",)),
        "review": TargetSelection(("second",)),
        "consult": TargetSelection(("primary",)),
    },
    "other": {
        "implement": TargetSelection(("primary",)),
        "review": TargetSelection(("primary",)),
        "consult": TargetSelection(("primary",)),
    },
}
_BASE_DECLARATIONS = {
    "balanced": ProfileDeclaration(
        None,
        {
            "implement": TargetSelection(("primary",)),
            "review": TargetSelection(("second",)),
            "consult": TargetSelection(("primary",)),
        },
    ),
    "other": ProfileDeclaration("balanced", {"review": TargetSelection(("primary",))}),
}


@dataclasses.dataclass(frozen=True)
class _Loaded:
    targets: list[TargetConfig]
    profiles: dict
    declarations: dict
    profiles_unchanged: bool
    declarations_unchanged: bool


_PROJECT_CASES = {
    "empty": (b"", _Loaded([_PRIMARY, _SECOND], _BASE_PROFILES, _BASE_DECLARATIONS, True, True)),
    "invalid_toml": (
        b"[[[x",
        Raised(TOMLDecodeError, "Invalid initial character for a key part (at line 1, column 3)"),
    ),
    "bad_utf8": (
        b"\xff\xfe",
        Raised(UnicodeDecodeError, "'utf-8' codec can't decode byte 0xff in position 0: invalid start byte"),
    ),
    "removed_section": (
        b"[project]\nx = 1\n",
        Raised(ValueError, "[project] has been removed; pass profile on submit"),
    ),
    "removed_langfuse": (b"[langfuse]\nx = 1\n", Raised(ValueError, "[langfuse] has been removed")),
    "unsupported_section": (
        b"[daemon]\nport = 1\n",
        Raised(ValueError, "Unsupported project config sections: ['daemon']"),
    ),
    "removed_section_before_unsupported": (
        b"[daemon]\nport = 1\n\n[project]\nx = 1\n",
        Raised(ValueError, "[project] has been removed; pass profile on submit"),
    ),
    "targets_not_list": (b"targets = 1\n", Raised(ValueError, "[targets] must be a TOML array of tables")),
    "targets_table": (
        b'[targets]\nid = "primary"\n',
        Raised(ValueError, "[targets] must be a TOML array of tables"),
    ),
    "item_not_dict": (b"targets = [1]\n", Raised(ValueError, "Each target must be a TOML table")),
    "unknown_target": (
        b'[[targets]]\nid = "new"\n',
        Raised(ValueError, "Project config cannot add targets: 'new'"),
    ),
    "missing_id": (b"[[targets]]\nenv = {}\n", Raised(ValueError, "Project config cannot add targets: ''")),
    "blank_id": (b'[[targets]]\nid = "  "\n', Raised(ValueError, "Project config cannot add targets: ''")),
    "int_id": (b"[[targets]]\nid = 3\n", Raised(ValueError, "Project config cannot add targets: ''")),
    "duplicate": (
        b'[[targets]]\nid = "primary"\n[[targets]]\nid = "primary"\n',
        Raised(ValueError, "Duplicate project target override: 'primary'"),
    ),
    "removed_key": (
        b'[[targets]]\nid = "primary"\nprofile = "x"\n',
        Raised(ValueError, "targets[].profile has been removed; use targets[].backend_profile"),
    ),
    "unsupported_field": (
        b'[[targets]]\nid = "primary"\nmodel = "x"\nbackend = "pi"\n',
        Raised(ValueError, "Unsupported project target settings: ['backend', 'model']"),
    ),
    "removed_before_unsupported": (
        b'[[targets]]\nid = "primary"\nmodel = "x"\nprofile = "x"\n',
        Raised(ValueError, "targets[].profile has been removed; use targets[].backend_profile"),
    ),
    "env_merge": (
        b'[[targets]]\nid = "primary"\nenv = { OVER = "proj", NEW = "2" }\n',
        _Loaded(
            [TargetConfig("primary", "codex", env={"KEEP": "1", "OVER": "proj", "NEW": "2"}), _SECOND],
            _BASE_PROFILES,
            _BASE_DECLARATIONS,
            True,
            True,
        ),
    ),
    "env_none": (
        b'[[targets]]\nid = "second"\n',
        _Loaded([_PRIMARY, _SECOND], _BASE_PROFILES, _BASE_DECLARATIONS, True, True),
    ),
    "env_override_second": (
        b'[[targets]]\nid = " second "\nenv = { Z = "z" }\n',
        _Loaded(
            [_PRIMARY, TargetConfig("second", "pi", env={"Z": "z"})],
            _BASE_PROFILES,
            _BASE_DECLARATIONS,
            True,
            True,
        ),
    ),
    "env_bad_type": (
        b'[[targets]]\nid = "primary"\nenv = 3\n',
        Raised(ValueError, "Target 'primary' env must be a TOML table"),
    ),
    "env_bad_key": (
        b'[[targets]]\nid = "primary"\nenv = { "A=B" = "x" }\n',
        Raised(ValueError, "Environment key cannot contain '=' in Target 'primary' env"),
    ),
    "env_template": (
        b'[[targets]]\nid = "primary"\nenv = { A = "${HOME}" }\n',
        Raised(ValueError, "${NAME} in targets[].env has been removed; write the literal value"),
    ),
    "empty_targets": (
        b"targets = []\n",
        _Loaded([_PRIMARY, _SECOND], _BASE_PROFILES, _BASE_DECLARATIONS, True, True),
    ),
    "profiles_only": (
        b'[profiles.extra]\nimplement = "primary"\n',
        _Loaded(
            [_PRIMARY, _SECOND],
            {
                "balanced": {
                    "implement": TargetSelection(("primary",)),
                    "review": TargetSelection(("second",)),
                    "consult": TargetSelection(("primary",)),
                },
                "other": {
                    "implement": TargetSelection(("primary",)),
                    "review": TargetSelection(("primary",)),
                    "consult": TargetSelection(("primary",)),
                },
                "extra": {"implement": TargetSelection(("primary",))},
            },
            {
                "balanced": ProfileDeclaration(
                    None,
                    {
                        "implement": TargetSelection(("primary",)),
                        "review": TargetSelection(("second",)),
                        "consult": TargetSelection(("primary",)),
                    },
                ),
                "other": ProfileDeclaration("balanced", {"review": TargetSelection(("primary",))}),
                "extra": ProfileDeclaration(None, {"implement": TargetSelection(("primary",))}),
            },
            False,
            False,
        ),
    ),
    "profiles_extends_base": (
        b'[profiles.extra]\nextends = "balanced"\nreview = "primary"\n',
        _Loaded(
            [_PRIMARY, _SECOND],
            {
                "balanced": {
                    "implement": TargetSelection(("primary",)),
                    "review": TargetSelection(("second",)),
                    "consult": TargetSelection(("primary",)),
                },
                "other": {
                    "implement": TargetSelection(("primary",)),
                    "review": TargetSelection(("primary",)),
                    "consult": TargetSelection(("primary",)),
                },
                "extra": {
                    "implement": TargetSelection(("primary",)),
                    "review": TargetSelection(("primary",)),
                    "consult": TargetSelection(("primary",)),
                },
            },
            {
                "balanced": ProfileDeclaration(
                    None,
                    {
                        "implement": TargetSelection(("primary",)),
                        "review": TargetSelection(("second",)),
                        "consult": TargetSelection(("primary",)),
                    },
                ),
                "other": ProfileDeclaration("balanced", {"review": TargetSelection(("primary",))}),
                "extra": ProfileDeclaration("balanced", {"review": TargetSelection(("primary",))}),
            },
            False,
            False,
        ),
    ),
    "profiles_extends_self": (
        b'[profiles.balanced]\nextends = "balanced"\nreview = "primary"\n',
        _Loaded(
            [_PRIMARY, _SECOND],
            {
                "balanced": {
                    "implement": TargetSelection(("primary",)),
                    "review": TargetSelection(("primary",)),
                    "consult": TargetSelection(("primary",)),
                },
                "other": {
                    "implement": TargetSelection(("primary",)),
                    "review": TargetSelection(("primary",)),
                    "consult": TargetSelection(("primary",)),
                },
            },
            {
                "balanced": ProfileDeclaration("balanced", {"review": TargetSelection(("primary",))}),
                "other": ProfileDeclaration("balanced", {"review": TargetSelection(("primary",))}),
            },
            False,
            False,
        ),
    ),
    "profiles_self_unknown": (
        b'[profiles.fresh]\nextends = "fresh"\n',
        Raised(ValueError, "Profile 'fresh' extends unknown parent 'fresh'"),
    ),
    "profiles_unknown_parent": (
        b'[profiles.extra]\nextends = "nope"\n',
        Raised(ValueError, "Profile 'extra' extends unknown parent 'nope'"),
    ),
    "profiles_cycle": (
        b'[profiles.a]\nextends = "b"\n[profiles.b]\nextends = "a"\n',
        Raised(ValueError, "Profile inheritance cycle: a -> b -> a"),
    ),
    "profiles_replace_existing": (
        b'[profiles.balanced]\nimplement = "second"\nreview = "second"\nconsult = "second"\n',
        _Loaded(
            [_PRIMARY, _SECOND],
            {
                "balanced": {
                    "implement": TargetSelection(("second",)),
                    "review": TargetSelection(("second",)),
                    "consult": TargetSelection(("second",)),
                },
                "other": {
                    "implement": TargetSelection(("primary",)),
                    "review": TargetSelection(("primary",)),
                    "consult": TargetSelection(("primary",)),
                },
            },
            {
                "balanced": ProfileDeclaration(
                    None,
                    {
                        "implement": TargetSelection(("second",)),
                        "review": TargetSelection(("second",)),
                        "consult": TargetSelection(("second",)),
                    },
                ),
                "other": ProfileDeclaration("balanced", {"review": TargetSelection(("primary",))}),
            },
            False,
            False,
        ),
    ),
    "profiles_bad": (b"profiles = 1\n", Raised(ValueError, "[profiles] must contain at least one profile")),
    "profiles_empty": (b"[profiles]\n", Raised(ValueError, "[profiles] must contain at least one profile")),
    "profiles_unknown_target": (
        b'[profiles.x]\nimplement = "ghost"\n',
        Raised(ValueError, "Profile 'x' workflow 'implement' has invalid targets: ['ghost']"),
    ),
    "profiles_unknown_workflow": (
        b'[profiles.x]\nbogus = "primary"\n',
        Raised(
            ValueError,
            "Unknown workflow 'bogus'; expected one of ('consult', 'implement', 'other', 'review')",
        ),
    ),
    "both": (
        b'[[targets]]\nid = "primary"\nenv = { N = "1" }\n[profiles.extra]\nextends = "balanced"\nconsult = "second"\n',
        _Loaded(
            [TargetConfig("primary", "codex", env={"KEEP": "1", "OVER": "base", "N": "1"}), _SECOND],
            {
                "balanced": {
                    "implement": TargetSelection(("primary",)),
                    "review": TargetSelection(("second",)),
                    "consult": TargetSelection(("primary",)),
                },
                "other": {
                    "implement": TargetSelection(("primary",)),
                    "review": TargetSelection(("primary",)),
                    "consult": TargetSelection(("primary",)),
                },
                "extra": {
                    "implement": TargetSelection(("primary",)),
                    "review": TargetSelection(("second",)),
                    "consult": TargetSelection(("second",)),
                },
            },
            {
                "balanced": ProfileDeclaration(
                    None,
                    {
                        "implement": TargetSelection(("primary",)),
                        "review": TargetSelection(("second",)),
                        "consult": TargetSelection(("primary",)),
                    },
                ),
                "other": ProfileDeclaration("balanced", {"review": TargetSelection(("primary",))}),
                "extra": ProfileDeclaration("balanced", {"consult": TargetSelection(("second",))}),
            },
            False,
            False,
        ),
    ),
    "target_error_before_profile_error": (
        b'[[targets]]\nid = "ghost"\n[profiles]\n',
        Raised(ValueError, "Project config cannot add targets: 'ghost'"),
    ),
    "unsupported_before_target_error": (
        b'[daemon]\nx = 1\n[[targets]]\nid = "ghost"\n',
        Raised(ValueError, "Unsupported project config sections: ['daemon']"),
    ),
}


@pytest.mark.parametrize("case", list(_PROJECT_CASES))
def test_load_project_config_values_characterization(tmp_path, case) -> None:
    data, expected = _PROJECT_CASES[case]
    path = tmp_path / "config.toml"
    path.write_text(_PROJECT_BASE, encoding="utf-8")
    base = load_config(path)

    def call():
        loaded = _load_project_config_values(tmp_path / "noproject", base, data)
        if loaded is base:
            return "BASE"
        return _Loaded(
            list(loaded.targets),
            loaded.profiles,
            loaded.profile_declarations,
            loaded.profiles == base.profiles,
            loaded.profile_declarations == base.profile_declarations,
        )

    assert outcome(call) == plain(expected)


def test_load_project_config_values_without_file_returns_base(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_PROJECT_BASE, encoding="utf-8")
    base = load_config(path)
    assert _load_project_config_values(tmp_path / "noproject", base, None) is base
