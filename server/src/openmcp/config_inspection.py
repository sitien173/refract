"""Safe metadata helpers for global configuration loading."""

from __future__ import annotations

import hashlib
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
        # The exception retains the established validation message. Runtime
        # health storage applies the bound before exposing it.
        super().__init__(message)
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
