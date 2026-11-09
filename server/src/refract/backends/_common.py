"""Helpers shared by backend parsers: token normalization, tool events, and bounded event buffering.

Only helpers that more than one backend needs belong here. Backends that still keep their own
copies migrate onto this module when they are moved to the async path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import AsyncEventHandler, classify_backend_output, classify_tool_activity


def as_int(val: Any) -> int | None:
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        return None
    return val


def read_and_unlink(path: Path, *, errors: str) -> str:
    """Return the file's UTF-8 text, or "" when it cannot be read. The file is removed either way."""
    try:
        return path.read_text(encoding="utf-8", errors=errors)
    except OSError:
        return ""
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def parse_token_component(usage: dict[str, Any], key: str) -> tuple[int | None, bool]:
    """Return (value, malformed). A missing or null key is absent, not malformed."""
    if key not in usage:
        return None, False
    val = usage[key]
    if val is None:
        return None, False
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        return None, True
    return val, False


@dataclass(slots=True, frozen=True)
class TokenUsage:
    """Normalized usage. ``input`` is raw input plus cache reads and writes, or None when the raw input is absent or malformed.

    ``observed`` is True when any component was present or malformed, which is the
    condition for recording consumption.
    """

    input: int | None
    output: int | None
    cache_read: int | None
    cache_write: int | None
    observed: bool


def read_usage(
    usage: dict[str, Any],
    *,
    input_key: str = "input_tokens",
    output_key: str = "output_tokens",
    cache_read_key: str = "cache_read_input_tokens",
    cache_write_key: str = "cache_creation_input_tokens",
) -> TokenUsage:
    raw_in, raw_in_bad = parse_token_component(usage, input_key)
    cr, cr_bad = parse_token_component(usage, cache_read_key)
    cw, cw_bad = parse_token_component(usage, cache_write_key)
    raw_out, raw_out_bad = parse_token_component(usage, output_key)
    if raw_in_bad or cr_bad or cw_bad or raw_in is None:
        norm_in = None
    else:
        norm_in = raw_in + (cr or 0) + (cw or 0)
    observed = any(v is not None for v in (norm_in, cr, cw, raw_out)) or raw_in_bad or cr_bad or cw_bad or raw_out_bad
    return TokenUsage(input=norm_in, output=raw_out, cache_read=cr, cache_write=cw, observed=observed)


def is_fatal_line(line: str) -> bool:
    """Apply the classifier's fatal-token rule to one diagnostic line."""
    probe = classify_backend_output(backend_name="", agent_messages="x", session_id="x", error_text=line)
    return probe.error_class == "fatal_backend"


def tool_started(entity_id: str, provider: str, tool_name: str, *, has_input: bool, tool_input: Any = None) -> dict[str, Any]:
    """Build a ``tool.started`` event. ``input`` is included only when ``has_input`` is set."""
    data: dict[str, Any] = {"tool": tool_name, "activity": classify_tool_activity(provider, tool_name)}
    if has_input:
        data["input"] = tool_input
    return {"kind": "tool.started", "entity_id": entity_id, "data": data}


class EventBuffer:
    """Collect the events one parsed line produces, then await the sink once per event in order.

    The parser stays synchronous. Events are only collected when a sink is set, which is the
    streaming case. ``flush`` runs after each line, so a failing sink fails the attempt at that line.
    """

    def __init__(self, sink: AsyncEventHandler | None) -> None:
        self._sink = sink
        self._pending: list[dict[str, Any]] = []

    @property
    def enabled(self) -> bool:
        return self._sink is not None

    def emit(self, event: dict[str, Any]) -> None:
        if self._sink is not None:
            self._pending.append(event)

    async def flush(self) -> None:
        if self._sink is None:
            return
        while self._pending:
            await self._sink(self._pending.pop(0))


__all__ = [
    "EventBuffer",
    "TokenUsage",
    "as_int",
    "is_fatal_line",
    "parse_token_component",
    "read_and_unlink",
    "read_usage",
    "tool_started",
]
