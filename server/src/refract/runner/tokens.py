"""Flat token counters: six nullable integers, null when unknown, never zero-filled."""

from __future__ import annotations

from typing import Any

TOKEN_KEYS = ("context_used", "context_window", "input", "output", "cache_read", "cache_write")
CONSUMPTION_KEYS = ("input", "output", "cache_read", "cache_write")


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


class TokenCounters:
    """Backend totals and context are recorded per field; an unrecorded field stays unknown."""

    def __init__(self) -> None:
        self._totals: dict[str, int] = {}
        self._context: dict[str, int] = {}

    def record_totals(
        self,
        *,
        input: Any = None,
        output: Any = None,
        cache_read: Any = None,
        cache_write: Any = None,
    ) -> None:
        values = {"input": input, "output": output, "cache_read": cache_read, "cache_write": cache_write}
        for key, value in values.items():
            count = _count(value)
            if count is not None:
                self._totals[key] = count

    def record_context(self, *, used: Any = None, window: Any = None) -> None:
        for key, value in (("context_used", used), ("context_window", window)):
            count = _count(value)
            if count is not None:
                self._context[key] = count

    def as_dict(self) -> dict[str, int | None]:
        return {
            "context_used": self._context.get("context_used"),
            "context_window": self._context.get("context_window"),
            **{key: self._totals.get(key) for key in CONSUMPTION_KEYS},
        }


def counters_from(values: dict[str, Any]) -> TokenCounters:
    """Build one attempt's counters from a snapshot; a key absent from the snapshot is unknown."""
    counters = TokenCounters()
    counters.record_totals(
        input=values.get("input"), output=values.get("output"),
        cache_read=values.get("cache_read"), cache_write=values.get("cache_write"),
    )
    counters.record_context(used=values.get("context_used"), window=values.get("context_window"))
    return counters


def attempt_tokens(counters: TokenCounters | None, window: int | None) -> dict[str, int | None] | None:
    """One attempt's tokens; the target's configured window wins and context used never exceeds it."""
    if counters is None and window is None:
        return None
    tokens = (counters or TokenCounters()).as_dict()
    if window is not None:
        tokens["context_window"] = window
    if tokens["context_used"] is None and tokens["input"] is not None and tokens["output"] is not None:
        tokens["context_used"] = tokens["input"] + tokens["output"]
    if tokens["context_used"] is not None and tokens["context_window"] is not None:
        tokens["context_used"] = min(tokens["context_used"], tokens["context_window"])
    return tokens
