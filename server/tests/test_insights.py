from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import sqlite3

import pytest

import refract.database as database_module
from refract.pricing import ModelPricing, PricingConfig
from refract.insights import get_stats


INSERT_METRICS = (
    "INSERT INTO job_metrics(job_id, finished_at, workflow, target, backend, model, state, failure_kind, "
    "duration_ms, tok_input, tok_output, tok_cache_read, tok_cache_write, attempts, skipped_targets, retry_of) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
)


@pytest.fixture
def metrics_db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(database_module._METRICS_DDL[0])
    rows = [
        ("bad", "2026-01-01T23:30:00+00:00", "implement", "a", "claude", "priced", "failed", None, 3600000, 100, 20, 0, 0, 1, 0, ""),
        ("ok", "2026-01-02T00:30:00+00:00", "implement", "a", "codex", "priced", "succeeded", None, 1800000, 100, 10, 40, 5, 2, 1, "bad"),
        ("other", "2026-01-02T00:30:00+00:00", "review", "", "pi", "unpriced", "succeeded", None, 600000, 50, 5, 10, 0, None, None, ""),
    ]
    connection.executemany(INSERT_METRICS, rows)
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
        INSERT_METRICS,
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
        INSERT_METRICS,
        ("old-failure", "2025-12-30T00:00:00+00:00", "implement", "a", "codex",
         "priced", "failed", None, 0, 0, 0, 0, 0, 1, 0, ""),
    )
    metrics_db._connection.execute(
        INSERT_METRICS,
        ("recent-retry", "2026-01-02T00:00:00+00:00", "implement", "a", "codex",
         "priced", "succeeded", None, 0, 0, 0, 0, 0, 1, 0, "old-failure"),
    )
    result = get_stats(
        metrics_db, PricingConfig(), 1,
        now=datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
    )
    assert result["failover_saves"]["retries_after_failure"] == 1


def test_stats_rejects_timezone_offset_outside_supported_range(metrics_db):
    config = PricingConfig()
    with pytest.raises(ValueError, match="tz_offset_minutes must be an integer between -1440 and 1440"):
        get_stats(metrics_db, config, 7, 999999999999)


