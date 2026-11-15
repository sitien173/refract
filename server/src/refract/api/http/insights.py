"""Local usage analytics from retained jobs and their attempts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from refract.models import TERMINAL_STATES
from refract.store import attempts as attempt_rows
from refract.store.jobs import DERIVED

INPUT_INCLUDES_CACHE_COMPONENTS = {
    "codex": frozenset({"cache_read"}),
    "claude": frozenset({"cache_read", "cache_write"}),
    "pi": frozenset({"cache_read", "cache_write"}),
}
VALID_DAYS = frozenset({1, 7, 30, 365})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _strip_provider_prefix(raw: str) -> str:
    """Drop a leading provider prefix (`provider/model` -> `model`)."""
    return raw.rpartition("/")[2] or raw


_TERMINAL = tuple(sorted(TERMINAL_STATES))
_ROWS = (
    "SELECT j.id AS job_id, COALESCE(j.finished_at, j.updated_at) AS finished_at, j.profile, j.workflow, j.state,"
    f" j.failure_kind, {DERIVED},"
    " COALESCE((SELECT a.backend FROM attempts a WHERE a.job_id=j.id ORDER BY a.seq DESC LIMIT 1), '') AS backend,"
    " (SELECT COUNT(*) FROM attempts a WHERE a.job_id=j.id) AS attempt_count,"
    " (SELECT COUNT(*) FROM attempts a WHERE a.job_id=j.id AND a.reason='fallback') AS fallback_count"
    f" FROM jobs j WHERE j.state IN ({','.join('?' for _ in _TERMINAL)})"
    " AND COALESCE(j.finished_at, j.updated_at) >= ? ORDER BY finished_at, j.id"
)


def get_stats(database: Any, days: int = 7,
              tz_offset_minutes: int = 0, *, now: datetime | None = None) -> dict[str, Any]:
    """Aggregate retained jobs for one rolling window."""
    if isinstance(days, bool) or days not in VALID_DAYS:
        raise ValueError("days must be one of 1, 7, 30, or 365")
    if (isinstance(tz_offset_minutes, bool) or not isinstance(tz_offset_minutes, int)
            or not -1440 <= tz_offset_minutes <= 1440):
        raise ValueError("tz_offset_minutes must be an integer between -1440 and 1440")
    end = now or _utc_now()
    start = end - timedelta(days=days)
    connection = database._connection
    records = [dict(row) for row in connection.execute(_ROWS, (*_TERMINAL, start.isoformat()))]
    by_reason = attempt_rows.counts_by_reason(connection, start.isoformat())
    by_workflow: dict[str, dict[str, int]] = {}
    by_state: dict[str, int] = {}
    breakdown: dict[tuple[str, str, str, str], int] = {}
    daily: dict[str, dict[str, int]] = {}
    skipped = retries = 0
    unknown_attempts = unknown_skipped_targets = 0
    total_duration = succeeded = failures = 0
    by_backend: dict[str, dict[str, int]] = {}
    by_model: dict[str, dict[str, int]] = {}
    by_target: dict[str, dict[str, int]] = {}

    def token_accumulator(mapping: dict[str, dict[str, int]], key: str) -> dict[str, int]:
        return mapping.setdefault(key, {"input": 0, "uncached_input": 0, "output": 0,
                                        "cache_read": 0, "cache_write": 0, "jobs": 0})

    for row in records:
        state = row["state"]
        workflow = row["workflow"]
        by_workflow.setdefault(workflow, {})[state] = by_workflow.setdefault(workflow, {}).get(state, 0) + 1
        by_state[state] = by_state.get(state, 0) + 1
        key = (row["profile"] or "unknown", workflow, row["target"] or "unknown", state)
        breakdown[key] = breakdown.get(key, 0) + 1
        total_duration += row["duration_ms"] or 0
        if state == "succeeded":
            succeeded += 1
        elif state == "failed":
            failures += 1
        local = datetime.fromisoformat(row["finished_at"].replace("Z", "+00:00")) + timedelta(minutes=tz_offset_minutes)
        day = local.date().isoformat()
        if state in {"succeeded", "failed"}:
            daily.setdefault(day, {"succeeded": 0, "failed": 0})
            daily[day][state] += 1
        if state == "succeeded":
            if row["attempt_count"] == 0:
                unknown_skipped_targets += 1
                unknown_attempts += 1
            else:
                skipped += int(row["fallback_count"] > 0)
                retries += int(row["attempt_count"] > 1)

        raw_input = row["tok_input"] or 0
        cache_read = row["tok_cache_read"] or 0
        cache_write = row["tok_cache_write"] or 0
        included_components = INPUT_INCLUDES_CACHE_COMPONENTS.get(row["backend"], frozenset())
        included_cache = (cache_read if "cache_read" in included_components else 0) + (
            cache_write if "cache_write" in included_components else 0
        )
        uncached = max(0, raw_input - included_cache)
        values = {"input": raw_input, "uncached_input": uncached, "output": row["tok_output"] or 0,
                  "cache_read": cache_read, "cache_write": cache_write}
        label = _strip_provider_prefix(row["model"] or "") or "unassigned"
        dimensions = ((by_backend, row["backend"] or "unassigned"),
                      (by_model, label),
                      (by_target, row["target"] or "unassigned"))
        for mapping, key in dimensions:
            totals = token_accumulator(mapping, key)
            for name, value in values.items():
                totals[name] += value
            totals["jobs"] += 1

    def add_cache_ratio(values: dict[str, dict[str, int]]) -> dict[str, dict[str, int | float]]:
        return {key: {**item, "cache_hit_ratio": item["cache_read"] /
                      (item["uncached_input"] + item["cache_read"])
                      if item["uncached_input"] + item["cache_read"] else 0.0}
                for key, item in values.items()}

    return {
        "days": days,
        "work_delegated": {"by_workflow": by_workflow, "by_state": by_state,
            "breakdown": [{"profile": profile, "workflow": workflow, "target": target, "state": state, "jobs": jobs}
                          for (profile, workflow, target, state), jobs in sorted(breakdown.items())],
            "worker_hours": total_duration / 3_600_000,
            "success_rate": succeeded / (succeeded + failures) if succeeded + failures else 0.0,
            "daily": dict(sorted(daily.items()))},
        "failover_saves": {"skipped_targets": skipped, "retries": retries,
                            "attempts_by_reason": by_reason,
                            "unknown_skipped_targets": unknown_skipped_targets,
                            "unknown_attempts": unknown_attempts},
        "tokens": {"by_backend": add_cache_ratio(by_backend), "by_model": add_cache_ratio(by_model),
                   "by_target": add_cache_ratio(by_target)},
    }
