from __future__ import annotations

import dataclasses
import re

import pytest

from refract.config import (
    DaemonConfig,
    LoggingConfig,
    RetryPolicy,
    TargetConfig,
    load_config,
    load_project_config,
    resolve_target_environment,
)
from refract.planning import resolve_execution_plan
from refract.workflows import get_workflow


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
    with pytest.raises(ValueError) as caught:
        if layer == "global":
            _load_global(tmp_path, text)
        else:
            _load_project(tmp_path, _load_global(tmp_path, _global()), text)
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
    with pytest.raises(ValueError, match=r"Target has invalid retry settings"):
        _load_global(tmp_path, _global(target_extra=f"retry = {retry}"))


def test_unknown_target_setting_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match=r"Unsupported target settings"):
        _load_global(tmp_path, _global(target_extra='capabilities = ["code"]'))


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
