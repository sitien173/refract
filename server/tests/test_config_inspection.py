from __future__ import annotations

import hashlib

import pytest

from refract.config import load_config
from refract.config_inspection import REMOVED_KEYS, removed_key_message, sanitize_config_error, sha256_bytes


def _config() -> str:
    return '''[daemon]
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


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Unknown workflow 'SECRET_WORKFLOW'", "Unknown workflow"),
        (
            "Profile inheritance cycle: SECRET_PROFILE -> other -> SECRET_PROFILE",
            "Profile inheritance cycle",
        ),
        (
            "Profile 'SECRET_PROFILE' extends unknown parent 'SECRET_PARENT'",
            "Profile extends unknown parent",
        ),
    ],
)
def test_sanitizer_does_not_passthrough_configuration_identifiers(message, expected) -> None:
    assert sanitize_config_error(message) == expected
    assert "SECRET_" not in sanitize_config_error(message)


@pytest.mark.parametrize("key", sorted(REMOVED_KEYS))
def test_sanitizer_preserves_removed_config_message(key) -> None:
    message = removed_key_message(key)
    assert sanitize_config_error(message) == message


def test_sanitizer_preserves_only_parser_location_evidence() -> None:
    message = "Expected '=' after a key (at line 4, column 9) SECRET_VALUE"

    sanitized = sanitize_config_error(message)

    assert sanitized == "Invalid TOML syntax (at line 4, column 9)"
    assert "SECRET_VALUE" not in sanitized


def test_missing_source_has_empty_revision(tmp_path) -> None:
    with pytest.raises(ValueError) as raised:
        load_config(tmp_path / "missing.toml")

    assert getattr(raised.value, "revision", None) == ""


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Target 'SECRET_TARGET' has invalid retry settings",
            "Target has invalid retry settings",
        ),
        (
            "Unsupported target settings: ['SECRET_FIELD']",
            "Unsupported target settings",
        ),
    ],
)
def test_sanitizer_does_not_expose_retry_settings(message, expected) -> None:
    sanitized = sanitize_config_error(message)
    assert sanitized == expected
    assert "SECRET_" not in sanitized



@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Target 'SECRET_TARGET' env must be a TOML table",
            "Target env must be a TOML table",
        ),
        (
            "Environment values must be strings in Target 'SECRET_TARGET' env",
            "Environment values must be strings",
        ),
        (
            "Environment values cannot contain NUL bytes in Target 'SECRET_TARGET' env",
            "Environment values cannot contain NUL bytes",
        ),
        (
            "Environment key cannot be empty in Target 'SECRET_TARGET' env",
            "Environment key cannot be empty",
        ),
        (
            "Environment key cannot contain '=' in Target 'SECRET_TARGET' env",
            "Environment key cannot contain '='",
        ),
        (
            "Environment key cannot contain NUL bytes in Target 'SECRET_TARGET' env",
            "Environment key cannot contain NUL bytes",
        ),
        (
            "Environment keys cannot use protected prefix REFRACT_ASK_ in Target 'SECRET_TARGET' env",
            "Environment keys cannot use protected prefix",
        ),
        (
            "Unsupported project target settings: ['SECRET_FIELD']",
            "Unsupported project target settings",
        ),
        (
            "Project config cannot add targets: 'SECRET_TARGET'",
            "Project config cannot add targets",
        ),
        (
            "Duplicate project target override: 'SECRET_TARGET'",
            "Duplicate project target override",
        ),
        (
            "Unknown target: 'SECRET_TARGET'",
            "Unknown target",
        ),
    ],
)
def test_sanitizer_does_not_expose_environment_details(message, expected) -> None:
    sanitized = sanitize_config_error(message)
    assert sanitized == expected
    assert "SECRET_" not in sanitized
