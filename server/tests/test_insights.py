from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import sqlite3

import pytest

from refract.api.http.insights import get_stats
from refract.store.schema import DDL


_METRIC_COLUMNS = (
    "job_id", "finished_at", "workflow", "target", "backend", "model", "state", "failure_kind", "duration_ms",
    "tok_input", "tok_output", "tok_cache_read", "tok_cache_write", "attempts", "skipped_targets", "retry_of",
)


def _connect():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(DDL)
    connection.execute("INSERT INTO projects(id, root, created_at) VALUES ('p', '/p', 'now')")
    return connection


def _add_job(connection, row, profile=""):
    """Insert one terminal job and its attempt rows; totals sit on the last attempt, as the runtime reports them."""
    r = dict(zip(_METRIC_COLUMNS, row))
    connection.execute(
        "INSERT INTO jobs(id, project_id, workflow, profile, session, from_job, state, failure_kind, plan_json,"
        " created_at, finished_at, updated_at) VALUES (?, 'p', ?, ?, 's', ?, ?, ?, '{}', ?, ?, ?)",
        (r["job_id"], r["workflow"], profile, r["retry_of"], r["state"], r["failure_kind"], r["finished_at"],
         r["finished_at"], r["finished_at"]),
    )
    count = r["attempts"] if r["attempts"] is not None else 0
    for seq in range(1, count + 1):
        last = seq == count
        reason = "fallback" if last and r["skipped_targets"] else "initial" if seq == 1 else "retry"
        totals = last and (r["duration_ms"], r["tok_input"], r["tok_output"], r["tok_cache_read"], r["tok_cache_write"])
        connection.execute(
            "INSERT INTO attempts(job_id, seq, reason, target, backend, model, state, started_at, duration_ms,"
            " tok_input, tok_output, tok_cache_read, tok_cache_write) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r["job_id"], seq, reason, r["target"], r["backend"], r["model"],
             r["state"] if last else "failed", r["finished_at"], *(totals or (None,) * 5)),
        )


def _add_jobs(connection, rows):
    for row in rows:
        _add_job(connection, row)


@pytest.fixture
def metrics_db():
    connection = _connect()
    rows = [
        ("bad", "2026-01-01T23:30:00+00:00", "implement", "a", "claude", "priced", "failed", None, 3600000, 100, 20, 0, 0, 1, 0, ""),
        ("ok", "2026-01-02T00:30:00+00:00", "implement", "a", "codex", "priced", "succeeded", None, 1800000, 100, 10, 40, 5, 2, 1, "bad"),
        ("other", "2026-01-02T00:30:00+00:00", "review", "", "pi", "unpriced", "succeeded", None, 600000, 50, 5, 10, 0, None, None, ""),
    ]
    _add_jobs(connection, rows)
    yield SimpleNamespace(_connection=connection)
    connection.close()


def test_stats_aggregates_work_failover_tokens_and_normalizes_codex(metrics_db):
    result = get_stats(metrics_db, 7, 0, now=datetime(2026, 1, 3, tzinfo=timezone.utc))
    work = result["work_delegated"]
    assert work["by_workflow"] == {"implement": {"failed": 1, "succeeded": 1}, "review": {"succeeded": 1}}
    assert work["by_state"] == {"failed": 1, "succeeded": 2}
    assert work["worker_hours"] == pytest.approx(1.5)  # the job without attempt rows carries no duration
    assert work["success_rate"] == pytest.approx(2 / 3)
    assert result["failover_saves"] == {
        "skipped_targets": 1, "retries": 1,
        "unknown_skipped_targets": 1, "unknown_attempts": 1,
        "attempts_by_reason": {"fallback": 1, "initial": 2},
    }
    codex = result["tokens"]["by_backend"]["codex"]
    assert (codex["uncached_input"], codex["cache_read"], codex["cache_hit_ratio"]) == (60, 40, .4)
    assert "unassigned" in result["tokens"]["by_target"]
    assert "estimated_cost" not in result
    assert "currency" not in result


