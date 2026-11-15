"""Config source metadata and safe error reporting.

Errors are classified by the pydantic error ``code`` and ``loc``, never by
message text. Messages and hints are built here from fixed text so that no
configuration value, prompt, or secret reaches health records or MCP errors.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

MAX_CONFIG_ERROR_LENGTH = 512

Scope = Literal["global", "project"]
Loc = tuple[str | int, ...]

_WORKFLOWS = frozenset({"consult", "implement", "other", "review"})
_TARGET_TEXT = frozenset({"model", "reasoning", "system_prompt"})
_TARGET_NUMBERS = frozenset({"max_concurrency", "context_window"})
_TYPE_CODES = frozenset({
    "string_type", "int_type", "bool_type", "dict_type", "list_type", "model_type",
    "greater_than_equal", "less_than_equal", "string_too_short",
})

_ENV_MESSAGES = {
    "env_key_empty": "Environment key cannot be empty",
    "env_key_equals": "Environment key cannot contain '='",
    "env_key_nul": "Environment key cannot contain NUL bytes",
    "env_key_reserved": "Environment keys cannot use protected prefix",
    "env_value_nul": "Environment values cannot contain NUL bytes",
    "env_value_interpolation": "Environment values cannot contain '${'; write the literal value",
}
_FIXED_MESSAGES = {
    **_ENV_MESSAGES,
    "empty_profile": "Profile declaration must declare extends or a workflow",
    "breaker_order": "[daemon].breaker_max_cooldown_s must be >= breaker_base_cooldown_s",
    "log_level": "Invalid logging level",
    "log_file_type": "logging.file must be a path string or false",
    "args_nul": "Target args cannot contain NUL bytes",
    "args_reserved_token": "Target args cannot contain the reserved token",
    "args_workspace_override": "Codex target args cannot override the workspace root",
    "unknown_default_profile": "Unknown [daemon].default_profile",
    "duplicate_target": "Target identifiers must be unique",
    "unknown_target": "Profile workflow has invalid targets",
    "duplicate_selection_target": "Profile workflow has invalid targets",
    "unknown_parent": "Profile extends unknown parent",
    "profile_cycle": "Profile inheritance cycle",
    "project_unknown_target": "Project config cannot add targets",
    "project_duplicate_target": "Duplicate project target override",
}
_HINTS = {
    "missing": "Add the required key.",
    "extra_forbidden": "Remove the unknown key or correct its spelling.",
    "literal_error": "Use one of the supported values.",
    "toml_syntax": "Fix the TOML syntax at the reported line and column.",
    "invalid_utf8": "Save the config file as UTF-8.",
    "missing_file": "Create the config file; see server/config.v3.toml for an example.",
    "unreadable_file": "Check that the config file is readable.",
}
_DEFAULT_HINT = "Correct the value at this location in the config file."
_SCHEMA_HINT = "Add schema_version = 1 at the top level of the config file."


@dataclass(frozen=True, slots=True)
class ConfigIssue:
    """One load error with its pydantic ``code``, ``loc``, and safe text."""

    code: str
    loc: Loc
    msg: str
    hint: str

    def as_json(self) -> dict[str, object]:
        return {"code": self.code, "loc": list(self.loc), "msg": self.msg, "hint": self.hint}


def _extra_forbidden(loc: Loc, scope: Scope) -> str:
    section = loc[0] if loc else ""
    if len(loc) == 1:
        return "Unsupported project config sections" if scope == "project" else "Unsupported config sections"
    if section == "targets":
        if scope == "project":
            return "Unsupported project target settings"
        return "Target has invalid retry settings" if len(loc) > 3 else "Unsupported target settings"
    if section == "profiles":
        return "Unknown workflow" if len(loc) == 3 else "Profile workflow has unsupported settings"
    return f"Unsupported {section} settings"


def _missing(loc: Loc, scope: Scope) -> str:
    if loc == ("schema_version",):
        return "Missing required schema_version"
    if len(loc) == 1:
        return f"Missing required [{loc[0]}] section"
    if loc == ("daemon", "default_profile"):
        return "[daemon].default_profile must be set"
    if scope == "project" and loc[-1] == "id":
        return "Project config cannot add targets"
    return "Invalid target declaration" if loc[0] == "targets" else "Missing required setting"


def _literal(loc: Loc) -> str:
    if loc == ("schema_version",):
        return "Unsupported schema_version; expected 1"
    if "codes" in loc:
        return "Unknown retry code"
    return "Invalid target declaration" if loc[-1] == "backend" else "Invalid configuration"


def _empty_string(loc: Loc) -> str:
    return {
        "default_profile": "[daemon].default_profile must be set",
        "host": "[daemon].host must be a non-empty string",
        "extends": "Profile declaration must use a non-empty string",
    }.get(str(loc[-1]), "Invalid target declaration")


def _too_short(loc: Loc) -> str:
    if loc == ("targets",):
        return "[targets] must contain at least one target"
    if loc == ("profiles",):
        return "[profiles] must contain at least one profile"
    return "Profile workflow has invalid targets"


def _target_type(loc: Loc, code: str) -> str:
    tail = loc[-1]
    if len(loc) == 2:
        return "Each target must be a TOML table"
    if "env" in loc:
        return "Target env must be a TOML table" if tail == "env" else "Environment values must be strings"
    if "args" in loc:
        return "Target args must be a list of strings"
    if "retry" in loc:
        return "Target has invalid retry settings"
    if tail in _TARGET_NUMBERS:
        return "Target setting must be a positive integer"
    if tail == "backend_profile":
        return "Target backend_profile must be a string"
    if tail in _TARGET_TEXT:
        return "Target settings must be strings"
    return "Invalid target declaration"


def _profile_type(loc: Loc) -> str:
    if len(loc) == 1:
        return "[profiles] must contain at least one profile"
    if len(loc) == 2:
        return "Profile declaration must declare extends or a workflow"
    if loc[2] == "extends":
        return "Profile declaration must use a non-empty string"
    if loc[-1] == "timeout_s":
        return "timeout_s must be a non-negative integer"
    if isinstance(loc[-1], int):
        return "Profile workflow targets must contain only strings"
    return "Profile workflow has invalid targets"


def _section_type(loc: Loc, code: str) -> str:
    section, tail = loc[0], loc[-1]
    if len(loc) == 1:
        return f"[{section}] must be a TOML table"
    if section == "notifications":
        return "notifications.enabled must be true or false"
    if section == "logging":
        if tail == "level":
            return "Invalid logging level"
        if code == "greater_than_equal":
            return f"logging.{tail} must be at least {1 if tail == 'max_bytes' else 0}"
        return "Logging retention settings must be integers"
    if code == "less_than_equal":
        return "[daemon].port must not exceed 65535"
    if tail in {"host", "default_profile"}:
        return f"[daemon].{tail} must be a non-empty string"
    return "Configuration setting must be a positive integer"


def _type_error(code: str, loc: Loc) -> str:
    if not loc:
        return "Invalid configuration"
    if loc == ("schema_version",):
        return "Unsupported schema_version; expected 1"
    if loc == ("targets",):
        return "[targets] must be a TOML array of tables"
    if loc[0] == "targets":
        return _target_type(loc, code)
    if loc[0] == "profiles":
        return _profile_type(loc)
    if loc[0] in {"daemon", "logging", "notifications"}:
        return _section_type(loc, code)
    return "Invalid configuration"


def describe(code: str, loc: Loc, scope: Scope = "global") -> tuple[str, str]:
    """Return the safe message and fix hint for one error code and location."""
    if code in _FIXED_MESSAGES:
        message = _FIXED_MESSAGES[code]
    elif code == "extra_forbidden":
        message = _extra_forbidden(loc, scope)
    elif code == "missing":
        message = _missing(loc, scope)
    elif code == "literal_error":
        message = _literal(loc)
    elif code == "empty_string":
        message = _empty_string(loc)
    elif code == "too_short":
        message = _too_short(loc)
    elif code in _TYPE_CODES:
        message = _type_error(code, loc)
    else:
        message = "Invalid configuration"
    if loc == ("schema_version",) and code in {"missing", "literal_error"}:
        return message, _SCHEMA_HINT
    return message, _HINTS.get(code, _DEFAULT_HINT)


def make_issue(
    code: str, loc: Loc = (), scope: Scope = "global", *, msg: str | None = None
) -> ConfigIssue:
    """Build an issue; ``msg`` overrides the text for source-level errors."""
    message, hint = describe(code, loc, scope)
    return ConfigIssue(code, loc, msg if msg is not None else message, hint)


def issues_from_validation_error(error: ValidationError, scope: Scope = "global") -> tuple[ConfigIssue, ...]:
    """Convert pydantic errors without reading their messages or input values."""
    return tuple(
        make_issue(item["type"], tuple(item["loc"]), scope)
        for item in error.errors(include_url=False, include_context=False, include_input=False)
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    """Return the full lowercase SHA-256 digest of *data*."""
    return hashlib.sha256(data).hexdigest()


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
    """A user-safe configuration error with issues and source health metadata."""

    def __init__(
        self,
        issues: tuple[ConfigIssue, ...],
        *,
        path: Path,
        revision: str = "",
        modification_time: str = "",
        attempted_at: str = "",
    ) -> None:
        super().__init__(bound_error("; ".join(dict.fromkeys(issue.msg for issue in issues))))
        self.issues = issues
        self.path = path
        self.revision = revision
        self.modification_time = modification_time
        self.attempted_at = attempted_at or utc_now()

    def payload(self) -> dict[str, object]:
        """The ``config_invalid`` error object shared by the CLI and MCP layers."""
        return {"code": "config_invalid", "errors": [issue.as_json() for issue in self.issues]}


def sanitize_config_error(error: object) -> str:
    """Return the safe text of a load error, or a generic text for anything else."""
    if isinstance(error, ConfigurationLoadError):
        return str(error)
    return "Invalid configuration"


__all__ = [
    "ConfigIssue",
    "ConfigSource",
    "ConfigurationLoadError",
    "MAX_CONFIG_ERROR_LENGTH",
    "bound_error",
    "describe",
    "issues_from_validation_error",
    "make_issue",
    "modification_time",
    "read_config_source",
    "sanitize_config_error",
    "sha256_bytes",
    "utc_now",
]
