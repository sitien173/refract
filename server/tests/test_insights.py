from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import sqlite3

import pytest

from refract.pricing import ModelPricing, PricingConfig
from refract.insights import get_stats


@pytest.fixture
def metrics_db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE job_metrics (
        job_id TEXT, finished_at TEXT, workflow TEXT, target TEXT, backend TEXT, model TEXT,
        state TEXT, failure_kind TEXT, duration_ms INTEGER, tok_input INTEGER, tok_output INTEGER,
        tok_cache_read INTEGER, tok_cache_write INTEGER, attempts INTEGER, skipped_targets INTEGER,
        retry_of TEXT)""")
    rows = [
        ("bad", "2026-01-01T23:30:00+00:00", "implement", "a", "claude", "priced", "failed", None, 3600000, 100, 20, 0, 0, 1, 0, ""),
        ("ok", "2026-01-02T00:30:00+00:00", "implement", "a", "codex", "priced", "succeeded", None, 1800000, 100, 10, 40, 5, 2, 1, "bad"),
        ("other", "2026-01-02T00:30:00+00:00", "review", "", "pi", "unpriced", "succeeded", None, 600000, 50, 5, 10, 0, None, None, ""),
    ]
    connection.executemany("INSERT INTO job_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    yield SimpleNamespace(_connection=connection)
    connection.close()


def test_stats_aggregates_work_failover_tokens_cost_and_normalizes_codex(metrics_db):
    config = PricingConfig("USD", {
        "priced": ModelPricing(1, 2, 3, 4),
    })
    result = get_stats(metrics_db, config, 7, 0, now=datetime(2026, 1, 3, tzinfo=timezone.utc))
    work = result["work_delegated"]
    assert work["by_workflow"] == {"implement": {"failed": 1, "succeeded": 1}, "review": {"succeeded": 1}}
    assert work["by_state"] == {"failed": 1, "succeeded": 2}
    assert work["worker_hours"] == pytest.approx(5 / 3)
    assert work["success_rate"] == pytest.approx(2 / 3)
    assert result["failover_saves"] == {
        "skipped_targets": 1, "retries": 1, "retries_after_failure": 1,
        "unknown_skipped_targets": 1, "unknown_attempts": 1,
    }
    codex = result["tokens"]["by_backend"]["codex"]
    assert (codex["uncached_input"], codex["cache_read"], codex["cache_hit_ratio"]) == (60, 40, .4)
    assert "unassigned" in result["tokens"]["by_target"]
    assert result["estimated_cost"]["unpriced_models"] == ["unpriced"]
    assert result["estimated_cost"]["total"] == pytest.approx(.00036)


def test_stats_normalizes_backend_input_with_cache_components(metrics_db):
    metrics_db._connection.executemany(
        "INSERT INTO job_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("claude-cache", "2026-01-02T00:30:00+00:00", "review", "a", "claude",
             "unpriced", "succeeded", None, 0, 150, 0, 20, 30, 1, 0, ""),
            ("pi-cache", "2026-01-02T00:30:00+00:00", "review", "a", "pi",
             "unpriced", "succeeded", None, 0, 105, 0, 10, 5, 1, 0, ""),
            ("agy-cache", "2026-01-02T00:30:00+00:00", "review", "a", "agy",
             "unpriced", "succeeded", None, 0, 50, 0, 10, 5, 1, 0, ""),
        ],
    )
    result = get_stats(
        metrics_db, PricingConfig(), 7, 0,
        now=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    by_backend = result["tokens"]["by_backend"]
    assert (by_backend["claude"]["input"], by_backend["claude"]["uncached_input"]) == (250, 200)
    assert (by_backend["pi"]["input"], by_backend["pi"]["uncached_input"]) == (155, 130)
    assert (by_backend["agy"]["input"], by_backend["agy"]["uncached_input"]) == (50, 50)
    assert (by_backend["codex"]["input"], by_backend["codex"]["uncached_input"]) == (100, 60)


def test_stats_timezone_offsets_produce_exact_daily_buckets(metrics_db):
    config = PricingConfig()
    now = datetime(2026, 1, 3, tzinfo=timezone.utc)
    utc = get_stats(metrics_db, config, 7, 0, now=now)["work_delegated"]["daily"]
    ahead = get_stats(metrics_db, config, 7, 120, now=now)["work_delegated"]["daily"]
    behind = get_stats(metrics_db, config, 7, -60, now=now)["work_delegated"]["daily"]
    assert utc == {"2026-01-01": {"succeeded": 0, "failed": 1},
                   "2026-01-02": {"succeeded": 2, "failed": 0}}
    assert ahead == {"2026-01-02": {"succeeded": 2, "failed": 1}}
    assert behind == {"2026-01-01": {"succeeded": 2, "failed": 1}}


def test_retry_after_failed_job_outside_window_counts_as_failover_save(metrics_db):
    metrics_db._connection.execute("DELETE FROM job_metrics")
    metrics_db._connection.execute(
        "INSERT INTO job_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("old-failure", "2025-12-30T00:00:00+00:00", "implement", "a", "codex",
         "priced", "failed", None, 0, 0, 0, 0, 0, 1, 0, ""),
    )
    metrics_db._connection.execute(
        "INSERT INTO job_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("recent-retry", "2026-01-02T00:00:00+00:00", "implement", "a", "codex",
         "priced", "succeeded", None, 0, 0, 0, 0, 0, 1, 0, "old-failure"),
    )
    result = get_stats(
        metrics_db, PricingConfig(), 1,
        now=datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
    )
    assert result["failover_saves"]["retries_after_failure"] == 1


def test_stats_rejects_timezone_offset_outside_supported_range(metrics_db):
    with pytest.raises(ValueError, match="tz_offset_minutes must be an integer between -1440 and 1440"):
        get_stats(metrics_db, PricingConfig(), 7, 999999999999)


def test_stats_window_includes_just_inside_and_excludes_just_outside(metrics_db):
    now = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
    metrics_db._connection.executemany(
        "INSERT INTO job_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("inside", (now - timedelta(days=7) + timedelta(microseconds=1)).isoformat(),
             "workflow", "t", "codex", "model", "succeeded", None, 0, 0, 0, 0, 0, 1, 0, ""),
            ("outside", (now - timedelta(days=7) - timedelta(microseconds=1)).isoformat(),
             "workflow", "t", "codex", "model", "succeeded", None, 0, 0, 0, 0, 0, 1, 0, ""),
        ],
    )
    result = get_stats(metrics_db, PricingConfig(), 7, now=now)
    assert result["work_delegated"]["by_state"]["succeeded"] == 1


def test_stats_zero_success_and_failure_count_has_zero_success_rate(metrics_db):
    metrics_db._connection.execute("DELETE FROM job_metrics")
    metrics_db._connection.executemany(
        "INSERT INTO job_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(name, "2026-01-02T00:00:00+00:00", "workflow", "t", "codex", "model",
          state, None, 0, 0, 0, 0, 0, 1, 0, "")
         for name, state in (("cancelled", "cancelled"), ("interrupted", "interrupted"))],
    )
    result = get_stats(
        metrics_db, PricingConfig(), 7,
        now=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    assert result["work_delegated"]["success_rate"] == 0.0
    assert result["work_delegated"]["daily"] == {}


def test_stats_labels_empty_backend_and_model_in_every_section_but_prices_raw_model(metrics_db):
    metrics_db._connection.execute(
        "INSERT INTO job_metrics VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("unassigned", "2026-01-02T00:30:00+00:00", "workflow", "", "", "",
         "succeeded", None, 0, 100, 0, 0, 0, 1, 0, ""),
    )
    config = PricingConfig("USD", {"": ModelPricing(1, 0, 0, 0)})
    result = get_stats(
        metrics_db, config, 7, now=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    assert result["tokens"]["by_backend"]["unassigned"]["jobs"] == 1
    assert result["tokens"]["by_model"]["unassigned"]["jobs"] == 1
    assert result["estimated_cost"]["by_model"] == {"unassigned": pytest.approx(0.0001)}
    assert "unassigned" not in result["estimated_cost"]["unpriced_models"]


@pytest.mark.parametrize("days", [2, 0, 366])
def test_stats_rejects_unsupported_days(metrics_db, days):
    with pytest.raises(ValueError, match="days must"):
        get_stats(metrics_db, PricingConfig(), days)


def test_stats_rejects_non_integer_timezone_offset(metrics_db):
    with pytest.raises(ValueError, match="tz_offset_minutes"):
        get_stats(metrics_db, PricingConfig(), 7, "x")
