"""Job writes: compare-and-set terminal transitions, one-transaction finish, sessions, health, cursor reads."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from refract.store import attempts, health, jobs, schema, sessions, transcripts
from refract.store.pool import Pool


@pytest.fixture
def pool(tmp_path):
    path = tmp_path / "refract.db"
    schema.initialize(path)
    pool = Pool(path)
    with pool.transaction() as conn:
        jobs.upsert_project(conn, "p", "/p")
    yield pool
    pool.close()


def make_job(conn, job_id="j", **extra):
    jobs.create(conn, job_id=job_id, project_id="p", workflow="consult", profile="prof",
                prompt="hello", plan_json="{}", session="s", **extra)


def test_create_start_and_finish_succeeds_once(pool):
    conn = pool.connection
    make_job(conn)
    assert jobs.record(conn, "j")["state"] == "queued"
    assert jobs.start(conn, "j") is True
    assert jobs.start(conn, "j") is False
    assert jobs.finish(conn, "j", "succeeded", result="done", target="t1") is True
    row = jobs.record(conn, "j")
    assert (row["state"], row["result"], row["target"]) == ("succeeded", "done", "t1")
    assert row["finished_at"]


def test_terminal_write_on_terminal_job_changes_nothing_and_reports_loss(pool):
    conn = pool.connection
    make_job(conn)
    jobs.start(conn, "j")
    assert jobs.finish(conn, "j", "cancelled", error="stop") is True
    before = jobs.record(conn, "j")
    assert jobs.finish(conn, "j", "succeeded", result="late", target="t1", model="m", duration_ms=5) is False
    assert jobs.record(conn, "j") == before
    assert attempts.for_job(conn, "j") == []


def test_finish_unknown_job_reports_loss(pool):
    assert jobs.finish(pool.connection, "missing", "failed") is False


def test_finish_writes_state_result_and_final_attempt_in_one_transaction(pool):
    conn = pool.connection
    make_job(conn)
    jobs.start(conn, "j")
    conn.execute("""CREATE TRIGGER reject_attempt BEFORE INSERT ON attempts
                    BEGIN SELECT RAISE(ABORT, 'attempt rejected'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="attempt rejected"):
        jobs.finish(conn, "j", "succeeded", result="done", target="t1")
    row = jobs.record(conn, "j")
    assert (row["state"], row["result"]) == ("running", None)


def test_finish_records_attempt_with_derived_job_fields(pool):
    conn = pool.connection
    make_job(conn)
    jobs.start(conn, "j")
    tokens = {"input": 10, "output": 4, "context_used": 7}
    jobs.finish(conn, "j", "succeeded", result="r", target="t1", model="m1", duration_ms=120, tokens=tokens)
    [attempt] = attempts.for_job(conn, "j")
    assert (attempt["seq"], attempt["reason"], attempt["state"], attempt["target"]) == (1, "initial", "succeeded", "t1")
    row = jobs.record(conn, "j")
    assert (row["model"], row["duration_ms"], row["tok_input"], row["tok_output"], row["tok_context_used"]) == ("m1", 120, 10, 4, 7)
    assert row["tok_cache_read"] is None


def test_finish_with_attempt_count_adds_retry_rows(pool):
    conn = pool.connection
    make_job(conn)
    jobs.start(conn, "j")
    attempts.begin(conn, "j", "t1")
    jobs.finish(conn, "j", "succeeded", target="t1", attempts=3, duration_ms=9, tokens={"input": 1})
    rows = attempts.for_job(conn, "j")
    assert [(row["seq"], row["reason"]) for row in rows] == [(1, "initial"), (2, "retry"), (3, "retry")]
    assert [row["state"] for row in rows] == ["failed", "failed", "succeeded"]
    assert jobs.record(conn, "j")["duration_ms"] == 9
    assert attempts.counts_by_reason(conn, "0000") == {"initial": 1, "retry": 2}


def test_new_target_after_open_attempt_is_a_fallback(pool):
    conn = pool.connection
    make_job(conn)
    jobs.start(conn, "j")
    attempts.begin(conn, "j", "t1")
    attempts.begin(conn, "j", "t1")
    attempts.begin(conn, "j", "t2")
    rows = attempts.for_job(conn, "j")
    assert [(row["target"], row["reason"], row["state"]) for row in rows] == [
        ("t1", "initial", "failed"), ("t2", "fallback", "running")]


def test_finish_without_attempt_data_adds_no_attempt(pool):
    conn = pool.connection
    make_job(conn)
    jobs.finish(conn, "j", "cancelled", error="before execution")
    assert attempts.for_job(conn, "j") == []
    assert jobs.record(conn, "j")["target"] == ""


