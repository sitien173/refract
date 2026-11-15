from __future__ import annotations

import dataclasses
import re

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
)
from refract.runner.planning import resolve_execution_plan
from refract.workflows import get_workflow


_BASE = """{schema}[daemon]
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


def _global(
    target_extra: str = "",
    profile_extra: str = "",
    sections: str = "",
    schema: str = "schema_version = 1\n\n",
) -> str:
    return _BASE.format(
        target_extra=target_extra, profile_extra=profile_extra, sections=sections, schema=schema
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

# (removed key, expected sanitized error, layer, global text or project overlay text)
_REMOVED = [
    (f"[{_LF}]", "Unsupported config sections", "global", _global(sections=f"[{_LF}]\nenabled = true\n")),
    (f"[daemon].{_HIST}", "Unsupported daemon settings", "global", _global().replace(
        'default_profile = "balanced"', f'default_profile = "balanced"\n{_HIST} = 8')),
    (f"[daemon].{_HIST_BYTES}", "Unsupported daemon settings", "global", _global().replace(
        'default_profile = "balanced"', f'default_profile = "balanced"\n{_HIST_BYTES} = 8')),
    (f"[{_POLICIES}]", "Unsupported config sections", "global",
     _global(sections=f"[{_POLICIES}.fast]\nretry_attempt = 1\n")),
    ("[envs]", "Unsupported config sections", "global", _global(sections="[envs.shared]\nA = \"1\"\n")),
    ("[telemetry]", "Unsupported config sections", "global", _global(sections="[telemetry]\nenabled = true\n")),
    (f"targets[].{_POLICY}", "Unsupported target settings", "global",
     _global(target_extra=f'{_POLICY} = "fast"')),
    (f"targets[].{_ENV_SETS}", "Unsupported target settings", "global",
     _global(target_extra=f'{_ENV_SETS} = ["shared"]')),
    ("targets[].envs", "Unsupported target settings", "global", _global(target_extra='envs = { A = "1" }')),
    (f"targets[].{_WINDOW}", "Unsupported target settings", "global",
     _global(target_extra=f"{_WINDOW} = 1000")),
    ("targets[].profile", "Unsupported target settings", "global",
     _global(target_extra='profile = "work"')),
    ("profiles workflow max_attempts", "Profile workflow has unsupported settings", "global",
     _global().replace('implement = "primary"',
                       'implement = { targets = ["primary"], max_attempts = 2 }')),
    ("${NAME} in targets[].env", "Environment values cannot contain '${'; write the literal value", "global",
     _global(target_extra='env = { A = "${HOME}" }')),
    ("[logging].format", "Unsupported logging settings", "global", _global(sections='[logging]\nformat = "json"\n')),
    ("[logging].console", "Unsupported logging settings", "global", _global(sections="[logging]\nconsole = true\n")),
    ("[logging].capture_warnings", "Unsupported logging settings", "global",
     _global(sections="[logging]\ncapture_warnings = true\n")),
    ("[project]", "Unsupported project config sections", "project", '[project]\ndefault_profile = "balanced"\n'),
    ("[envs]", "Unsupported project config sections", "project", '[envs.shared]\nA = "1"\n'),
    (f"targets[].{_ENV_SETS}", "Unsupported project target settings", "project",
     f'[[targets]]\nid = "primary"\n{_ENV_SETS} = ["shared"]\n'),
    ("targets[].envs", "Unsupported project target settings", "project",
     '[[targets]]\nid = "primary"\nenvs = { A = "1" }\n'),
    ("${NAME} in targets[].env", "Environment values cannot contain '${'; write the literal value", "project",
     '[[targets]]\nid = "primary"\nenv = { A = "${HOME}" }\n'),
]


@pytest.mark.parametrize(
    ("key", "expected", "layer", "text"),
    _REMOVED,
    ids=[f"{layer}:{key}" for key, _, layer, _ in _REMOVED],
)
def test_removed_key_fails_load_with_generic_error(tmp_path, key, expected, layer, text) -> None:
    base = _load_global(tmp_path, _global()) if layer != "global" else None
    with pytest.raises(ValueError) as caught:
        if layer == "global":
            _load_global(tmp_path, text)
        else:
            _load_project(tmp_path, base, text)
    assert re.search(re.escape(expected) + r"$", str(caught.value)), str(caught.value)


def test_target_config_has_exact_v3_fields() -> None:
    assert [field.name for field in dataclasses.fields(TargetConfig)] == [
        "id", "backend", "model", "backend_profile", "reasoning", "system_prompt",
        "args", "max_concurrency", "retry", "env",
    ]
    assert [field.name for field in dataclasses.fields(RetryPolicy)] == [
        "attempts", "codes", "patterns",
    ]
    assert [field.name for field in dataclasses.fields(LoggingConfig)] == [
        "level", "file", "max_bytes", "backup_count",
    ]
    names = {field.name for field in dataclasses.fields(DaemonConfig)}
    assert not names & {"retry_policies", "envs", "project_profile_declarations"}


def test_inline_retry_and_literal_env_load(tmp_path) -> None:
    catalog = _load_global(tmp_path, _global(target_extra="""retry = { attempts = 2, codes = ["service_error"], patterns = ["overloaded"] }
