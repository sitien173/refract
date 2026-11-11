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


def get_stats(database: Any, pricing: PricingConfig, days: int = 7,
              tz_offset_minutes: int = 0, *, now: datetime | None = None) -> dict[str, Any]:
    """Aggregate retained job metrics for one rolling window."""
    if isinstance(days, bool) or days not in VALID_DAYS:
        raise ValueError("days must be one of 1, 7, 30, or 365")
    if (isinstance(tz_offset_minutes, bool) or not isinstance(tz_offset_minutes, int)
            or not -1440 <= tz_offset_minutes <= 1440):
        raise ValueError("tz_offset_minutes must be an integer between -1440 and 1440")
    end = now or _utc_now()
    start = end - timedelta(days=days)
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
    by_workflow: dict[str, dict[str, int]] = {}
    by_state: dict[str, int] = {}
    daily: dict[str, dict[str, int]] = {}
    skipped = retries = retry_jobs = 0
    unknown_attempts = unknown_skipped_targets = 0
    total_duration = succeeded = failures = 0
    by_backend: dict[str, dict[str, int]] = {}
    by_model: dict[str, dict[str, int]] = {}
    by_target: dict[str, dict[str, int]] = {}
    cost_models: dict[str, float] = {}
    unpriced: set[str] = set()
    cost_total = 0.0

    def token_accumulator(mapping: dict[str, dict[str, int]], key: str) -> dict[str, int]:
        return mapping.setdefault(key, {"input": 0, "uncached_input": 0, "output": 0,
                                        "cache_read": 0, "cache_write": 0, "jobs": 0})

    for row in records:
        state = row["state"]
        workflow = row["workflow"]
        by_workflow.setdefault(workflow, {})[state] = by_workflow.setdefault(workflow, {}).get(state, 0) + 1
        by_state[state] = by_state.get(state, 0) + 1
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
            if row["skipped_targets"] is None:
                unknown_skipped_targets += 1
            else:
                skipped += int(row["skipped_targets"] > 0)
            if row["attempts"] is None:
                unknown_attempts += 1
            else:
                retries += int(row["attempts"] > 1)
            retry_jobs += int(bool(row["retry_of"] and row["retry_of"] in failed_retry_ids))

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
        dimensions = ((by_backend, row["backend"] or "unassigned"),
                      (by_model, label),
                      (by_target, row["target"] or "unassigned"))
        for mapping, key in dimensions:
            totals = token_accumulator(mapping, key)
            for name, value in values.items():
                totals[name] += value
            totals["jobs"] += 1
        price = pricing.models.get(canonical)
        if price is None:
            unpriced.add(label)
            continue
        amount = (uncached * price.input + values["output"] * price.output
                  + cache_read * price.cache_read + values["cache_write"] * price.cache_write) / 1_000_000
        cost_total += amount
        cost_models[label] = cost_models.get(label, 0.0) + amount

    def add_cache_ratio(values: dict[str, dict[str, int]]) -> dict[str, dict[str, int | float]]:
        return {key: {**item, "cache_hit_ratio": item["cache_read"] /
                      (item["uncached_input"] + item["cache_read"])
                      if item["uncached_input"] + item["cache_read"] else 0.0}
                for key, item in values.items()}

    return {
        "days": days,
        "currency": pricing.currency,
        "work_delegated": {"by_workflow": by_workflow, "by_state": by_state,
            "worker_hours": total_duration / 3_600_000,
            "success_rate": succeeded / (succeeded + failures) if succeeded + failures else 0.0,
            "daily": dict(sorted(daily.items()))},
        "failover_saves": {"skipped_targets": skipped, "retries": retries,
                            "retries_after_failure": retry_jobs,
                            "unknown_skipped_targets": unknown_skipped_targets,
                            "unknown_attempts": unknown_attempts},
        "tokens": {"by_backend": add_cache_ratio(by_backend), "by_model": add_cache_ratio(by_model),
                   "by_target": add_cache_ratio(by_target)},
        "estimated_cost": {"total": cost_total, "by_model": dict(sorted(cost_models.items())),
                           "unpriced_models": sorted(unpriced)},
    }
