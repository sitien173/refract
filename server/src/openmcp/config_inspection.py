"""Safe metadata helpers for global configuration loading."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MAX_CONFIG_ERROR_LENGTH = 512


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    """Return the full lowercase SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


# Descriptive alias for callers inspecting a source without loading it.
hash_config_bytes = sha256_bytes


def modification_time(path: Path) -> str:
    """Return an ISO timestamp for display; it is not revision identity."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        return ""


def bound_error(error: object) -> str:
    """Keep health evidence useful without retaining tracebacks or payloads."""
    value = str(error).replace("\x00", "")
    if len(value) > MAX_CONFIG_ERROR_LENGTH:
        return value[:MAX_CONFIG_ERROR_LENGTH - 3] + "..."
    return value


def _safe_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.:/-]+", value))


def sanitize_config_error(error: object) -> str:
    """Keep structural diagnostics while removing configuration values.

    Validation errors are written by many small validators. Keeping an
    allow-list here makes a future validator unable to accidentally publish a
    prompt, argument, provider secret, or arbitrary TOML value.
    """
    raw_text = str(error).replace("\x00", "")
    text = bound_error(raw_text)
    location = re.search(r"\(at line (\d+), column (\d+)\)", raw_text)
    if location:
        return (
            "Invalid TOML syntax "
            f"(at line {location.group(1)}, column {location.group(2)})"
        )
    if text.startswith("Missing config file:") or text.startswith(
        "Unable to read config file:"
    ):
        return text
    if text.startswith("Invalid config file:") and "invalid UTF-8" in text:
        return text
    if text.startswith("Unsupported config sections"):
        return "Unsupported config sections"
    if text.startswith("Unsupported daemon settings"):
        return "Unsupported daemon settings"
    if text.startswith("Unsupported project config sections"):
        return "Unsupported project config sections"
    if text.startswith("Unsupported project settings"):
        return "Unsupported project settings"
    missing = re.fullmatch(r"Missing required \[(targets|profiles)\] section", text)
    if missing:
        return text
    if text in {
        "[targets] must contain at least one target",
        "[targets] must be a TOML array of tables",
        "[profiles] must contain at least one profile",
        "[logging] must be a TOML table",
        "[project] must be a TOML table",
        "[daemon].default_profile must be set",
        "[daemon].host must be a non-empty string",
        "[daemon].port must not exceed 65535",
        "Logging format must be 'text' or 'json'",
        "Logging retention settings must be integers",
        "Target identifiers must be unique",
        "Invalid target declaration",
    }:
        return text
    if text.startswith("Unknown [daemon].default_profile"):
        return "Unknown [daemon].default_profile"
    if text.startswith("Unknown project profile"):
        return "Unknown project profile"
    workflow = re.fullmatch(r"Unknown workflow '([^']+)'.*", raw_text)
    if workflow and _safe_identifier(workflow.group(1)):
        return f"Unknown workflow '{workflow.group(1)}'"
    cycle = raw_text.removeprefix("Profile inheritance cycle: ")
    if cycle != raw_text and all(
        _safe_identifier(item) for item in cycle.split(" -> ")
    ):
        return f"Profile inheritance cycle: {cycle}"
    parent = re.fullmatch(
        r"Profile '([^']+)' extends unknown parent '([^']+)'", raw_text
    )
    if parent and all(_safe_identifier(item) for item in parent.groups()):
        return raw_text
    if text.startswith("Profile "):
        if "declare extends or a workflow" in text:
            return "Profile declaration must declare extends or a workflow"
        if "non-empty string" in text:
            return "Profile declaration must use a non-empty string"
        if "unsupported settings" in text:
            return "Profile workflow has unsupported settings"
        if "invalid targets" in text:
            return "Profile workflow has invalid targets"
        if "targets must contain only strings" in text:
            return "Profile workflow targets must contain only strings"
    if text.startswith("Target ") or text.startswith("Codex target ") or text.startswith(
        "Isolated Pi target "
    ):
        if "args must contain only strings" in text:
            return "Target args must contain only strings"
        if "args must be a list of strings" in text:
            return "Target args must be a list of strings"
        if "cannot contain NUL bytes" in text:
            return "Target args cannot contain NUL bytes"
        if "reserved '--' token" in text:
            return "Target args cannot contain the reserved token"
        if "override the workspace root" in text:
            return "Codex target args cannot override the workspace root"
        if "extensions, skills, or prompt templates" in text:
            return "Isolated Pi target cannot explicitly load extensions, skills, or prompt templates"
        if "settings must be strings" in text:
            return "Target settings must be strings"
        if "backend_profile must be a string" in text:
            return "Target backend_profile must be a string"
        if "positive integer" in text:
            return "Target setting must be a positive integer"
    if text.startswith("Invalid logging level"):
        return "Invalid logging level"
    if "must be a positive integer" in text:
        return "Configuration setting must be a positive integer"
    if "must be true or false" in text:
        return "Configuration setting must be true or false"
    return "Invalid configuration"


@dataclass(frozen=True, slots=True)
class ConfigSource:
    """The one byte buffer and metadata used for one load attempt."""

    path: Path
    data: bytes
    revision: str
    modification_time: str
    loaded_at: str


def read_config_source(path: Path) -> ConfigSource:
    """Read a source once and calculate identity from those exact bytes."""
    data = path.read_bytes()
    return ConfigSource(
        path=path,
        data=data,
        revision=sha256_bytes(data),
        modification_time=modification_time(path),
        loaded_at=utc_now(),
    )


class ConfigurationLoadError(ValueError):
    """A user-safe configuration error with source health metadata."""

    def __init__(
        self,
        message: str,
        *,
        path: Path,
        revision: str = "",
        modification_time: str = "",
        attempted_at: str = "",
    ) -> None:
        super().__init__(sanitize_config_error(message))
        self.path = path
        self.revision = revision
        self.modification_time = modification_time
        self.attempted_at = attempted_at or utc_now()


__all__ = [
    "ConfigSource",
    "ConfigurationLoadError",
    "MAX_CONFIG_ERROR_LENGTH",
    "bound_error",
    "hash_config_bytes",
    "modification_time",
    "read_config_source",
    "sha256_bytes",
    "utc_now",
]