env = { API_URL = "https://example.invalid", MODE = "$literal" }"""))

    target = catalog.targets[0]
    assert target.retry == RetryPolicy(attempts=2, codes=("service_error",), patterns=("overloaded",))
    assert target.env == {"API_URL": "https://example.invalid", "MODE": "$literal"}
    assert resolve_target_environment(catalog, target) == target.env


def test_retry_defaults_to_no_retry(tmp_path) -> None:
    target = _load_global(tmp_path, _global()).targets[0]
    assert target.retry == RetryPolicy(attempts=0, codes=(), patterns=())
    assert target.env == {}


def test_empty_inline_retry_table_means_no_retry(tmp_path) -> None:
    target = _load_global(tmp_path, _global(target_extra="retry = {}")).targets[0]
    assert target.retry == RetryPolicy(attempts=0, codes=(), patterns=())


@pytest.mark.parametrize("codes", ["[123]", '[""]', '["no_agent_messages"]'])
def test_non_code_retry_entries_are_unknown_codes(tmp_path, codes) -> None:
    with pytest.raises(ValueError, match=r"Unknown retry code"):
        _load_global(tmp_path, _global(target_extra=f"retry = {{ codes = {codes} }}"))


@pytest.mark.parametrize(
    "retry",
    [
        "{ attempts = -1 }",
        "{ attempts = true }",
        "{ attempts = false }",
        "{ attempts = 1.5 }",
        '{ attempts = "2" }',
        '{ codes = "service_error" }',
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


def test_global_config_rejects_pricing_section(tmp_path) -> None:
    with pytest.raises(ValueError, match=r"Unsupported config sections"):
        _load_global(
            tmp_path,
            _global() + '\n[pricing]\ncurrency = "EUR"\n[pricing.models.m]\ninput = "bad"\n',
        )


def test_project_overlay_rejects_global_pricing(tmp_path) -> None:
    base = _load_global(tmp_path, _global())
    with pytest.raises(ValueError, match=r"Unsupported project config sections"):
        _load_project(tmp_path, base, "[pricing]\ncurrency = 'USD'\n")


def test_example_v3_config_loads_and_covers_every_key(tmp_path, monkeypatch) -> None:
    import tomllib
    from pathlib import Path

    from refract.config.models import TargetFile

    monkeypatch.setenv("REFRACT_HOME", str(tmp_path))
    path = Path(__file__).resolve().parents[1] / "config.v3.toml"
    config = load_config(path)
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    assert {target.backend for target in config.targets} == {"agy", "codex", "pi", "claude"}
    assert set().union(*(set(item) for item in raw["targets"])) == set(TargetFile.model_fields)
    assert set(raw["daemon"]) == {
        "host", "port", "max_jobs", "default_profile", "breaker_failure_threshold",
        "breaker_base_cooldown_s", "breaker_max_cooldown_s", "ask_timeout_s",
    }
    assert set(raw["logging"]) == {"level", "file", "max_bytes", "backup_count"}
    assert set(raw["notifications"]) == {"enabled"}
    assert "telemetry" not in raw
    assert not hasattr(config, "telemetry")
    assert not hasattr(config, "ignored_keys")
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


def test_load_project_config_without_file_returns_base(tmp_path) -> None:
    base = _load_global(tmp_path, _global())
    assert load_project_config(tmp_path / "noproject", base) is base


def test_load_config_rejects_env_expansion_with_direct_message(tmp_path) -> None:
    text = _global(target_extra='env = { TOKEN = "${HOME}" }')
    with pytest.raises(ValueError, match=r"\$\{"):
        _load_global(tmp_path, text)


# Pydantic loader contract: schema_version, unknown keys, and error code and loc.

def _issues(caught) -> list[tuple[str, tuple[str | int, ...]]]:
    return [(issue.code, issue.loc) for issue in caught.value.issues]


def test_schema_version_loads(tmp_path) -> None:
    assert _load_global(tmp_path, _global()).default_profile == "balanced"


def test_missing_schema_version_reports_code_loc_and_fix(tmp_path) -> None:
    with pytest.raises(ValueError) as caught:
        _load_global(tmp_path, _global(schema=""))
    assert _issues(caught) == [("missing", ("schema_version",))]
    assert "schema_version = 1" in caught.value.issues[0].hint


def test_wrong_schema_version_reports_literal_error(tmp_path) -> None:
    with pytest.raises(ValueError) as caught:
        _load_global(tmp_path, _global(schema="schema_version = 2\n\n"))
    assert _issues(caught) == [("literal_error", ("schema_version",))]


def test_unknown_top_level_key_reports_extra_forbidden_at_key(tmp_path) -> None:
    with pytest.raises(ValueError) as caught:
        _load_global(tmp_path, _global(sections='[unknown_section]\nfoo = "bar"\n'))
    assert _issues(caught) == [("extra_forbidden", ("unknown_section",))]


def test_unknown_retry_code_reports_exact_loc(tmp_path) -> None:
    text = _global(target_extra='retry = { attempts = 1, codes = ["service_error", "nope"] }')
    with pytest.raises(ValueError) as caught:
        _load_global(tmp_path, text)
    assert _issues(caught) == [("literal_error", ("targets", 0, "retry", "codes", 1))]


def test_every_documented_retry_code_loads(tmp_path) -> None:
    codes = [
        "timeout", "service_error", "execution_error", "stdin_failed", "no_output",
        "context_overflow", "bad_cwd", "invalid_prompt", "invalid_args",
        "unsupported_option", "invalid_model", "missing_cli", "spawn_failed", "auth",
    ]
    text = _global(target_extra=f"retry = {{ attempts = 1, codes = {codes!r} }}".replace("'", '"'))
    assert _load_global(tmp_path, text).targets[0].retry.codes == tuple(codes)


def test_project_overlay_error_carries_code_and_loc(tmp_path) -> None:
    base = _load_global(tmp_path, _global())
    with pytest.raises(ValueError) as caught:
        _load_project(tmp_path, base, "[project]\nx = 1\n")
    assert _issues(caught) == [("extra_forbidden", ("project",))]


def test_toml_syntax_error_carries_code_and_empty_loc(tmp_path) -> None:
    with pytest.raises(ValueError) as caught:
        _load_global(tmp_path, "schema_version = \n")
    assert _issues(caught) == [("toml_syntax", ())]


@pytest.mark.parametrize("sentinel", ["false", "", "none", "None", "OFF", "-", "  "])
def test_logging_file_sentinels_disable_file_logging(tmp_path, sentinel) -> None:
    config = _load_global(tmp_path, _global(sections=f'[logging]\nfile = "{sentinel}"'))
    assert config.logging.file is None


def test_logging_level_is_trimmed_and_uppercased(tmp_path) -> None:
    config = _load_global(tmp_path, _global(sections='[logging]\nlevel = " debug "'))
    assert config.logging.level == "DEBUG"


@pytest.mark.parametrize("setting", ['max_bytes = "5"', "max_bytes = 1.9", "backup_count = 2.7", "max_bytes = true"])
def test_logging_retention_rejects_coerced_values(tmp_path, setting) -> None:
    with pytest.raises(ValueError):
        _load_global(tmp_path, _global(sections=f"[logging]\n{setting}"))


# Schema version type strictness, both loaders.

@pytest.mark.parametrize("value", ["true", "1.0", '"1"', "2"])
def test_global_schema_version_requires_integer_one(tmp_path, value) -> None:
    with pytest.raises(ValueError) as caught:
        _load_global(tmp_path, _global(schema=f"schema_version = {value}\n\n"))
    assert _issues(caught) == [("literal_error", ("schema_version",))]
    assert "schema_version = 1" in caught.value.issues[0].hint


@pytest.mark.parametrize("value", ["true", "1.0", '"1"', "2"])
def test_project_schema_version_requires_integer_one(tmp_path, value) -> None:
    base = _load_global(tmp_path, _global())
    with pytest.raises(ValueError) as caught:
        _load_project(tmp_path, base, f"schema_version = {value}\n")
    assert _issues(caught) == [("literal_error", ("schema_version",))]
    assert "schema_version = 1" in caught.value.issues[0].hint


def test_project_schema_version_one_loads(tmp_path) -> None:
    base = _load_global(tmp_path, _global())
    assert _load_project(tmp_path, base, "schema_version = 1\n") == base


# Target identity and type validation through the public loader.

_TARGET = 'id = "primary"\nbackend = "codex"'


def _with_target(tmp_path, target_body: str, extra: str = ""):
    text = _global().replace(_TARGET, target_body) + extra
    return _load_global(tmp_path, text)


def test_duplicate_target_ids_are_rejected(tmp_path) -> None:
    extra = '\n[[targets]]\nid = "primary"\nbackend = "pi"\n'
    with pytest.raises(ValueError) as caught:
        _load_global(tmp_path, _global(sections=extra))
    assert _issues(caught) == [("duplicate_target", ("targets", 1))]
    assert caught.value.payload()["code"] == "config_invalid"


@pytest.mark.parametrize(
    ("body", "code", "loc"),
    [
        ('backend = "codex"', "missing", ("targets", 0, "id")),
        ('id = ""\nbackend = "codex"', "empty_string", ("targets", 0, "id")),
        ('id = "  "\nbackend = "codex"', "empty_string", ("targets", 0, "id")),
        ('id = "primary"', "missing", ("targets", 0, "backend")),
        ('id = "primary"\nbackend = "nope"', "literal_error", ("targets", 0, "backend")),
        ('id = "primary"\nbackend = 3', "literal_error", ("targets", 0, "backend")),
        (f'{_TARGET}\nargs = "--x"', "list_type", ("targets", 0, "args")),
        (f"{_TARGET}\nargs = 5", "list_type", ("targets", 0, "args")),
        (f"{_TARGET}\nargs = [1]", "string_type", ("targets", 0, "args", 0)),
        (f'{_TARGET}\nargs = ["a", false]', "string_type", ("targets", 0, "args", 1)),
        (f"{_TARGET}\nmodel = 1", "string_type", ("targets", 0, "model")),
        (f"{_TARGET}\nreasoning = true", "string_type", ("targets", 0, "reasoning")),
        (f"{_TARGET}\nsystem_prompt = 2", "string_type", ("targets", 0, "system_prompt")),
        (f"{_TARGET}\nbackend_profile = 1.5", "string_type", ("targets", 0, "backend_profile")),
    ],
)
def test_target_identity_and_type_errors_carry_code_and_loc(tmp_path, body, code, loc) -> None:
    with pytest.raises(ValueError) as caught:
        _with_target(tmp_path, body)
    assert _issues(caught) == [(code, loc)]
    assert caught.value.payload()["code"] == "config_invalid"


# Logging validation through the public loader.

def _logging(tmp_path, body: str):
    return _load_global(tmp_path, _global(sections=f"[logging]\n{body}"))


def test_logging_file_false_disables_log_file(tmp_path) -> None:
    assert _logging(tmp_path, "file = false").logging.file is None


@pytest.mark.parametrize("value", ["true", "5", "['a']"])
def test_logging_file_rejects_non_string_paths(tmp_path, value) -> None:
    with pytest.raises(ValueError) as caught:
        _logging(tmp_path, f"file = {value}")
    assert _issues(caught) == [("log_file_type", ("logging", "file"))]


def test_logging_file_defaults_and_resolves_relative_to_home(tmp_path) -> None:
    config = _logging(tmp_path, 'file = "logs/app.log"')
    assert config.logging.file == config.home / "logs" / "app.log"
    assert _load_global(tmp_path, _global()).logging.file is not None


def test_logging_file_keeps_absolute_path(tmp_path) -> None:
    target = tmp_path / "abs" / "app.log"
    assert _logging(tmp_path, f"file = '{target}'").logging.file == target


@pytest.mark.parametrize("level", ['"LOUD"', '""', "5", "true"])
def test_logging_level_rejects_invalid_and_non_string(tmp_path, level) -> None:
    with pytest.raises(ValueError) as caught:
        _logging(tmp_path, f"level = {level}")
    assert [loc for _, loc in _issues(caught)] == [("logging", "level")]


@pytest.mark.parametrize(
    ("setting", "loc"),
    [("max_bytes = 0", ("logging", "max_bytes")), ("backup_count = -1", ("logging", "backup_count"))],
)
def test_logging_retention_rejects_out_of_range(tmp_path, setting, loc) -> None:
    with pytest.raises(ValueError) as caught:
        _logging(tmp_path, setting)
    assert _issues(caught) == [("greater_than_equal", loc)]


def test_logging_backup_count_zero_is_accepted(tmp_path) -> None:
    assert _logging(tmp_path, "backup_count = 0").logging.backup_count == 0


# Project overlay edge cases.

def test_empty_project_file_preserves_base(tmp_path) -> None:
    base = _load_global(tmp_path, _global())
    assert _load_project(tmp_path, base, "") == base


def test_project_empty_targets_preserves_base(tmp_path) -> None:
    base = _load_global(tmp_path, _global())
    assert _load_project(tmp_path, base, "targets = []\n") == base


@pytest.mark.parametrize(
    ("text", "code", "loc"),
    [
        ('targets = "primary"\n', "list_type", ("targets",)),
        ("targets = 5\n", "list_type", ("targets",)),
        ("targets = [1]\n", "model_type", ("targets", 0)),
        ('[targets]\nid = "primary"\n', "list_type", ("targets",)),
    ],
)
def test_malformed_project_target_container_is_rejected(tmp_path, text, code, loc) -> None:
    base = _load_global(tmp_path, _global())
    with pytest.raises(ValueError) as caught:
        _load_project(tmp_path, base, text)
    assert _issues(caught) == [(code, loc)]
