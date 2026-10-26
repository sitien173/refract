from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from refract.database import Database


def table_columns(database: Database, table: str) -> set[str]:
    return {
        row["name"]
        for row in database._connection.execute("SELECT name FROM pragma_table_info(?)", (table,))
    }


@pytest.mark.parametrize("version", [-1, *range(15), 16, 99])
def test_unsupported_schema_is_rejected_without_writes_or_connection_leaks(tmp_path, monkeypatch, version) -> None:
    path = tmp_path / "refract.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE retained (value TEXT NOT NULL)")
    connection.execute("INSERT INTO retained VALUES ('historical data')")
    connection.execute(f"PRAGMA user_version={version}")
    connection.commit()
    connection.close()
    before = path.read_bytes()
    files_before = set(tmp_path.iterdir())
    real_connect = sqlite3.connect
    opened = []
    statements = []

    def track_connection(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        opened.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", track_connection)
    with pytest.raises(ValueError, match=f"Unsupported database schema {version}") as error:
        Database(path)

    assert "supports schema 15 only" in str(error.value)
    assert "not modified" in str(error.value)
    assert str(path) in str(error.value)
    recovery = "upgrade" if version < 15 else f"supports schema {version}"
    assert recovery in str(error.value)
    assert path.read_bytes() == before
    assert set(tmp_path.iterdir()) == files_before
    assert not any("journal_mode" in statement.lower() for statement in statements)
    assert all(statement.startswith(("SELECT", "PRAGMA")) for statement in statements)
    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


@pytest.mark.parametrize("version", [14, 16])
def test_rejected_wal_database_is_not_checkpointed(tmp_path, version) -> None:
    path = tmp_path / "refract #?.db"
    subprocess.run([
        sys.executable, "-c",
        (
            "import os, sqlite3, sys; "
            "connection = sqlite3.connect(sys.argv[1]); "
            "connection.execute('PRAGMA journal_mode=WAL'); "
            "connection.execute('CREATE TABLE retained (value TEXT)'); "
            "connection.execute(\"INSERT INTO retained VALUES ('historical data')\"); "
            "connection.execute('PRAGMA user_version=' + sys.argv[2]); "
            "connection.commit(); os._exit(0)"
        ),
        str(path), str(version),
    ], check=True, timeout=10)
    wal = path.with_name(path.name + "-wal")
    before = path.read_bytes()
    wal_before = wal.read_bytes()

    with pytest.raises(ValueError, match=f"Unsupported database schema {version}"):
        Database(path)

    assert path.read_bytes() == before
    assert wal.read_bytes() == wal_before


@pytest.mark.parametrize("version", [14, 15, 16])
def test_stamped_empty_database_is_not_bootstrapped(tmp_path, version) -> None:
    path = tmp_path / "empty.db"
    connection = sqlite3.connect(path)
    connection.execute(f"PRAGMA user_version={version}")
    connection.close()
    before = path.read_bytes()

    with pytest.raises(ValueError, match=f"schema {version}"):
        Database(path)

    assert path.read_bytes() == before
    assert set(tmp_path.iterdir()) == {path}


def test_unversioned_view_only_database_is_not_empty(tmp_path) -> None:
    path = tmp_path / "view.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE VIEW retained AS SELECT 'historical data' AS value")
    connection.close()
    before = path.read_bytes()

    with pytest.raises(ValueError, match="Unsupported database schema 0"):
        Database(path)

    assert path.read_bytes() == before


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
        raise sqlite3.OperationalError("schema setup failed")

    monkeypatch.setattr(sqlite3, "connect", track_connection)
    if failure == "schema":
        monkeypatch.setattr(Database, "_create_schema", fail_schema)
    with pytest.raises(sqlite3.OperationalError, match="setup failed"):
        Database(tmp_path / "refract.db")

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")