def test_interrupt_running_marks_only_running_jobs(pool):
    conn = pool.connection
    for name in ("queued", "running", "done"):
        make_job(conn, name)
    jobs.start(conn, "running")
    jobs.start(conn, "done")
    jobs.finish(conn, "done", "succeeded")
    attempts.begin(conn, "running", "t1")
    rows = jobs.interrupt_running(conn)
    assert [row["id"] for row in rows] == ["running"]
    assert jobs.record(conn, "running")["state"] == "interrupted"
    assert jobs.record(conn, "queued")["state"] == "queued"
    assert jobs.record(conn, "done")["state"] == "succeeded"
    assert attempts.for_job(conn, "running")[0]["state"] == "interrupted"


def test_two_tier_retention_prunes_content_then_rows(pool, tmp_path):
    conn = pool.connection
    store = transcripts.Transcripts(tmp_path / "streams", tmp_path / "results")
    for name in ("recent", "stale", "ancient"):
        make_job(conn, name)
        jobs.finish(conn, name, "succeeded", result="text", target="t")
        store.append(conn, name, [{"kind": "x"}])
        store.write_result(name, "text")
    conn.execute("UPDATE jobs SET updated_at='2000-01-01' WHERE id='ancient'")
    conn.execute("UPDATE jobs SET updated_at='2026-01-01' WHERE id='stale'")
    conn.commit()
    pruned = jobs.prune(conn, content_before="2026-06-01", rows_before="2025-01-01", remove=store.remove)
    assert pruned.content == ["stale"]
    assert pruned.rows == ["ancient"]
    stale = jobs.record(conn, "stale")
    assert (stale["prompt"], stale["result"], stale["content_pruned"]) == (None, None, 1)
    assert jobs.record(conn, "ancient") is None
    assert attempts.for_job(conn, "ancient") == []
    assert jobs.record(conn, "recent")["prompt"] == "hello"
    assert not store.stream_path("stale").exists() and not store.result_path("stale").exists()
    assert store.stream_path("recent").exists()


def test_session_routes_and_backend_sessions(pool):
    conn = pool.connection
    assert sessions.sticky_target(conn, "p", "s", "consult") == ""
    sessions.set_sticky_target(conn, "p", "s", "consult", "t1")
    assert sessions.sticky_target(conn, "p", "s", "consult") == "t1"
    sessions.store_backend_session(conn, "p", "s", "consult", "k1", "b1")
    sessions.store_backend_session(conn, "p", "s", "consult", "k2", "b2")
    assert sessions.backend_session(conn, "p", "s", "consult", "k1") == "b1"
    sessions.store_backend_session(conn, "p", "s", "consult", "k3", "b3", clear=True)
    assert sessions.backend_session(conn, "p", "s", "consult", "k1") == ""
    assert sessions.backend_session(conn, "p", "s", "consult", "k3") == "b3"


def test_target_health_probe_claim_and_cooldown_cap(pool):
    conn = pool.connection
    assert health.get(conn, "t")["consecutive_failures"] == 0
    assert health.record_failure(conn, "t", immediate=True, base_cooldown_s=60) == 1
    assert health.claim_probe(conn, "t", "j1", "0000") is False
    open_until = health.get(conn, "t")["circuit_open_until"]
    assert health.claim_probe(conn, "t", "j1", open_until) is True
    assert health.claim_probe(conn, "t", "j2", open_until) is False
    health.release_probe(conn, "t", "j1")
    for _ in range(6):
        health.record_failure(conn, "t", failed_probe=True, base_cooldown_s=60, max_cooldown_s=900)
    assert health.get(conn, "t")["cooldown_s"] == 900
    health.record_success(conn, "t")
    assert health.get(conn, "t")["consecutive_failures"] == 0


def test_health_writes_clear_only_their_own_probe(pool):
    conn = pool.connection
    health.record_failure(conn, "t", immediate=True, circuit_open_until="2000-01-01T00:00:00+00:00")
    assert health.claim_probe(conn, "t", "b", "2999")
    before = health.get(conn, "t")
    assert (before["consecutive_failures"], before["cooldown_s"]) == (1, 60)
    health.record_failure(conn, "t", job_id="a", failed_probe=True)
    after = health.get(conn, "t")
    assert after["probe_job_id"] == "b"
    # A non-owner write still counts the failure and doubles the cooldown; it only keeps the probe.
    assert (after["consecutive_failures"], after["cooldown_s"]) == (2, 120)
    assert after["circuit_open_until"] != ""
    health.record_success(conn, "t", job_id="a")
    assert health.get(conn, "t")["probe_job_id"] == "b"
    health.record_failure(conn, "t", job_id="b", failed_probe=True)
    assert health.get(conn, "t")["probe_job_id"] == ""
    conn.execute("UPDATE target_health SET probe_job_id='b' WHERE target_id='t'")
    health.record_success(conn, "t", job_id="b")
    assert health.get(conn, "t")["probe_job_id"] == ""
    conn.execute("UPDATE target_health SET probe_job_id='b' WHERE target_id='t'")
    health.record_failure(conn, "t")
    assert health.get(conn, "t")["probe_job_id"] == ""