def test_stats_window_includes_just_inside_and_excludes_just_outside(metrics_db):
    now = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
    metrics_db._connection.executemany(
        INSERT_METRICS,
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
        INSERT_METRICS,
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


def _insert_models(metrics_db, *models):
    metrics_db._connection.execute("DELETE FROM job_metrics")
    metrics_db._connection.executemany(
        INSERT_METRICS,
        [(f"job-{index}", "2026-01-02T00:30:00+00:00", "workflow", "a", "codex", model,
          "succeeded", None, 0, 100, 10, 0, 0, 1, 0, "")
         for index, model in enumerate(models)],
    )


def test_stats_merges_prefixed_and_aliased_models_in_tokens_and_cost(metrics_db):
    _insert_models(metrics_db, "gpt-6-luna", "openai-codex/gpt-6-luna", "Display L")
    config = PricingConfig(
        "USD", {"gpt-6-luna": ModelPricing(1, 0, 0, 0)}, {"Display L": "gpt-6-luna"})
    result = get_stats(metrics_db, config, 7, now=datetime(2026, 1, 3, tzinfo=timezone.utc))
    by_model = result["tokens"]["by_model"]
    assert list(by_model) == ["gpt-6-luna"]
    assert (by_model["gpt-6-luna"]["input"], by_model["gpt-6-luna"]["jobs"]) == (300, 3)
    assert result["estimated_cost"]["by_model"] == {"gpt-6-luna": pytest.approx(0.0003)}
    assert result["estimated_cost"]["unpriced_models"] == []


def test_stats_lists_canonical_names_as_unpriced(metrics_db):
    _insert_models(metrics_db, "p/x", "x")
    result = get_stats(
        metrics_db, PricingConfig(), 7, now=datetime(2026, 1, 3, tzinfo=timezone.utc))
    assert list(result["tokens"]["by_model"]) == ["x"]
    assert result["estimated_cost"]["unpriced_models"] == ["x"]
    assert result["estimated_cost"]["by_model"] == {}


def test_stats_cost_labels_are_token_labels(metrics_db):
    _insert_models(metrics_db, "p/m", "", "other")
    config = PricingConfig("USD", {"m": ModelPricing(1, 0, 0, 0), "": ModelPricing(1, 0, 0, 0)})
    result = get_stats(metrics_db, config, 7, now=datetime(2026, 1, 3, tzinfo=timezone.utc))
    assert set(result["estimated_cost"]["by_model"]) == {"m", "unassigned"}
    assert set(result["estimated_cost"]["by_model"]) <= set(result["tokens"]["by_model"])


def test_stats_labels_empty_backend_and_model_in_every_section_but_prices_raw_model(metrics_db):
    metrics_db._connection.execute(
        INSERT_METRICS,
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
    config = PricingConfig()
    with pytest.raises(ValueError, match="days must"):
        get_stats(metrics_db, config, days)


def test_stats_rejects_non_integer_timezone_offset(metrics_db):
    config = PricingConfig()
    with pytest.raises(ValueError, match="tz_offset_minutes"):
        get_stats(metrics_db, config, 7, "x")


@pytest.fixture
def breakdown_db():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(database_module._METRICS_DDL[0])
    rows = [
        ("b1", "balanced", "review", "t2", "failed"),
        ("b2", "balanced", "implement", "t1", "succeeded"),
        ("b3", "balanced", "implement", "t1", "succeeded"),
        ("b4", "balanced", "implement", "t1", "failed"),
        ("a1", "alpha", "review", "t1", "succeeded"),
        ("u1", "", "implement", "", "succeeded"),
    ]
    connection.executemany(
        "INSERT INTO job_metrics(job_id, finished_at, profile, workflow, target, backend, model, state) "
        "VALUES (?, '2026-01-02T00:30:00+00:00', ?, ?, ?, 'claude', 'm', ?)",
        rows,
    )
    connection.execute(
        "INSERT INTO job_metrics(job_id, finished_at, profile, workflow, target, backend, model, state) "
        "VALUES ('old', '2025-01-01T00:00:00+00:00', 'alpha', 'review', 't1', 'claude', 'm', 'succeeded')"
    )
    yield SimpleNamespace(_connection=connection)
    connection.close()


def test_breakdown_counts_rows_sorted_with_unknown_fallbacks(breakdown_db):
    result = get_stats(breakdown_db, PricingConfig(), 7, 0, now=datetime(2026, 1, 3, tzinfo=timezone.utc))
    assert result["work_delegated"]["breakdown"] == [
        {"profile": "alpha", "workflow": "review", "target": "t1", "state": "succeeded", "jobs": 1},
        {"profile": "balanced", "workflow": "implement", "target": "t1", "state": "failed", "jobs": 1},
        {"profile": "balanced", "workflow": "implement", "target": "t1", "state": "succeeded", "jobs": 2},
        {"profile": "balanced", "workflow": "review", "target": "t2", "state": "failed", "jobs": 1},
        {"profile": "unknown", "workflow": "implement", "target": "unknown", "state": "succeeded", "jobs": 1},
    ]


def test_breakdown_leaves_by_workflow_and_by_state_unchanged(breakdown_db):
    work = get_stats(breakdown_db, PricingConfig(), 7, 0, now=datetime(2026, 1, 3, tzinfo=timezone.utc))["work_delegated"]
    assert work["by_workflow"] == {
        "implement": {"failed": 1, "succeeded": 3},
        "review": {"failed": 1, "succeeded": 1},
    }
    assert work["by_state"] == {"failed": 2, "succeeded": 4}


def test_breakdown_is_empty_without_jobs_in_window(breakdown_db):
    result = get_stats(breakdown_db, PricingConfig(), 1, 0, now=datetime(2026, 3, 1, tzinfo=timezone.utc))
    assert result["work_delegated"]["breakdown"] == []
