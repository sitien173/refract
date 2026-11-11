from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest

from refract.database import Database
from tests.test_storage_v3 import _schema_18, _schema_19, _user_version


def table_columns(database: Database, table: str) -> set[str]:
    return {
        row["name"]
        for row in database._connection.execute("SELECT name FROM pragma_table_info(?)", (table,))
    }


# Schema 20 as shipped at 49bc8621: job_metrics without profile.
SCHEMA_20_METRICS_DDL = (
    """CREATE TABLE job_metrics (
    job_id TEXT PRIMARY KEY,
    finished_at TEXT NOT NULL,
    workflow TEXT NOT NULL,
    target TEXT NOT NULL,
    backend TEXT NOT NULL,
    model TEXT NOT NULL,
    state TEXT NOT NULL,
    failure_kind TEXT,
    duration_ms INTEGER,
    tok_input INTEGER,
    tok_output INTEGER,
    tok_cache_read INTEGER,
    tok_cache_write INTEGER,
    attempts INTEGER,
    skipped_targets INTEGER,
    retry_of TEXT NOT NULL DEFAULT ''
)""",
    "CREATE INDEX job_metrics_finished_idx ON job_metrics(finished_at)",
    """CREATE TABLE telemetry_outbox (
    id INTEGER PRIMARY KEY,
    event_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    send_attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL
)""",
)


def _schema_20(path) -> str:
    """Create a schema 20 database: a retained job, its metrics row, and a metrics row whose job was pruned."""
    job_id = _schema_19(path)
    with closing(sqlite3.connect(path)) as connection:
        for statement in SCHEMA_20_METRICS_DDL:
            connection.execute(statement)
        for metric_id in (job_id, "pruned-job"):
            connection.execute(
                "INSERT INTO job_metrics(job_id, finished_at, workflow, target, backend, model, state) "
                "VALUES (?, 't2', 'implement', 'target-a', 'codex', 'm', 'succeeded')",
                (metric_id,),
            )
        connection.execute("PRAGMA user_version=20")
        connection.commit()
    return job_id


def _profiles(path) -> dict[str, str]:
    with closing(sqlite3.connect(path)) as connection:
        return dict(connection.execute("SELECT job_id, profile FROM job_metrics").fetchall())


@pytest.mark.parametrize("failure", ["connection", "schema"])
def test_initialization_failure_closes_connection(tmp_path, monkeypatch, failure) -> None:
    real_connect = sqlite3.connect
    opened = []

    class FailingConnection(sqlite3.Connection):
        def execute(self, statement, *args, **kwargs):
            if failure == "connection" and statement == "PRAGMA foreign_keys=ON":
                raise sqlite3.OperationalError("connection setup failed")
            return super().execute(statement, *args, **kwargs)

    def track_connection(*args, **kwargs):
        connection = real_connect(*args, factory=FailingConnection, **kwargs)
        opened.append(connection)
        return connection

    def fail_schema(self):
        self._connection.execute("SELECT 1")
        raise sqlite3.OperationalError("schema setup failed")

    monkeypatch.setattr(sqlite3, "connect", track_connection)
    if failure == "schema":
        monkeypatch.setattr(Database, "_create_schema", fail_schema)
    with pytest.raises(sqlite3.OperationalError, match="setup failed"):
        Database(tmp_path / "refract.db")

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


def test_create_job_persists_fresh_flag(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="proj", root="/proj")
    database.create_job(
        job_id="standard-job",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="question",
        execution_plan_json="{}",
        session="consult",
    )
    database.create_job(
        job_id="fresh-job",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="question",
        execution_plan_json="{}",
        session="consult",
        fresh=True,
    )
    standard_record = database.job_record("standard-job")
    fresh_record = database.job_record("fresh-job")
    assert standard_record
    assert standard_record["fresh"] == 0
    assert fresh_record
    assert fresh_record["fresh"] == 1
    database.close()


