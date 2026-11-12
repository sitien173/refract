"""Local usage analytics from the retained per-job metrics table."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from refract.pricing import PricingConfig, canonical_model

INPUT_INCLUDES_CACHE_COMPONENTS = {
    "codex": frozenset({"cache_read"}),
    "claude": frozenset({"cache_read", "cache_write"}),
    "pi": frozenset({"cache_read", "cache_write"}),
}
VALID_DAYS = frozenset({1, 7, 30, 365})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _token_accumulator(mapping: dict[str, dict[str, int]], key: str) -> dict[str, int]:
    return mapping.setdefault(key, {"input": 0, "uncached_input": 0, "output": 0,
                                    "cache_read": 0, "cache_write": 0, "jobs": 0})


def _add_cache_ratio(values: dict[str, dict[str, int]]) -> dict[str, dict[str, int | float]]:
    return {key: {**item, "cache_hit_ratio": item["cache_read"] /
                  (item["uncached_input"] + item["cache_read"])
                  if item["uncached_input"] + item["cache_read"] else 0.0}
            for key, item in values.items()}


def _validate_stats_args(days: int, tz_offset_minutes: int) -> None:
    if isinstance(days, bool) or days not in VALID_DAYS:
        raise ValueError("days must be one of 1, 7, 30, or 365")
    if (isinstance(tz_offset_minutes, bool) or not isinstance(tz_offset_minutes, int)
            or not -1440 <= tz_offset_minutes <= 1440):
        raise ValueError("tz_offset_minutes must be an integer between -1440 and 1440")


def _load_stats_rows(database: Any, start: datetime) -> tuple[list[dict[str, Any]], set[str]]:
    rows = database._connection.execute(
        "SELECT * FROM job_metrics WHERE finished_at >= ? ORDER BY finished_at, job_id",
        (start.isoformat(),),
    ).fetchall()
    records = [dict(row) for row in rows]
    failed_retry_ids = {
        row["job_id"] for row in database._connection.execute(
            "SELECT job_id FROM job_metrics WHERE state='failed' AND job_id IN "
            "(SELECT retry_of FROM job_metrics WHERE state='succeeded' AND finished_at >= ? "
            "AND retry_of != '')",
            (start.isoformat(),),
        ).fetchall()
    }
    return records, failed_retry_ids


def _count_stats_row(row: dict[str, Any], tz_offset_minutes: int,
                     totals: dict[str, Any], failed_retry_ids: set[str]) -> None:
    state = row["state"]
    workflow = row["workflow"]
    workflow_counts = totals["by_workflow"].setdefault(workflow, {})
    workflow_counts[state] = workflow_counts.get(state, 0) + 1
    totals["by_state"][state] = totals["by_state"].get(state, 0) + 1
    key = (row["profile"] or "unknown", workflow, row["target"] or "unknown", state)
    totals["breakdown"][key] = totals["breakdown"].get(key, 0) + 1
    totals["duration"] += row["duration_ms"] or 0
    if state == "succeeded":
        totals["succeeded"] += 1
    elif state == "failed":
        totals["failures"] += 1
    local = datetime.fromisoformat(row["finished_at"].replace("Z", "+00:00")) + timedelta(
        minutes=tz_offset_minutes)
    day = local.date().isoformat()
    if state in {"succeeded", "failed"}:
        daily = totals["daily"].setdefault(day, {"succeeded": 0, "failed": 0})
        daily[state] += 1
    if state == "succeeded":
        if row["skipped_targets"] is None:
            totals["unknown_skipped_targets"] += 1
        else:
            totals["skipped"] += int(row["skipped_targets"] > 0)
        if row["attempts"] is None:
            totals["unknown_attempts"] += 1
        else:
            totals["retries"] += int(row["attempts"] > 1)
        totals["retry_jobs"] += int(bool(row["retry_of"] and row["retry_of"] in failed_retry_ids))


def _accumulate_row_tokens(row: dict[str, Any], pricing: PricingConfig,
                           totals: dict[str, Any]) -> None:
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
    canonical = canonical_model(row["model"] or "", pricing.aliases)
    label = canonical or "unassigned"
    dimensions = ((totals["by_backend"], row["backend"] or "unassigned"),
                  (totals["by_model"], label), (totals["by_target"], row["target"] or "unassigned"))
    for mapping, key in dimensions:
        aggregate = _token_accumulator(mapping, key)
        for name, value in values.items():
            aggregate[name] += value
        aggregate["jobs"] += 1
    price = pricing.models.get(canonical)
    if price is None:
        totals["unpriced"].add(label)
        return
    amount = (uncached * price.input + values["output"] * price.output
              + cache_read * price.cache_read + values["cache_write"] * price.cache_write) / 1_000_000
    totals["cost_total"] += amount
    totals["cost_models"][label] = totals["cost_models"].get(label, 0.0) + amount


def _assemble_stats(days: int, pricing: PricingConfig, totals: dict[str, Any]) -> dict[str, Any]:
    succeeded = totals["succeeded"]
    failures = totals["failures"]
    return {
        "days": days,
        "currency": pricing.currency,
        "work_delegated": {"by_workflow": totals["by_workflow"], "by_state": totals["by_state"],
            "breakdown": [{"profile": profile, "workflow": workflow, "target": target,
                           "state": state, "jobs": jobs}
                          for (profile, workflow, target, state), jobs in sorted(totals["breakdown"].items())],
            "worker_hours": totals["duration"] / 3_600_000,
            "success_rate": succeeded / (succeeded + failures) if succeeded + failures else 0.0,
            "daily": dict(sorted(totals["daily"].items()))},
        "failover_saves": {"skipped_targets": totals["skipped"], "retries": totals["retries"],
            "retries_after_failure": totals["retry_jobs"],
            "unknown_skipped_targets": totals["unknown_skipped_targets"],
            "unknown_attempts": totals["unknown_attempts"]},
        "tokens": {"by_backend": _add_cache_ratio(totals["by_backend"]),
                   "by_model": _add_cache_ratio(totals["by_model"]),
                   "by_target": _add_cache_ratio(totals["by_target"])},
        "estimated_cost": {"total": totals["cost_total"],
                           "by_model": dict(sorted(totals["cost_models"].items())),
                           "unpriced_models": sorted(totals["unpriced"])},
    }


def get_stats(database: Any, pricing: PricingConfig, days: int = 7,
              tz_offset_minutes: int = 0, *, now: datetime | None = None) -> dict[str, Any]:
    """Aggregate retained job metrics for one rolling window."""
    _validate_stats_args(days, tz_offset_minutes)
    end = now or _utc_now()
    start = end - timedelta(days=days)
    records, failed_retry_ids = _load_stats_rows(database, start)
    totals: dict[str, Any] = {
        "by_workflow": {}, "by_state": {}, "breakdown": {}, "daily": {}, "skipped": 0,
        "retries": 0, "retry_jobs": 0, "unknown_attempts": 0,
        "unknown_skipped_targets": 0, "duration": 0, "succeeded": 0, "failures": 0,
        "by_backend": {}, "by_model": {}, "by_target": {}, "cost_models": {},
        "unpriced": set(), "cost_total": 0.0,
    }
    for row in records:
        _count_stats_row(row, tz_offset_minutes, totals, failed_retry_ids)
        _accumulate_row_tokens(row, pricing, totals)
    return _assemble_stats(days, pricing, totals)