def test_stats_normalizes_backend_input_with_cache_components(metrics_db):
    _add_jobs(
        metrics_db._connection,
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
        metrics_db, 7, 0,
        now=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    by_backend = result["tokens"]["by_backend"]
    assert (by_backend["claude"]["input"], by_backend["claude"]["uncached_input"]) == (250, 200)
    assert (by_backend["pi"]["input"], by_backend["pi"]["uncached_input"]) == (105, 90)  # the job without attempts adds none
    assert (by_backend["agy"]["input"], by_backend["agy"]["uncached_input"]) == (50, 50)
    assert (by_backend["codex"]["input"], by_backend["codex"]["uncached_input"]) == (100, 60)


def test_stats_timezone_offsets_produce_exact_daily_buckets(metrics_db):
    now = datetime(2026, 1, 3, tzinfo=timezone.utc)
    utc = get_stats(metrics_db, 7, 0, now=now)["work_delegated"]["daily"]
    ahead = get_stats(metrics_db, 7, 120, now=now)["work_delegated"]["daily"]
    behind = get_stats(metrics_db, 7, -60, now=now)["work_delegated"]["daily"]
    assert utc == {"2026-01-01": {"succeeded": 0, "failed": 1},
                   "2026-01-02": {"succeeded": 2, "failed": 0}}
    assert ahead == {"2026-01-02": {"succeeded": 2, "failed": 1}}
    assert behind == {"2026-01-01": {"succeeded": 2, "failed": 1}}


def test_retry_after_failed_job_outside_window_counts_as_failover_save(metrics_db):
    metrics_db._connection.execute("DELETE FROM jobs")
    _add_job(
        metrics_db._connection,
        ("old-failure", "2025-12-30T00:00:00+00:00", "implement", "a", "codex",
         "priced", "failed", None, 0, 0, 0, 0, 0, 1, 0, ""),
    )
    _add_job(
        metrics_db._connection,
        ("recent-retry", "2026-01-02T00:00:00+00:00", "implement", "a", "codex",
         "priced", "succeeded", None, 0, 0, 0, 0, 0, 1, 0, "old-failure"),
    )
    result = get_stats(
        metrics_db, 1,
        now=datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
    )
    assert "retries_after_failure" not in result["failover_saves"]
    assert result["failover_saves"]["attempts_by_reason"] == {"initial": 1}


def test_stats_rejects_timezone_offset_outside_supported_range(metrics_db):
    with pytest.raises(ValueError, match="tz_offset_minutes must be an integer between -1440 and 1440"):
        get_stats(metrics_db, 7, 999999999999)


def test_stats_window_includes_just_inside_and_excludes_just_outside(metrics_db):
    now = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
    _add_jobs(
        metrics_db._connection,
        [
            ("inside", (now - timedelta(days=7) + timedelta(microseconds=1)).isoformat(),
             "workflow", "t", "codex", "model", "succeeded", None, 0, 0, 0, 0, 0, 1, 0, ""),
            ("outside", (now - timedelta(days=7) - timedelta(microseconds=1)).isoformat(),
             "workflow", "t", "codex", "model", "succeeded", None, 0, 0, 0, 0, 0, 1, 0, ""),
        ],
    )
    result = get_stats(metrics_db, 7, now=now)
    assert result["work_delegated"]["by_state"]["succeeded"] == 1


def test_stats_zero_success_and_failure_count_has_zero_success_rate(metrics_db):
    metrics_db._connection.execute("DELETE FROM jobs")
    _add_jobs(
        metrics_db._connection,
        [(name, "2026-01-02T00:00:00+00:00", "workflow", "t", "codex", "model",
          state, None, 0, 0, 0, 0, 0, 1, 0, "")
         for name, state in (("cancelled", "cancelled"), ("interrupted", "interrupted"))],
    )
    result = get_stats(
        metrics_db, 7,
        now=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    assert result["work_delegated"]["success_rate"] == 0.0
    assert result["work_delegated"]["daily"] == {}


def _insert_models(metrics_db, *models):
    metrics_db._connection.execute("DELETE FROM jobs")
    _add_jobs(
        metrics_db._connection,
        [(f"job-{index}", "2026-01-02T00:30:00+00:00", "workflow", "a", "codex", model,
          "succeeded", None, 0, 100, 10, 0, 0, 1, 0, "")
         for index, model in enumerate(models)],
    )


def test_stats_merges_provider_prefixed_models_in_tokens(metrics_db):
    _insert_models(metrics_db, "gpt-6-luna", "openai-codex/gpt-6-luna")
    result = get_stats(metrics_db, 7, now=datetime(2026, 1, 3, tzinfo=timezone.utc))
    by_model = result["tokens"]["by_model"]
    assert list(by_model) == ["gpt-6-luna"]
    assert (by_model["gpt-6-luna"]["input"], by_model["gpt-6-luna"]["jobs"]) == (200, 2)


def test_stats_labels_empty_backend_and_model_as_unassigned(metrics_db):
    _add_job(
        metrics_db._connection,
        ("unassigned", "2026-01-02T00:30:00+00:00", "workflow", "", "", "",
         "succeeded", None, 0, 100, 0, 0, 0, 1, 0, ""),
    )
    result = get_stats(
        metrics_db, 7, now=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )
    # the fixture job without attempt rows is unassigned too
    assert result["tokens"]["by_backend"]["unassigned"]["jobs"] == 2
    assert result["tokens"]["by_model"]["unassigned"]["jobs"] == 2


@pytest.mark.parametrize("days", [2, 0, 366])
def test_stats_rejects_unsupported_days(metrics_db, days):
    with pytest.raises(ValueError, match="days must"):
        get_stats(metrics_db, days)


def test_stats_rejects_non_integer_timezone_offset(metrics_db):
    with pytest.raises(ValueError, match="tz_offset_minutes"):
        get_stats(metrics_db, 7, "x")


@pytest.fixture
def breakdown_db():
    connection = _connect()
    rows = [
        ("b1", "balanced", "review", "t2", "failed"),
        ("b2", "balanced", "implement", "t1", "succeeded"),
        ("b3", "balanced", "implement", "t1", "succeeded"),
        ("b4", "balanced", "implement", "t1", "failed"),
        ("a1", "alpha", "review", "t1", "succeeded"),
        ("u1", "", "implement", "", "succeeded"),
    ]
    for job_id, profile, workflow, target, state in rows:
        _add_job(connection, (job_id, "2026-01-02T00:30:00+00:00", workflow, target, "claude", "m", state,
                              None, None, None, None, None, None, 1, 0, ""), profile)
    _add_job(connection, ("old", "2025-01-01T00:00:00+00:00", "review", "t1", "claude", "m", "succeeded",
                          None, None, None, None, None, None, 1, 0, ""), "alpha")
    yield SimpleNamespace(_connection=connection)
    connection.close()


def test_breakdown_counts_rows_sorted_with_unknown_fallbacks(breakdown_db):
    result = get_stats(breakdown_db, 7, 0, now=datetime(2026, 1, 3, tzinfo=timezone.utc))
    assert result["work_delegated"]["breakdown"] == [
        {"profile": "alpha", "workflow": "review", "target": "t1", "state": "succeeded", "jobs": 1},
        {"profile": "balanced", "workflow": "implement", "target": "t1", "state": "failed", "jobs": 1},
        {"profile": "balanced", "workflow": "implement", "target": "t1", "state": "succeeded", "jobs": 2},
        {"profile": "balanced", "workflow": "review", "target": "t2", "state": "failed", "jobs": 1},
        {"profile": "unknown", "workflow": "implement", "target": "unknown", "state": "succeeded", "jobs": 1},
    ]


def test_breakdown_leaves_by_workflow_and_by_state_unchanged(breakdown_db):
    work = get_stats(breakdown_db, 7, 0, now=datetime(2026, 1, 3, tzinfo=timezone.utc))["work_delegated"]
    assert work["by_workflow"] == {
        "implement": {"failed": 1, "succeeded": 3},
        "review": {"failed": 1, "succeeded": 1},
    }
    assert work["by_state"] == {"failed": 2, "succeeded": 4}


def test_breakdown_is_empty_without_jobs_in_window(breakdown_db):
    result = get_stats(breakdown_db, 1, 0, now=datetime(2026, 3, 1, tzinfo=timezone.utc))
    assert result["work_delegated"]["breakdown"] == []
