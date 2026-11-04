from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from refract.database import Database


def table_columns(database: Database, table: str) -> set[str]:
    return {
        row["name"]
        for row in database._connection.execute("SELECT name FROM pragma_table_info(?)", (table,))
    }


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
    assert standard_record and standard_record["fresh"] == 0
    assert fresh_record and fresh_record["fresh"] == 1
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