def test_transcript_reads_stop_at_events_committed(pool, tmp_path):
    conn = pool.connection
    make_job(conn)
    store = transcripts.Transcripts(tmp_path / "streams", tmp_path / "results")
    store.append(conn, "j", [{"n": 1}, {"n": 2}])
    store.append(conn, "j", [{"n": 3}])
    assert jobs.record(conn, "j")["events_committed"] == 3
    with open(store.stream_path("j"), "a", encoding="utf-8") as handle:
        handle.write('{"n": 4}\n')
    events, last, more = store.read(conn, "j", after=0, limit=10)
    assert [event["n"] for event in events] == [1, 2, 3]
    assert (last, more) == (3, False)
    events, last, more = store.read(conn, "j", after=1, limit=1)
    assert ([event["n"] for event in events], last, more) == ([2], 2, True)
    assert store.read(conn, "nope", after=0, limit=10) == ([], 0, False)


def test_transcript_append_overwrites_uncommitted_tail_after_a_crash(pool, tmp_path):
    conn = pool.connection
    make_job(conn)
    store = transcripts.Transcripts(tmp_path / "streams", tmp_path / "results")
    store.append(conn, "j", [{"n": 1}])
    with open(store.stream_path("j"), "a", encoding="utf-8") as handle:
        handle.write('{"n": "orphan"}\n{"par')
    fresh = transcripts.Transcripts(tmp_path / "streams", tmp_path / "results")
    fresh.append(conn, "j", [{"n": 2}])
    events, last, _more = fresh.read(conn, "j", after=0, limit=10)
    assert [event["n"] for event in events] == [1, 2]
    assert last == 2


def _expire(conn, *names):
    for name in names:
        make_job(conn, name)
        jobs.finish(conn, name, "succeeded", result="text", target="t")
    conn.execute("UPDATE jobs SET updated_at='2026-01-01'")
    conn.commit()


def test_failed_file_removal_keeps_content_and_the_next_sweep_retries(pool, tmp_path):
    conn = pool.connection
    store = transcripts.Transcripts(tmp_path / "streams", tmp_path / "results")
    _expire(conn, "stale")
    store.write_result("stale", "text")
    failing = True

    def remove(job_id):
        if failing:
            raise PermissionError("busy")
        store.remove(job_id)

    pruned = jobs.prune(conn, content_before="2026-06-01", rows_before="2025-01-01", remove=remove)
    assert pruned.content == []
    row = jobs.record(conn, "stale")
    assert (row["content_pruned"], row["prompt"], row["result"]) == (0, "hello", "text")
    assert store.result_path("stale").exists()
    failing = False
    pruned = jobs.prune(conn, content_before="2026-06-01", rows_before="2025-01-01", remove=remove)
    assert pruned.content == ["stale"]
    assert jobs.record(conn, "stale")["content_pruned"] == 1
    assert not store.result_path("stale").exists()


def test_row_retention_keeps_the_row_when_its_files_cannot_be_removed(pool):
    conn = pool.connection
    _expire(conn, "ancient")

    def remove(job_id):
        raise PermissionError("busy")

    pruned = jobs.prune(conn, content_before="2026-06-01", rows_before="2027-01-01", remove=remove)
    assert pruned.rows == [] and jobs.record(conn, "ancient") is not None
    pruned = jobs.prune(conn, content_before="2026-06-01", rows_before="2027-01-01", remove=lambda job_id: None)
    assert pruned.rows == ["ancient"] and jobs.record(conn, "ancient") is None


def test_pruned_job_never_returns_a_leftover_result_file(tmp_path):
    from refract.store.database import Database

    database = Database(tmp_path / "refract.db")
    try:
        database.upsert_project(project_id="p", root="/p")
        database.create_job(job_id="j", project_id="p", workflow="consult", profile="prof", prompt="hello",
                            plan_json="{}", session="s")
        database.start_job("j")
        database.finish_job("j", "succeeded", text="secret", target="t")
        database.prune_retention(content_before="9999-01-01", rows_before="0000-01-01")
        database.result_path("j").write_text("leftover", encoding="utf-8")
        assert database.job("j").result.text == ""
        assert database.job_detail("j")["result"]["text"] == ""
    finally:
        database.close()