@pytest.mark.parametrize("existing_empty_file", [False, True])
def test_fresh_database_uses_v15_schema(tmp_path, existing_empty_file) -> None:
    path = tmp_path / "refract.db"
    if existing_empty_file:
        path.touch()
    database = Database(path)
    tables = {row["name"] for row in database._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert database._connection.execute("PRAGMA user_version").fetchone()[0] == 15
    assert table_columns(database, "projects") == {"id", "alias", "root", "created_at"}
    assert table_columns(database, "jobs") == {"id", "project_id", "workflow", "profile", "prompt", "execution_plan_json", "context_key", "state", "result_text", "target_id", "attempts", "error", "config_revision", "fresh_session", "result_metadata_json", "created_at", "updated_at"}
    assert "job_dependencies" not in tables
    assert {"projects", "jobs", "events", "context_sessions", "context_turns", "target_health", "job_stream_events"} <= tables
    assert "stages" not in tables
    assert "artifacts" not in tables
    database.close()


def test_reopening_v15_preserves_jobs_and_history(tmp_path) -> None:
    path = tmp_path / "refract.db"
    first = Database(path)
    project = first.upsert_project(project_id="project", alias="project", root="/project")
    first.create_job(
        job_id="job", project_id=project.id, workflow="consult", profile="balanced",
        prompt="retained prompt", execution_plan_json="{}", context_key="consult",
    )
    first.append_turn(
        project_id=project.id, context_key="consult", role="consult", target_id="target",
        target_key="target", session_id="session", prompt="retained prompt", response="retained response",
    )
    first.finish_job("job", "succeeded", text="retained response", target_id="target")
    first.record_target_failure("target")
    before = list(first._connection.iterdump())
    first.close()

    second = Database(path)
    assert second._connection.execute("PRAGMA user_version").fetchone()[0] == 15
    assert list(second._connection.iterdump()) == before
    job = second.job("job")
    assert job is not None
    assert job.result.text == "retained response"
    assert second.session(project.id, "consult", "consult", "target") == "session"
    assert second.recent_turns(project.id, "consult", "consult", 8)[0]["response"] == "retained response"
    assert second.target_health("target")["consecutive_failures"] == 1
    second.close()


def test_create_job_persists_fresh_session_flag(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="proj", alias="proj", root="/proj")
    database.create_job(
        job_id="standard-job",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="question",
        execution_plan_json="{}",
        context_key="consult",
    )
    database.create_job(
        job_id="fresh-job",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="question",
        execution_plan_json="{}",
        context_key="consult",
        fresh_session=True,
    )
    standard_record = database.job_record("standard-job")
    fresh_record = database.job_record("fresh-job")
    assert standard_record and standard_record["fresh_session"] == 0
    assert fresh_record and fresh_record["fresh_session"] == 1
    database.close()


def test_job_revision_survives_retry_without_plan_changes(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", alias="project", root="/project")
    database.create_job(
        job_id="job",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="question",
        execution_plan_json='{"targets":["primary"]}',
        context_key="consult",
        config_revision="a" * 64,
    )
    with database._connection:
        database._connection.execute("UPDATE jobs SET state='failed' WHERE id='job'")
    database.reset_retry("job")
    record = database.job_record("job")
    assert record and record["config_revision"] == "a" * 64
    assert record["execution_plan_json"] == '{"targets":["primary"]}'
    database.close()


def test_jobs_load_with_one_query(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(
        project_id="project", alias="project", root="/project"
    )
    for job_id in ("first", "second"):
        database.create_job(
            job_id=job_id,
            project_id=project.id,
            workflow="consult",
            profile="balanced",
            prompt=job_id,
            execution_plan_json="{}",
            context_key="consult",
        )
    statements: list[str] = []
    database._connection.set_trace_callback(statements.append)

    jobs = database.jobs(project.id)

    database._connection.set_trace_callback(None)
    assert {job.id for job in jobs} == {"first", "second"}
    assert len([statement for statement in statements if statement.startswith("SELECT")]) == 1
    database.close()


def test_job_listing_bounds_terminal_jobs_and_uses_project_index(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", alias="project", root="/project")
    for index in range(14):
        job_id = f"job-{index:02d}"
        database.create_job(
            job_id=job_id, project_id=project.id, workflow="consult", profile="balanced",
            prompt=job_id, execution_plan_json="{}", context_key="consult",
        )
        if index >= 2:
            database.finish_job(job_id, "succeeded")

    active, recent, more_recent = database.job_listing(project.id, recent_limit=10)

    assert {record["id"] for record in active} == {"job-00", "job-01"}
    assert [record["id"] for record in recent] == [f"job-{index:02d}" for index in range(13, 3, -1)]
    assert more_recent == 2
    plan = database._connection.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM jobs WHERE project_id=? ORDER BY updated_at DESC", ("project",)
    ).fetchall()
    assert any("jobs_project_idx" in row["detail"] for row in plan)
    database.close()


def test_context_includes_sessionless_turns_with_fixed_query_count(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(
        project_id="project", alias="project", root="/project"
    )
    database.append_turn(
        project_id=project.id,
        context_key="shared",
        role="consult",
        target_id="sage",
        target_key="sage",
        session_id="",
        prompt="question",
        response="answer",
    )
    database.append_turn(
        project_id=project.id,
        context_key="shared",
        role="review",
        target_id="sentinel",
        target_key="sentinel",
        session_id="review-session",
        prompt="review",
        response="approved",
    )
    statements: list[str] = []
    database._connection.set_trace_callback(statements.append)

    streams = database.context(project.id, "shared")

    database._connection.set_trace_callback(None)
    assert [stream.role for stream in streams] == ["consult", "review"]
    assert streams[0].turns == 1
    assert streams[0].sessions == {}
    assert streams[1].turns == 1
    assert streams[1].sessions == {"sentinel": "review-session"}
    assert len([statement for statement in statements if statement.startswith("SELECT")]) == 2
    database.close()


def test_append_turn_atomic_rollback_preserves_sessions(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", alias="project", root="/project")
    database.append_turn(
        project_id=project.id,
        context_key="stream",
        role="implement",
        target_id="primary",
        target_key="primary",
        session_id="old-session",
        prompt="turn 1",
        response="response 1",
    )
    assert database.session(project.id, "stream", "implement", "primary") == "old-session"

    database._connection.execute("""
        CREATE TRIGGER fail_turn BEFORE INSERT ON context_turns
        BEGIN
            SELECT RAISE(FAIL, 'simulated turn failure');
        END;
    """)
    with pytest.raises(sqlite3.IntegrityError, match="simulated turn failure"):
        database.append_turn(
            project_id=project.id,
            context_key="stream",
            role="implement",
            target_id="primary",
            target_key="primary",
            session_id="new-session",
            prompt="turn 2",
            response="response 2",
            clear_sessions=True,
        )

    database._connection.execute("DROP TRIGGER fail_turn")
    assert database.session(project.id, "stream", "implement", "primary") == "old-session"
    database.close()


def test_append_turn_clear_sessions_clears_multiple_stale_and_preserves_unrelated(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="project", alias="project", root="/project")

    database.append_turn(
        project_id=project.id,
        context_key="stream-1",
        role="implement",
        target_id="primary",
        target_key="primary-key",
        session_id="stale-sess-1",
        prompt="turn 1",
        response="response 1",
    )
    database.append_turn(
        project_id=project.id,
        context_key="stream-1",
        role="implement",
        target_id="secondary",
        target_key="secondary-key",
        session_id="stale-sess-2",
        prompt="turn 2",
        response="response 2",
    )

    database.append_turn(
        project_id=project.id,
        context_key="stream-2",
        role="review",
        target_id="primary",
        target_key="primary-key",
        session_id="unrelated-sess",
        prompt="review turn",
        response="review response",
    )

    assert database.session(project.id, "stream-1", "implement", "primary-key") == "stale-sess-1"
    assert database.session(project.id, "stream-1", "implement", "secondary-key") == "stale-sess-2"
    assert database.session(project.id, "stream-2", "review", "primary-key") == "unrelated-sess"

    database.append_turn(
        project_id=project.id,
        context_key="stream-1",
        role="implement",
        target_id="primary",
        target_key="primary-key",
        session_id="replacement-sess",
        prompt="recovered turn",
        response="recovered response",
        clear_sessions=True,
    )

    assert database.session(project.id, "stream-1", "implement", "primary-key") == "replacement-sess"
    assert database.session(project.id, "stream-1", "implement", "secondary-key") == ""

    cursor = database._connection.execute(
        "SELECT target_key, session_id FROM context_sessions WHERE project_id=? AND context_key=? AND role=?",
        (project.id, "stream-1", "implement"),
    )
    rows = cursor.fetchall()
    assert len(rows) == 1
    assert rows[0]["session_id"] == "replacement-sess"

    assert database.session(project.id, "stream-2", "review", "primary-key") == "unrelated-sess"
    database.close()


def test_append_stream_events_persists_batch_transactionally(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="p1", alias="p1", root="/p1")
    database.create_job(
        job_id="job-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    events = [
        {
            "created_at": "2026-09-11T04:40:00Z",
            "attempt": 1,
            "target_id": "target-a",
            "backend": "claude",
            "kind": "assistant.message.started",
            "entity_id": "msg-1",
            "parent_entity_id": "",
            "data": {"role": "assistant"},
        },
        {
            "created_at": "2026-09-11T04:40:01Z",
            "attempt": 1,
            "target_id": "target-a",
            "backend": "claude",
            "kind": "assistant.text.delta",
            "entity_id": "msg-1",
            "parent_entity_id": "",
            "data": {"text": "chunk 1"},
        },
    ]
    persisted = database.append_stream_events("job-1", events)
    assert len(persisted) == 2
    assert persisted[0].id > 0
    assert persisted[1].id > persisted[0].id
    assert persisted[0].kind == "assistant.message.started"
    assert persisted[1].data == {"text": "chunk 1"}

    rows = database._connection.execute(
        "SELECT id, kind, data_json, size_bytes FROM job_stream_events WHERE job_id='job-1' ORDER BY id"
    ).fetchall()
    assert len(rows) == 2
    assert rows[1]["size_bytes"] == len(json.dumps({"text": "chunk 1"}, ensure_ascii=False).encode("utf-8"))
    database.close()


def test_stream_events_returns_ascending_cursor_pages(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="p1", alias="p1", root="/p1")
    database.create_job(
        job_id="job-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    batch = [
        {
            "attempt": 1,
            "target_id": "t1",
            "backend": "claude",
            "kind": "assistant.text.delta",
            "entity_id": f"msg-{i}",
            "parent_entity_id": "",
            "data": {"text": f"token-{i}"},
        }
        for i in range(5)
    ]
    persisted = database.append_stream_events("job-1", batch)
    ids = [e.id for e in persisted]

    page1 = database.stream_events("job-1", after=0, limit=2)
    assert [e.id for e in page1] == ids[:2]

    page2 = database.stream_events("job-1", after=ids[1], limit=2)
    assert [e.id for e in page2] == ids[2:4]

    page3 = database.stream_events("job-1", after=ids[3], limit=2)
    assert [e.id for e in page3] == ids[4:]

    page4 = database.stream_events("job-1", after=ids[4], limit=2)
    assert page4 == []
    database.close()


def test_stream_high_water_and_retained_from_lookups(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="p1", alias="p1", root="/p1")
    database.create_job(
        job_id="job-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    assert database.stream_high_water("job-1") == 0
    assert database.stream_retained_from("job-1") == 0

    batch = [
        {
            "attempt": 1,
            "target_id": "t1",
            "backend": "claude",
            "kind": "assistant.text.delta",
            "entity_id": f"msg-{i}",
            "parent_entity_id": "",
            "data": {"text": f"token-{i}"},
        }
        for i in range(3)
    ]
    persisted = database.append_stream_events("job-1", batch)
    assert database.stream_high_water("job-1") == persisted[-1].id
    assert database.stream_retained_from("job-1") == persisted[0].id
    database.close()


def test_stream_events_cascade_delete_on_job_deletion(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="p1", alias="p1", root="/p1")
    database.create_job(
        job_id="job-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    database.append_stream_events("job-1", [{
        "attempt": 1,
        "target_id": "t1",
        "backend": "claude",
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "parent_entity_id": "",
        "data": {"text": "hi"},
    }])
    assert database.stream_high_water("job-1") > 0
    with database._connection:
        database._connection.execute("DELETE FROM jobs WHERE id='job-1'")
    assert database.stream_high_water("job-1") == 0
    count = database._connection.execute("SELECT COUNT(*) FROM job_stream_events WHERE job_id='job-1'").fetchone()[0]
    assert count == 0
    database.close()


def test_database_reopen_preserves_stream_events_and_cursors(tmp_path) -> None:
    path = tmp_path / "refract.db"
    database = Database(path)
    project = database.upsert_project(project_id="p1", alias="p1", root="/p1")
    database.create_job(
        job_id="job-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    persisted = database.append_stream_events("job-1", [{
        "attempt": 1,
        "target_id": "t1",
        "backend": "claude",
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "parent_entity_id": "",
        "data": {"text": "persisted token"},
    }])
    event_id = persisted[0].id
    database.close()

    reopened = Database(path)
    assert reopened._connection.execute("PRAGMA user_version").fetchone()[0] == 15
    assert reopened.stream_high_water("job-1") == event_id
    assert reopened.stream_retained_from("job-1") == event_id
    events = reopened.stream_events("job-1", after=0)
    assert len(events) == 1
    assert events[0].id == event_id
    assert events[0].data == {"text": "persisted token"}
    reopened.close()


def test_stream_totals_computes_event_count_and_bytes(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="p1", alias="p1", root="/p1")
    database.create_job(
        job_id="job-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    totals = database.stream_totals("job-1")
    assert totals.events == 0
    assert totals.bytes == 0

    database.append_stream_events("job-1", [
        {
            "attempt": 1,
            "target_id": "t1",
            "backend": "claude",
            "kind": "assistant.text.delta",
            "entity_id": "msg-1",
            "parent_entity_id": "",
            "data": {"text": "a" * 100},
        },
        {
            "attempt": 1,
            "target_id": "t1",
            "backend": "claude",
            "kind": "assistant.text.delta",
            "entity_id": "msg-1",
            "parent_entity_id": "",
            "data": {"text": "b" * 200},
        },
    ])
    totals2 = database.stream_totals("job-1")
    assert totals2.events == 2
    assert totals2.bytes > 300
    events_count, total_bytes = totals2
    assert events_count == 2
    assert total_bytes == totals2.bytes
    database.close()


def test_prune_terminal_stream_events_removes_only_terminal_before_cutoff(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="p1", alias="p1", root="/p1")

    # job-old-term: terminal, updated long ago
    database.create_job(
        job_id="job-old-term",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    with database._connection:
        database._connection.execute(
            "UPDATE jobs SET state='succeeded', updated_at='2026-09-01T00:00:00Z' WHERE id='job-old-term'"
        )

    # job-recent-term: terminal, updated recently
    database.create_job(
        job_id="job-recent-term",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k2",
    )
    with database._connection:
        database._connection.execute(
            "UPDATE jobs SET state='failed', updated_at='2026-09-10T00:00:00Z' WHERE id='job-recent-term'"
        )

    # job-old-active: active (running), updated long ago
    database.create_job(
        job_id="job-old-active",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k3",
    )
    with database._connection:
        database._connection.execute(
            "UPDATE jobs SET state='running', updated_at='2026-09-01T00:00:00Z' WHERE id='job-old-active'"
        )

    for jid in ("job-old-term", "job-recent-term", "job-old-active"):
        database.append_stream_events(jid, [{
            "attempt": 1,
            "target_id": "t1",
            "backend": "claude",
            "kind": "assistant.text.delta",
            "entity_id": "msg-1",
            "parent_entity_id": "",
            "data": {"text": "data"},
        }])

    cutoff = "2026-09-05T00:00:00Z"
    deleted = database.prune_terminal_stream_events(cutoff)
    assert deleted == 1

    assert database.stream_high_water("job-old-term") == 0
    assert database.stream_high_water("job-recent-term") > 0
    assert database.stream_high_water("job-old-active") > 0

    # Job rows themselves are never deleted
    assert database.job("job-old-term") is not None
    assert database.job("job-recent-term") is not None
    assert database.job("job-old-active") is not None
    database.close()


def test_stream_is_truncated_lookup(tmp_path) -> None:
    database = Database(tmp_path / "refract.db")
    project = database.upsert_project(project_id="p1", alias="p1", root="/p1")
    database.create_job(
        job_id="job-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    assert database.stream_is_truncated("job-1") is False

    database.append_stream_events("job-1", [{
        "attempt": 1,
        "target_id": "t1",
        "backend": "claude",
        "kind": "assistant.text.delta",
        "entity_id": "m1",
        "parent_entity_id": "",
        "data": {"text": "hi"},
    }])
    assert database.stream_is_truncated("job-1") is False

    database.append_stream_events("job-1", [{
        "attempt": 1,
        "target_id": "t1",
        "backend": "claude",
        "kind": "stream.truncated",
        "entity_id": "stream",
        "parent_entity_id": "",
        "data": {"reason": "limit_exceeded"},
    }])
    assert database.stream_is_truncated("job-1") is True
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


def test_merge_job_telemetry_preserves_unrelated_fields(tmp_path) -> None:
    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="p1", alias="p1", root="/p1")
    db.create_job(
        job_id="job-tel-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    with db._connection:
        db._connection.execute(
            "UPDATE jobs SET result_metadata_json=? WHERE id=?",
            (json.dumps({"custom_flag": "test", "model_name": "gpt-4"}), "job-tel-1"),
        )
    telemetry_payload = {
        "version": 1,
        "completeness": "complete",
        "total_input_tokens": {"value": 150, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:00Z"},
        "total_output_tokens": {"value": 50, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:00Z"},
    }
    db.merge_job_telemetry("job-tel-1", telemetry_payload)
    job = db.job("job-tel-1")
    assert job is not None
    assert job.result.metadata["custom_flag"] == "test"
    assert job.result.metadata["model_name"] == "gpt-4"
    assert job.result.metadata["telemetry"]["total_input_tokens"]["value"] == 150
    assert job.result.metadata["telemetry"]["total_output_tokens"]["value"] == 50
    db.close()


def test_terminal_metadata_protected_against_stale_observations(tmp_path) -> None:
    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="p1", alias="p1", root="/p1")
    db.create_job(
        job_id="job-term-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    final_telemetry = {
        "version": 1,
        "completeness": "complete",
        "total_input_tokens": {"value": 200, "source": "result", "quality": "reported", "observed_at": "2026-10-26T00:00:02Z"},
    }
    db.finish_job("job-term-1", "succeeded", metadata={"telemetry": final_telemetry})

    # Stale observation should be ignored on terminal job
    stale_telemetry = {
        "version": 1,
        "completeness": "partial",
        "total_input_tokens": {"value": 100, "source": "stream", "quality": "reported", "observed_at": "2026-10-26T00:00:01Z"},
    }
    db.merge_job_telemetry("job-term-1", stale_telemetry)
    job = db.job("job-term-1")
    assert job is not None
    assert job.result.metadata["telemetry"]["total_input_tokens"]["value"] == 200
    db.close()


def test_merge_job_telemetry_validates_and_sanitizes_before_persistence(tmp_path) -> None:
    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="p1", alias="p1", root="/p1")
    db.create_job(
        job_id="job-san-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    # Attempt to write invalid telemetry (e.g. negative tokens or booleans)
    invalid_payload = {
        "version": 1,
        "total_input_tokens": {"value": -100, "source": "provider", "quality": "reported"},
    }
    db.merge_job_telemetry("job-san-1", invalid_payload)
    job = db.job("job-san-1")
    assert job is not None
    # Invalid telemetry must NOT be persisted
    assert "telemetry" not in job.result.metadata
    # A telemetry key is always validated, including explicit null values.
    db.finish_job("job-san-1", "failed", metadata={"telemetry": None})
    job = db.job("job-san-1")
    assert job is not None
    assert "telemetry" not in job.result.metadata
    db.close()



def test_finish_job_merges_with_running_telemetry(tmp_path) -> None:
    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="p1", alias="p1", root="/p1")
    db.create_job(
        job_id="job-fin-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    running_telemetry = {
        "version": 1,
        "completeness": "complete",
        "total_input_tokens": {"value": 300, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:01Z"},
    }
    db.merge_job_telemetry("job-fin-1", running_telemetry)

    # finish_job called with non-telemetry metadata
    db.finish_job("job-fin-1", "succeeded", metadata={"duration_ms": 120, "model_name": "claude"})
    job = db.job("job-fin-1")
    assert job is not None
    assert job.result.metadata["duration_ms"] == 120
    assert job.result.metadata["model_name"] == "claude"
    assert job.result.metadata["telemetry"]["total_input_tokens"]["value"] == 300
    db.close()


def test_retry_preserves_completed_attempt_aggregate_and_totals(tmp_path) -> None:
    db = Database(tmp_path / "refract.db")
    project = db.upsert_project(project_id="p1", alias="p1", root="/p1")
    db.create_job(
        job_id="job-retry-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    attempt1_telemetry = {
        "version": 1,
        "completeness": "complete",
        "total_input_tokens": {"value": 150, "source": "response", "quality": "reported", "observed_at": "2026-10-26T00:00:01Z"},
        "total_output_tokens": {"value": 50, "source": "response", "quality": "reported", "observed_at": "2026-10-26T00:00:01Z"},
        "context_used_tokens": {"value": 1000, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:01Z"},
        "attribution": {"attempt": 1, "invocation": 1},
        "completed_attempts": {"total_input_tokens": 0, "total_output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0},
    }
    db.merge_job_telemetry("job-retry-1", attempt1_telemetry)
    db.finish_job("job-retry-1", "failed", error="timeout")

    # Reset retry
    db.reset_retry("job-retry-1")
    job = db.job("job-retry-1")
    assert job is not None
    assert job.state == "queued"
    telemetry = job.result.metadata["telemetry"]
    # Aggregate from attempt 1 preserved
    assert telemetry["completed_attempts"]["total_input_tokens"] == 150
    assert telemetry["completed_attempts"]["total_output_tokens"] == 50
    # Total consumption preserved
    assert telemetry["total_input_tokens"]["value"] == 150
    assert telemetry["total_output_tokens"]["value"] == 50
    # Context snapshot is cleared (not carried over to new attempt)
    assert telemetry["context_used_tokens"]["value"] is None
    assert telemetry["context_used_tokens"]["quality"] == "unavailable"
    db.close()


def test_database_reopen_preserves_telemetry_without_schema_upgrade(tmp_path) -> None:
    path = tmp_path / "reopen.db"
    db = Database(path)
    project = db.upsert_project(project_id="p1", alias="p1", root="/p1")
    db.create_job(
        job_id="job-reopen-1",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="hello",
        execution_plan_json="{}",
        context_key="k1",
    )
    telemetry = {
        "version": 1,
        "completeness": "complete",
        "total_input_tokens": {"value": 500, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T00:00:01Z"},
    }
    db.merge_job_telemetry("job-reopen-1", telemetry)
    db.close()

    # Reopen
    db2 = Database(path)
    version = int(db2._connection.execute("PRAGMA user_version").fetchone()[0])
    assert version == 15
    job = db2.job("job-reopen-1")
    assert job is not None
    assert job.result.metadata["telemetry"]["total_input_tokens"]["value"] == 500
    db2.close()