def test_jobs_load_with_one_query(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(
        project_id="project", root="/project"
    )
    for job_id in ("first", "second"):
        database.create_job(
            job_id=job_id,
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt=job_id,
            execution_plan_json="{}",
            session="consult",
        )
    statements: list[str] = []
    database._connection.set_trace_callback(statements.append)

    jobs = database.jobs(project.id)

    database._connection.set_trace_callback(None)
    assert {job.id for job in jobs} == {"first", "second"}
    assert len([statement for statement in statements if statement.startswith("SELECT")]) == 1
    database.close()


def test_job_overview_bounds_terminal_jobs_and_uses_project_index(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", root="/project")
    for index in range(14):
        job_id = f"job-{index:02d}"
        database.create_job(
            job_id=job_id, project_id=project.id, workflow="consult", profile="balanced",
            prompt=job_id, execution_plan_json="{}", session="consult",
        )
        if index >= 2:
            database.finish_job(job_id, "succeeded")

    active, recent, more_recent = database.job_overview(project.id, recent_limit=10)

    assert {record["id"] for record in active} == {"job-00", "job-01"}
    assert [record["id"] for record in recent] == [f"job-{index:02d}" for index in range(13, 3, -1)]
    assert more_recent == 2
    plan = database._connection.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM jobs WHERE project_id=? ORDER BY updated_at DESC", ("project",)
    ).fetchall()
    assert any("jobs_project_idx" in row["detail"] for row in plan)
    database.close()


def test_fresh_success_clears_multiple_stale_sessions_and_preserves_unrelated(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", root="/project")
    database.create_job(
        job_id="job", project_id=project.id, workflow="implement", profile="balanced",
        prompt="p", execution_plan_json="{}", session="stream-1",
    )
    database.start_job("job")

    database.store_session(
        project_id=project.id, session="stream-1", workflow="implement",
        target_key="primary-key", backend_session_id="stale-sess-1",
    )
    database.store_session(
        project_id=project.id, session="stream-1", workflow="implement",
        target_key="secondary-key", backend_session_id="stale-sess-2",
    )
    database.store_session(
        project_id=project.id, session="stream-2", workflow="review",
        target_key="primary-key", backend_session_id="unrelated-sess",
    )

    assert database.session(project.id, "stream-1", "implement", "primary-key") == "stale-sess-1"
    assert database.session(project.id, "stream-1", "implement", "secondary-key") == "stale-sess-2"
    assert database.session(project.id, "stream-2", "review", "primary-key") == "unrelated-sess"

    database.finish_fresh_job_success(
        job_id="job",
        project_id=project.id,
        session="stream-1",
        workflow="implement",
        target="primary",
        target_key="primary-key",
        backend_session_id="replacement-sess",
        text="done",
    )

    assert database.session(project.id, "stream-1", "implement", "primary-key") == "replacement-sess"
    assert database.session(project.id, "stream-1", "implement", "secondary-key") == ""

    rows = database._connection.execute(
        "SELECT target_key, backend_session_id FROM target_sessions WHERE project_id=? AND session=? AND workflow=?",
        (project.id, "stream-1", "implement"),
    ).fetchall()
    assert [tuple(row) for row in rows] == [("primary-key", "replacement-sess")]

    assert database.session(project.id, "stream-2", "review", "primary-key") == "unrelated-sess"
    metric = database._connection.execute("SELECT state, backend, attempts FROM job_metrics WHERE job_id='job'").fetchone()
    assert tuple(metric) == ("succeeded", "", None)
    database.close()



def test_two_terminal_writes_replace_one_metrics_row(tmp_path):
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", root="/project")
    database.create_job(
        job_id="terminal", project_id=project.id, workflow="implement", profile="balanced",
        prompt="p", execution_plan_json='{"targets":[{"id":"target","backend":"codex"}]}', session="s",
    )

    database.finish_job("terminal", "failed", target="target", model="first", error="old")
    database.finish_job("terminal", "succeeded", target="target", model="second", tokens={"input": 7})

    rows = database._connection.execute("SELECT * FROM job_metrics WHERE job_id='terminal'").fetchall()
    assert len(rows) == 1
    assert (rows[0]["state"], rows[0]["model"], rows[0]["backend"], rows[0]["tok_input"]) == (
        "succeeded", "second", "codex", 7,
    )
    database.close()


def test_fresh_success_writes_complete_metrics_row(tmp_path):
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", root="/project")
    database.create_job(
        job_id="fresh-metrics", project_id=project.id, workflow="implement", profile="balanced",
        prompt="p", execution_plan_json='{"targets":[{"id":"target","backend":"claude"}]}',
        session="s", fresh=True,
    )

    database.finish_fresh_job_success(
        job_id="fresh-metrics", project_id=project.id, session="s", workflow="implement",
        target="target", target_key="target-key", backend_session_id="backend-session",
        text="done", model="model-x", tokens={"input": 11, "output": 3},
    )

    row = database._connection.execute("SELECT * FROM job_metrics WHERE job_id='fresh-metrics'").fetchone()
    assert row is not None
    assert (row["state"], row["target"], row["backend"], row["model"], row["tok_input"], row["tok_output"]) == (
        "succeeded", "target", "claude", "model-x", 11, 3,
    )
    database.close()


def test_empty_or_malformed_execution_plan_writes_unassigned_backend(tmp_path):
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", root="/project")
    for job_id, plan in (("empty-plan", "{}"), ("malformed-plan", "not json")):
        database.create_job(
            job_id=job_id, project_id=project.id, workflow="implement", profile="balanced",
            prompt="p", execution_plan_json=plan, session=job_id,
        )
        database.finish_job(job_id, "failed", target="target")
        row = database._connection.execute(
            "SELECT state, backend FROM job_metrics WHERE job_id=?", (job_id,),
        ).fetchone()
        assert tuple(row) == ("failed", "")
    database.close()


def test_non_string_backend_in_plan_still_persists_terminal_job_with_empty_backend(tmp_path):
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", root="/project")
    database.create_job(
        job_id="bad-backend", project_id=project.id, workflow="implement", profile="balanced",
        prompt="p", execution_plan_json='{"targets":[{"id":"target","backend":{"bad":"value"}}]}',
        session="s",
    )
    database.start_job("bad-backend")

    database.finish_job("bad-backend", "failed", target="target")

    assert database.job_record("bad-backend")["state"] == "failed"
    row = database._connection.execute(
        "SELECT state, backend FROM job_metrics WHERE job_id='bad-backend'"
    ).fetchone()
    assert tuple(row) == ("failed", "")
    database.close()


def test_interrupt_active_jobs_writes_metrics_only_for_running_jobs(tmp_path):
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", root="/project")
    for job_id in ("running-a", "running-b", "queued"):
        database.create_job(
            job_id=job_id, project_id=project.id, workflow="implement", profile="balanced",
            prompt="p", execution_plan_json="{}", session=job_id,
        )
    database.start_job("running-a")
    database.start_job("running-b")

    interrupted = database.interrupt_active_jobs()

    assert {row["id"] for row in interrupted} == {"running-a", "running-b"}
    rows = database._connection.execute(
        "SELECT job_id, state, finished_at FROM job_metrics ORDER BY job_id"
    ).fetchall()
    assert {row["job_id"] for row in rows} == {"running-a", "running-b"}
    for row in rows:
        job = database.job_record(row["job_id"])
        assert row["state"] == "interrupted"
        assert row["finished_at"] == job["updated_at"]
    database.close()


def test_metrics_upsert_failure_rolls_back_terminal_job_update(tmp_path):
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", root="/project")
    database.create_job(
        job_id="rollback", project_id=project.id, workflow="implement", profile="balanced",
        prompt="p", execution_plan_json="{}", session="s",
    )
    database.start_job("rollback")
    database._connection.execute("DROP TABLE job_metrics")

    with pytest.raises(sqlite3.OperationalError, match="no such table: job_metrics"):
        database.finish_job("rollback", "failed")

    assert database.job_record("rollback")["state"] == "running"
    database.close()


def test_probe_claim_is_atomic_and_failure_cooldown_caps(tmp_path) -> None:
    path = tmp_path / "refract.db"
    db = Database(path)
    expired = "2000-01-01T00:00:00+00:00"
    with db._connection:
        db._connection.execute("INSERT INTO target_health(target_id,circuit_open_until,cooldown_s) VALUES ('t',?,60)", (expired,))
    db.close()

    def claim(job: int) -> bool:
        connection = Database(path)
        try:
            return connection.claim_target_probe("t", str(job), "2026-01-01T00:00:00+00:00")
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=20) as pool:
        claims = list(pool.map(claim, range(20)))
    assert sum(claims) == 1
    db = Database(path)
    assert db.target_health("t")["probe_job_id"] in {str(i) for i in range(20)}
    db.record_target_failure("t", threshold=3, base_cooldown_s=60, max_cooldown_s=100, failed_probe=True)
    assert db.target_health("t")["cooldown_s"] == 100
    db.record_target_success("t", base_cooldown_s=60)
    health = db.target_health("t")
    assert health["consecutive_failures"] == 0
    assert health["circuit_open_until"] == ""
    assert health["probe_job_id"] == ""
    assert health["cooldown_s"] == 60
    db.close()


def test_failure_threshold_and_immediate_open(tmp_path) -> None:
    db = Database(tmp_path / "refract.db")
    for _ in range(2):
        assert db.record_target_failure("retry", threshold=3, base_cooldown_s=60, max_cooldown_s=300) < 3
    assert db.target_health("retry")["circuit_open_until"] == ""
    db.record_target_failure("retry", threshold=3, base_cooldown_s=60, max_cooldown_s=300)
    assert db.target_health("retry")["circuit_open_until"]
    db.record_target_failure("fatal", threshold=3, base_cooldown_s=60, max_cooldown_s=300, immediate=True)
    assert db.target_health("fatal")["circuit_open_until"]
    db.close()


def test_cursor_roundtrip_and_validation() -> None:
    from refract.database import decode_cursor, encode_cursor

    cursor = encode_cursor("2026-11-05T10:00:00+00:00", "job-123")
    assert isinstance(cursor, str)
    created_at, job_id = decode_cursor(cursor)
    assert created_at == "2026-11-05T10:00:00+00:00"
    assert job_id == "job-123"

    with pytest.raises(ValueError, match="Invalid cursor"):
        decode_cursor("not-base64-json")

    with pytest.raises(ValueError, match="Invalid cursor"):
        decode_cursor("")


def test_job_summaries_reads_no_result_files(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="proj", root="/proj")
    db.create_job(
        job_id="job-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        session="sess",
    )

    def explode(*args, **kwargs):
        raise RuntimeError("result_path read! List query must not read result files.")

    monkeypatch.setattr(Database, "result_path", explode)
    monkeypatch.setattr(Path, "read_text", explode)

    summaries, next_cursor = db.job_summaries()
    assert len(summaries) == 1
    assert summaries[0]["id"] == "job-1"
    assert summaries[0]["project_root"] == "/proj"
    assert next_cursor is None
    db.close()


def test_job_summaries_filters_and_pagination(tmp_path) -> None:
    db = Database(tmp_path / "refract.db")
    p1 = db.upsert_project(project_id="p1", root="/root1")
    p2 = db.upsert_project(project_id="p2", root="/root2")

    # Insert 5 jobs with distinct timestamps and attributes
    now = "2026-11-05T12:00:0"
    for i in range(5):
        job_id = f"job_test_{i}"
        db.create_job(
            job_id=job_id,
            project_id=p1.id if i < 3 else p2.id,
            workflow="workflow-a" if i % 2 == 0 else "workflow-b",
            profile="balanced",
            prompt=f"prompt {i}",
            execution_plan_json="{}",
            session="sess",
        )
        # Update created_at so ordering is deterministic
        with db._connection:
            db._connection.execute(
                "UPDATE jobs SET created_at=?, target=?, state=? WHERE id=?",
                (f"{now}{i}+00:00", f"target-{i % 2}", "running" if i == 0 else "succeeded", job_id),
            )

    # Test filtering by state
    jobs, _ = db.job_summaries(state="running")
    assert len(jobs) == 1
    assert jobs[0]["id"] == "job_test_0"

    # Test filtering by project_id
    jobs, _ = db.job_summaries(project_id=p2.id)
    assert len(jobs) == 2
    assert {j["id"] for j in jobs} == {"job_test_3", "job_test_4"}

    # Test filtering by workflow
    jobs, _ = db.job_summaries(workflow="workflow-a")
    assert len(jobs) == 3
    assert {j["id"] for j in jobs} == {"job_test_0", "job_test_2", "job_test_4"}

    # Test filtering by target
    jobs, _ = db.job_summaries(target="target-1")
    assert len(jobs) == 2
    assert {j["id"] for j in jobs} == {"job_test_1", "job_test_3"}

    # Test q filter with wildcard escaping (e.g. searching for "_test_")
    jobs, _ = db.job_summaries(q="_test_")
    assert len(jobs) == 5

    # Keyset pagination with limit=2
    # Order: created_at DESC, id DESC: jobs 4, 3, 2, 1, 0
    page1, cursor1 = db.job_summaries(limit=2)
    assert len(page1) == 2
    assert [j["id"] for j in page1] == ["job_test_4", "job_test_3"]
    assert cursor1 is not None

    page2, cursor2 = db.job_summaries(cursor=cursor1, limit=2)
    assert len(page2) == 2
    assert [j["id"] for j in page2] == ["job_test_2", "job_test_1"]
    assert cursor2 is not None

    page3, cursor3 = db.job_summaries(cursor=cursor2, limit=2)
    assert len(page3) == 1
    assert [j["id"] for j in page3] == ["job_test_0"]
    assert cursor3 is None

    # Test options: unfiltered distinct values across all jobs
    opts = db.job_filter_options()
    assert opts["states"] == ["running", "succeeded"]
    assert opts["workflows"] == ["workflow-a", "workflow-b"]
    assert opts["targets"] == ["target-0", "target-1"]
    assert opts["projects"] == [{"id": "p1", "root": "/root1"}, {"id": "p2", "root": "/root2"}]

    db.close()




def _wal_copy_hook(monkeypatch, on_wal_copy):
    """Route shutil.copyfile through ``on_wal_copy`` for the -wal source only."""
    import shutil

    real_copyfile = shutil.copyfile
    wal_copies: list[str] = []

    def copyfile(source, destination, *args, **kwargs):
        if str(source).endswith("-wal"):
            wal_copies.append(str(source))
            on_wal_copy(source)
        return real_copyfile(source, destination, *args, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", copyfile)
    return wal_copies


def test_probe_version_restarts_when_wal_vanishes_after_the_existence_check(tmp_path, monkeypatch) -> None:
    from pathlib import Path

    database = Database(tmp_path / "refract.db")
    wal = Path(f"{database._path}-wal")
    expected = database._probe_version()
    assert expected
    assert wal.exists()

    def vanish(source) -> None:
        # A closing daemon checkpoints the WAL into the main file, then deletes it.
        if Path(source).exists() and len(copies) == 1:
            database._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            # The writer closes first: Windows refuses to delete a file another handle holds open.
            database._connection.close()
            Path(source).unlink(missing_ok=True)
            raise FileNotFoundError(source)

    copies = _wal_copy_hook(monkeypatch, vanish)
    assert database._probe_version() == expected
    assert len(copies) >= 1
    assert not list(tmp_path.glob(".version-probe-*"))


def test_probe_version_gives_up_after_three_attempts(tmp_path, monkeypatch) -> None:
    database = Database(tmp_path / "refract.db")

    def always_vanished(source) -> None:
        raise FileNotFoundError(source)

    copies = _wal_copy_hook(monkeypatch, always_vanished)
    with pytest.raises(FileNotFoundError):
        database._probe_version()
    assert len(copies) == 3
    assert not list(tmp_path.glob(".version-probe-*"))


def test_target_with_null_backend_writes_empty_backend_metrics(tmp_path):
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", root="/project")
    database.create_job(
        job_id="null-backend", project_id=project.id, workflow="implement", profile="balanced",
        prompt="p", execution_plan_json=json.dumps({"targets": [{"id": "t", "backend": None}]}),
        session="s",
    )
    database.finish_job("null-backend", "failed", target="t")
    row = database._connection.execute(
        "SELECT state, backend FROM job_metrics WHERE job_id='null-backend'",
    ).fetchone()
    assert tuple(row) == ("failed", "")
    database.close()


def test_interrupt_active_jobs_leaves_a_job_that_turned_terminal_after_the_select(tmp_path, monkeypatch):
    real_connect = sqlite3.connect
    race: dict[str, object] = {}

    class Selected:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

    class RacingConnection(sqlite3.Connection):
        def execute(self, statement, *args, **kwargs):
            cursor = super().execute(statement, *args, **kwargs)
            if "state='running' ORDER BY" in statement and race.get("hook"):
                rows = cursor.fetchall()
                hook, race["hook"] = race["hook"], None
                hook()
                return Selected(rows)
            return cursor

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **kw: real_connect(*a, factory=RacingConnection, **kw))
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", root="/project")
    for job_id in ("still-running", "finishes-first"):
        database.create_job(
            job_id=job_id, project_id=project.id, workflow="implement", profile="balanced",
            prompt="p", execution_plan_json="{}", session=job_id,
        )
        database.start_job(job_id)
    race["hook"] = lambda: database.finish_job(
        "finishes-first", "succeeded", text="done", target="t", model="m", tokens={"input": 5},
    )

    database.interrupt_active_jobs()

    assert database.job_record("finishes-first")["state"] == "succeeded"
    metrics = database.job_metrics_row("finishes-first")
    assert (metrics["state"], metrics["tok_input"]) == ("succeeded", 5)
    assert database.job_record("still-running")["state"] == "interrupted"
    assert database.job_metrics_row("still-running")["state"] == "interrupted"
    database.close()


def test_fresh_database_has_metrics_profile_column_at_schema_21(tmp_path) -> None:
    path = tmp_path / "refract.db"
    database = Database(path)

    assert "profile" in table_columns(database, "job_metrics")
    database.close()
    assert _user_version(path) == 21


def test_schema_20_database_migrates_and_backfills_profile_from_retained_jobs(tmp_path) -> None:
    path = tmp_path / "refract.db"
    job_id = _schema_20(path)

    Database(path).close()

    assert _user_version(path) == 21
    assert _profiles(path) == {job_id: "default", "pruned-job": ""}
    migrated = Database(path)
    project = migrated.upsert_project(project_id="p2", root="/p2")
    migrated.create_job(
        job_id="after-migration", project_id=project.id, workflow="implement", profile="fast",
        prompt="p", execution_plan_json="{}", session="s",
    )
    migrated.finish_job("after-migration", "succeeded", target="target")
    assert migrated.job_metrics_row("after-migration")["profile"] == "fast"
    migrated.close()


@pytest.mark.parametrize("make_old", [_schema_18, _schema_19], ids=["schema-18", "schema-19"])
def test_schema_18_and_19_reach_schema_21_with_profile_backfilled(tmp_path, make_old) -> None:
    path = tmp_path / "refract.db"
    job_id = make_old(path)

    Database(path).close()

    assert _user_version(path) == 21
    assert _profiles(path) == {job_id: "default"}


def test_failed_schema_21_migration_keeps_schema_20_without_profile_column(tmp_path, monkeypatch) -> None:
    path = tmp_path / "refract.db"
    _schema_20(path)
    real_connect = sqlite3.connect

    class FailingConnection(sqlite3.Connection):
        def execute(self, statement, *args, **kwargs):
            if statement.startswith("UPDATE job_metrics SET profile"):
                raise sqlite3.OperationalError("backfill failed")
            return super().execute(statement, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: real_connect(*a, factory=FailingConnection, **k))

    with pytest.raises(sqlite3.OperationalError, match="backfill failed"):
        Database(path)

    monkeypatch.undo()
    assert _user_version(path) == 20
    with closing(sqlite3.connect(path)) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(job_metrics)")}
    assert "profile" not in columns


def test_newly_terminal_job_stores_its_profile_in_metrics(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", root="/project")
    database.create_job(
        job_id="profiled", project_id=project.id, workflow="implement", profile="fast",
        prompt="p", execution_plan_json="{}", session="s",
    )

    database.finish_job("profiled", "succeeded", target="target")

    assert database.job_metrics_row("profiled")["profile"] == "fast"
    database.close()
