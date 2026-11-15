from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from refract.config import load_config, sanitize_config_error, sha256_bytes
from refract.config.inspection import ConfigurationLoadError, make_issue


def _config() -> str:
    return '''schema_version = 1

[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
'''


def test_revision_hashes_exact_source_bytes(tmp_path) -> None:
    path = tmp_path / "config.toml"
    raw = _config().replace("\n", "\r\n").encode("utf-8")
    path.write_bytes(raw)

    catalog = load_config(path)

    assert catalog.config_revision == hashlib.sha256(raw).hexdigest()
    assert sha256_bytes(raw) == catalog.config_revision


def test_invalid_utf8_uses_configuration_error_contract(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_bytes(b"[daemon]\n\xff")

    with pytest.raises(ValueError, match="Invalid config file"):
        load_config(path)


def _sanitized(code, loc, scope="global") -> str:
    issue = make_issue(code, loc, scope)
    return sanitize_config_error(ConfigurationLoadError((issue,), path=Path("config.toml")))


def test_sanitizer_ignores_message_text_of_plain_errors() -> None:
    assert sanitize_config_error("Unknown target: 'SECRET_TARGET'") == "Invalid configuration"


@pytest.mark.parametrize(
    ("code", "loc", "expected"),
    [
        ("extra_forbidden", ("profiles", "SECRET_PROFILE", "SECRET_WORKFLOW"), "Unknown workflow"),
        ("profile_cycle", ("profiles", "SECRET_PROFILE"), "Profile inheritance cycle"),
        ("unknown_parent", ("profiles", "SECRET_PROFILE", "extends"), "Profile extends unknown parent"),
    ],
)
def test_sanitizer_does_not_passthrough_configuration_identifiers(code, loc, expected) -> None:
    assert _sanitized(code, loc) == expected
    assert "SECRET_" not in _sanitized(code, loc)


def test_sanitizer_preserves_only_parser_location_evidence(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[daemon]\nSECRET_VALUE\n', encoding="utf-8")

    with pytest.raises(ConfigurationLoadError) as raised:
        load_config(path)

    sanitized = sanitize_config_error(raised.value)
    assert sanitized.startswith("Invalid TOML syntax (at line 2, column ")
    assert "SECRET_VALUE" not in sanitized
    assert raised.value.issues[0].code == "toml_syntax"



def test_missing_source_has_empty_revision(tmp_path) -> None:
    with pytest.raises(ValueError) as raised:
        load_config(tmp_path / "missing.toml")

    assert getattr(raised.value, "revision", None) == ""



@pytest.mark.parametrize(
    ("code", "loc", "expected"),
    [
        ("extra_forbidden", ("targets", 0, "retry", "SECRET_FIELD"), "Target has invalid retry settings"),
        ("extra_forbidden", ("targets", 0, "SECRET_FIELD"), "Unsupported target settings"),
    ],
)
def test_sanitizer_does_not_expose_retry_settings(code, loc, expected) -> None:
    sanitized = _sanitized(code, loc)
    assert sanitized == expected
    assert "SECRET_" not in sanitized


@pytest.mark.parametrize(
    ("code", "loc", "scope", "expected"),
    [
        ("dict_type", ("targets", 0, "env"), "global", "Target env must be a TOML table"),
        ("string_type", ("targets", 0, "env", "SECRET_TARGET"), "global", "Environment values must be strings"),
        ("env_value_nul", ("targets", 0, "env", "SECRET_TARGET"), "global", "Environment values cannot contain NUL bytes"),
        ("env_key_empty", ("targets", 0, "env"), "global", "Environment key cannot be empty"),
        ("env_key_equals", ("targets", 0, "env"), "global", "Environment key cannot contain '='"),
        ("env_key_nul", ("targets", 0, "env"), "global", "Environment key cannot contain NUL bytes"),
        ("env_key_reserved", ("targets", 0, "env"), "global", "Environment keys cannot use protected prefix"),
        ("extra_forbidden", ("targets", 0, "SECRET_FIELD"), "project", "Unsupported project target settings"),
        ("project_unknown_target", ("targets", 0), "project", "Project config cannot add targets"),
        ("project_duplicate_target", ("targets", 0), "project", "Duplicate project target override"),
        ("unknown_target", ("profiles", "SECRET_PROFILE", "implement", "targets", 0), "global", "Profile workflow has invalid targets"),
    ],
)
def test_sanitizer_does_not_expose_environment_details(code, loc, scope, expected) -> None:
    sanitized = _sanitized(code, loc, scope)
    assert sanitized == expected
    assert "SECRET_" not in sanitized


def test_missing_schema_version_message_says_how_to_fix(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(_config().replace("schema_version = 1\n", ""), encoding="utf-8")

    with pytest.raises(ConfigurationLoadError) as raised:
        load_config(path)

    issue = raised.value.issues[0]
    assert (issue.code, issue.loc) == ("missing", ("schema_version",))
    assert "schema_version = 1" in issue.hint
