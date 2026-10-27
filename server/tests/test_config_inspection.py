from __future__ import annotations

import hashlib

import pytest

from refract.config import load_config
from refract.config_inspection import sanitize_config_error, sha256_bytes


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
            "Retry policy 'SECRET_POLICY' has unsupported settings: ['SECRET_FIELD']",
            "Retry policy has unsupported settings",
        ),
        (
            "Retry policy 'SECRET_POLICY' retryAttempt must be a non-negative integer",
            "Retry policy retryAttempt must be a non-negative integer",
        ),
        (
            "Retry policy 'SECRET_POLICY' errorCodes must be a list of non-empty strings",
            "Retry policy errorCodes must be a list of non-empty strings",
        ),
        (
            "Retry policy 'SECRET_POLICY' errorPatterns must be a list of non-empty strings",
            "Retry policy errorPatterns must be a list of non-empty strings",
        ),
        (
            "Target 'SECRET_TARGET' references unknown retry policy: 'SECRET_POLICY'",
            "Target references unknown retry policy",
        ),
        (
            "Target 'SECRET_TARGET' cannot declare inline retry settings",
            "Target cannot declare inline retry settings",
        ),
        (
            "Target 'SECRET_TARGET' retryPolicy must be a non-empty string",
            "Target retryPolicy must be a non-empty string",
        ),
        (
            "Target 'SECRET_TARGET' has unsupported settings: ['retry_policy']",
            "Target has unsupported settings",
        ),
    ],
)
def test_sanitizer_does_not_expose_retry_policy_or_error_patterns(message, expected) -> None:
    sanitized = sanitize_config_error(message)
    assert sanitized == expected
    assert "SECRET_" not in sanitized



@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Target 'SECRET_TARGET' references unknown environment set: 'SECRET_GROUP'",
            "Target references unknown environment set",
        ),
        (
            "Target 'SECRET_TARGET' envs must be a TOML table",
            "Target envs must be a TOML table",
        ),
        (
            "Target 'SECRET_TARGET' envs_vars must be a list of strings",
            "Target envs_vars must be a list of strings",
        ),
        (
            "Environment set 'SECRET_GROUP' must be a TOML table",
            "Environment set must be a TOML table",
        ),
        (
            "Environment values must be strings in Environment set 'SECRET_GROUP'",
            "Environment values must be strings",
        ),
        (
            "Environment values cannot contain NUL bytes in Target 'SECRET_TARGET' envs",
            "Environment values cannot contain NUL bytes",
        ),
        (
            "Environment key cannot be empty in Target 'SECRET_TARGET' envs",
            "Environment key cannot be empty",
        ),
        (
            "Environment key cannot contain '=' in Environment set 'SECRET_GROUP'",
            "Environment key cannot contain '='",
        ),
        (
            "Environment key cannot contain NUL bytes in Environment set 'SECRET_GROUP'",
            "Environment key cannot contain NUL bytes",
        ),
        (
            "Environment keys cannot use protected prefix REFRACT_ASK_ in Environment set 'SECRET_GROUP'",
            "Environment keys cannot use protected prefix",
        ),
        (
            "Project target override 'SECRET_TARGET' has unsupported settings: ['SECRET_FIELD']",
            "Project target override has unsupported settings",
        ),
        (
            "Unknown project target override: 'SECRET_TARGET'",
            "Unknown project target override",
        ),
        (
            "Duplicate project target override: 'SECRET_TARGET'",
            "Duplicate project target override",
        ),
        (
            "Missing environment reference: SECRET_VAR",
            "Missing environment reference",
        ),
        (
            "Environment reference cycle detected: SECRET_VAR",
            "Environment reference cycle detected",
        ),
        (
            "Protected environment reference: SECRET_REF",
            "Protected environment reference",
        ),
        (
            "Unterminated environment reference",
            "Unterminated environment reference",
        ),
        (
            "Empty environment reference",
            "Empty environment reference",
        ),
        (
            "Malformed environment reference: SECRET_NAME",
            "Malformed environment reference",
        ),
        (
            "Unknown target: 'SECRET_TARGET'",
            "Unknown target",
        ),
    ],
)
def test_sanitizer_does_not_expose_environment_details_or_templates(message, expected) -> None:
    sanitized = sanitize_config_error(message)
    assert sanitized == expected
    assert "SECRET_" not in sanitized
