from __future__ import annotations

from typing import Any

TOKEN_KEYS = ("context_used", "context_window", "input", "output", "cache_read", "cache_write")


def tokens(**fields: int | None) -> dict[str, int | None]:
    """A full token mapping with every key unknown except the given ones."""
    return {**dict.fromkeys(TOKEN_KEYS), **fields}


def telemetry(**fields: int | None) -> dict[str, Any]:
    """A `telemetry.updated` event carrying `tokens(**fields)`."""
    return {"kind": "telemetry.updated", "data": tokens(**fields)}
