from __future__ import annotations

import json
import sqlite3

import pytest

from openmcp.database import Database


def create_legacy_database(path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE projects (id TEXT PRIMARY KEY, alias TEXT NOT NULL UNIQUE, root TEXT NOT NULL UNIQUE, head_commit TEXT NOT NULL, clean INTEGER NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), workflow TEXT NOT NULL, profile TEXT NOT NULL DEFAULT '', workflow_json TEXT NOT NULL, execution_plan_json TEXT NOT NULL DEFAULT '', result_stage TEXT NOT NULL DEFAULT '', inputs_json TEXT NOT NULL, context_key TEXT NOT NULL, parent_job_id TEXT NOT NULL DEFAULT '', state TEXT NOT NULL, base_commit TEXT NOT NULL, integration_base TEXT NOT NULL DEFAULT '', branch TEXT NOT NULL, worktree TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, result_commit TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '');
        CREATE TABLE stages (job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, id TEXT NOT NULL, ordinal INTEGER NOT NULL, mode TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, target_id TEXT NOT NULL DEFAULT '', text TEXT NOT NULL DEFAULT '', outputs_json TEXT NOT NULL DEFAULT '[]', error TEXT NOT NULL DEFAULT '', commit_sha TEXT NOT NULL DEFAULT '', start_commit TEXT NOT NULL DEFAULT '', PRIMARY KEY(job_id, id));
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, created_at TEXT NOT NULL, kind TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE artifacts (job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, kind TEXT NOT NULL, path TEXT NOT NULL, PRIMARY KEY(job_id, kind, path));
        CREATE TABLE context_sessions (project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, target_key TEXT NOT NULL, lane TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(project_id, context_key, role, target_key, lane));
        CREATE TABLE context_turns (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, prompt TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE target_health (target_id TEXT PRIMARY KEY, consecutive_failures INTEGER NOT NULL DEFAULT 0, circuit_open_until TEXT NOT NULL DEFAULT '', last_success_at TEXT NOT NULL DEFAULT '');
    """)
    connection.execute("INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?)", ("project", "project", "/project", "base-sha", 1, "2026-01-01"))
    inputs = json.dumps({"prompt": "legacy", "commit_message": "feat: legacy"})
    connection.executemany("""INSERT INTO jobs(id, project_id, workflow, profile, workflow_json, execution_plan_json, result_stage, inputs_json, context_key, parent_job_id, state, base_commit, integration_base, branch, worktree, created_at, updated_at, result_commit, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", [("completed", "project", "implement", "balanced", "{}", "{}", "execute", inputs, "legacy", "", "integrated", "base-sha", "base-sha", "openmcp/completed", "/worktree/completed", "2026-01-01", "2026-01-01", "result-sha", ""), ("running", "project", "implement", "balanced", "{}", "{}", "execute", inputs, "legacy", "", "running", "base-sha", "base-sha", "openmcp/running", "/worktree/running", "2026-01-01", "2026-01-01", "", ""), ("queued", "project", "review", "balanced", "{}", "{}", "execute", inputs, "legacy", "", "queued", "base-sha", "base-sha", "openmcp/queued", "/worktree/queued", "2026-01-01", "2026-01-01", "", ""), ("conflict", "project", "implement", "balanced", "{}", "{}", "execute", inputs, "legacy", "", "integration_conflict", "base-sha", "base-sha", "openmcp/conflict", "/worktree/conflict", "2026-01-01", "2026-01-01", "", "conflict")])
    connection.executemany("INSERT INTO stages(job_id, id, ordinal, mode, state, attempts, target_id, text, commit_sha) VALUES (?, 'execute', 0, 'write', ?, ?, ?, ?, ?)", [("completed", "succeeded", 2, "legacy-target", "legacy response", "result-sha"), ("running", "running", 1, "legacy-target", "", ""), ("queued", "pending", 0, "", "", ""), ("conflict", "succeeded", 1, "legacy-target", "", "result-sha")])
    connection.execute("INSERT INTO events(job_id, created_at, kind, data_json) VALUES (?, ?, ?, ?)", ("completed", "2026-01-01", "legacy.event", "{}"))
    connection.execute("INSERT INTO context_turns(project_id, context_key, role, target_id, prompt, response, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", ("project", "legacy", "implement", "legacy-target", "legacy prompt", "legacy response", "2026-01-01"))
    connection.commit()
    connection.close()


def create_v5_database(path, *, invalid_foreign_key: bool = False) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA foreign_keys=OFF;
        CREATE TABLE projects (id TEXT PRIMARY KEY, alias TEXT NOT NULL UNIQUE, root TEXT NOT NULL UNIQUE, head_commit TEXT NOT NULL, clean INTEGER NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), workflow TEXT NOT NULL, profile TEXT NOT NULL, prompt TEXT NOT NULL, commit_message TEXT NOT NULL DEFAULT '', execution_plan_json TEXT NOT NULL, context_key TEXT NOT NULL, state TEXT NOT NULL, base_commit TEXT NOT NULL DEFAULT '', result_text TEXT NOT NULL DEFAULT '', result_commit TEXT NOT NULL DEFAULT '', target_id TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, created_at TEXT NOT NULL, kind TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE context_sessions (project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, target_key TEXT NOT NULL, lane TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(project_id, context_key, role, target_key, lane));
        CREATE TABLE context_turns (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, prompt TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE target_health (target_id TEXT PRIMARY KEY, consecutive_failures INTEGER NOT NULL DEFAULT 0, circuit_open_until TEXT NOT NULL DEFAULT '', last_success_at TEXT NOT NULL DEFAULT '');
        CREATE INDEX jobs_state_idx ON jobs(state, created_at);
    """)
    connection.execute("PRAGMA user_version=5")
    connection.execute("INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?)", ("project", "project", "/project", "head", 0, "2026-01-01"))
    project_id = "missing" if invalid_foreign_key else "project"
    connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("job", project_id, "consult", "balanced", "prompt", "legacy message", "{}", "consult", "succeeded", "base", "result text", "result", "target", 2, "", "2026-01-01", "2026-01-02"))
    connection.execute("INSERT INTO events(job_id, created_at, kind, data_json) VALUES (?, ?, ?, ?)", ("job", "2026-01-01", "job.queued", "{}"))
    connection.execute("INSERT INTO context_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("project", "consult", "consult", "target", "target", "", "session", "2026-01-01"))
    connection.execute("INSERT INTO context_turns(project_id, context_key, role, target_id, prompt, response, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", ("project", "consult", "consult", "target", "prompt", "response", "2026-01-01"))
    connection.execute("INSERT INTO target_health VALUES (?, ?, ?, ?)", ("target", 1, "", "2026-01-01"))
    connection.commit()
    connection.close()


def create_v6_database(path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE projects (id TEXT PRIMARY KEY, alias TEXT NOT NULL UNIQUE, root TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
        CREATE TABLE jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), workflow TEXT NOT NULL, profile TEXT NOT NULL, prompt TEXT NOT NULL, execution_plan_json TEXT NOT NULL, context_key TEXT NOT NULL, state TEXT NOT NULL, result_text TEXT NOT NULL DEFAULT '', target_id TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, created_at TEXT NOT NULL, kind TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE context_sessions (project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, target_key TEXT NOT NULL, lane TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(project_id, context_key, role, target_key, lane));
        CREATE TABLE context_turns (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, prompt TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE target_health (target_id TEXT PRIMARY KEY, consecutive_failures INTEGER NOT NULL DEFAULT 0, circuit_open_until TEXT NOT NULL DEFAULT '', last_success_at TEXT NOT NULL DEFAULT '');
        CREATE INDEX jobs_state_idx ON jobs(state, created_at);
    """)
    connection.execute("PRAGMA user_version=6")
    connection.execute("INSERT INTO projects VALUES (?, ?, ?, ?)", ("project", "project", "/project", "2026-01-01"))
    connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("job", "project", "consult", "balanced", "prompt", "{}", "consult", "succeeded", "result text", "target", 2, "", "2026-01-01", "2026-01-02"))
    connection.execute("INSERT INTO events(job_id, created_at, kind, data_json) VALUES (?, ?, ?, ?)", ("job", "2026-01-01", "job.queued", "{}"))
    connection.execute("INSERT INTO context_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)", ("project", "consult", "consult", "target", "target", "", "session", "2026-01-01"))
    connection.execute("INSERT INTO context_turns(project_id, context_key, role, target_id, prompt, response, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", ("project", "consult", "consult", "target", "prompt", "response", "2026-01-01"))
    connection.execute("INSERT INTO target_health VALUES (?, ?, ?, ?)", ("target", 1, "", "2026-01-01"))
    connection.commit()
    connection.close()


def create_v8_database(path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE projects (id TEXT PRIMARY KEY, alias TEXT NOT NULL UNIQUE, root TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
        CREATE TABLE jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), workflow TEXT NOT NULL, profile TEXT NOT NULL, prompt TEXT NOT NULL, execution_plan_json TEXT NOT NULL, context_key TEXT NOT NULL, state TEXT NOT NULL, result_text TEXT NOT NULL DEFAULT '', target_id TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', config_revision TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, created_at TEXT NOT NULL, kind TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE context_sessions (project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, target_key TEXT NOT NULL, lane TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(project_id, context_key, role, target_key, lane));
        CREATE TABLE context_turns (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, prompt TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE context_instructions (project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, workflow TEXT NOT NULL, instruction TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(project_id, workflow));
        CREATE TABLE target_health (target_id TEXT PRIMARY KEY, consecutive_failures INTEGER NOT NULL DEFAULT 0, circuit_open_until TEXT NOT NULL DEFAULT '', last_success_at TEXT NOT NULL DEFAULT '');
        CREATE INDEX jobs_state_idx ON jobs(state, created_at);
        PRAGMA user_version=8;
    """)
    connection.execute("INSERT INTO projects VALUES (?, ?, ?, ?)", ("project", "project", "/project", "2026-01-01"))
    connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("job", "project", "consult", "balanced", "prompt", "{}", "consult", "succeeded", "result text", "target", 2, "", "rev", "2026-01-01", "2026-01-02"))
    connection.execute("INSERT INTO context_instructions VALUES (?, ?, ?, ?)", ("project", "consult", "instruction", "2026-01-01"))
    connection.commit()
    connection.close()


def create_v9_database(path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE projects (id TEXT PRIMARY KEY, alias TEXT NOT NULL UNIQUE, root TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
        CREATE TABLE jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), workflow TEXT NOT NULL, profile TEXT NOT NULL, prompt TEXT NOT NULL, execution_plan_json TEXT NOT NULL, context_key TEXT NOT NULL, state TEXT NOT NULL, result_text TEXT NOT NULL DEFAULT '', target_id TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', config_revision TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, created_at TEXT NOT NULL, kind TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE context_sessions (project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, target_key TEXT NOT NULL, lane TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(project_id, context_key, role, target_key, lane));
        CREATE TABLE context_turns (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, prompt TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE target_health (target_id TEXT PRIMARY KEY, consecutive_failures INTEGER NOT NULL DEFAULT 0, circuit_open_until TEXT NOT NULL DEFAULT '', last_success_at TEXT NOT NULL DEFAULT '');
        CREATE INDEX jobs_state_idx ON jobs(state, created_at);
        PRAGMA user_version=9;
    """)
    connection.execute("INSERT INTO projects VALUES (?, ?, ?, ?)", ("project", "project", "/project", "2026-01-01"))
    connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("job", "project", "consult", "balanced", "prompt", "{}", "consult", "succeeded", "result text", "target", 2, "", "rev", "2026-01-01", "2026-01-02"))
    connection.commit()
    connection.close()


def table_columns(database: Database, table: str) -> set[str]:
    return database._columns(table)


def test_fresh_database_uses_v11_schema(tmp_path) -> None:
    database = Database(tmp_path / "openmcp.db")
    tables = {row["name"] for row in database._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert database._connection.execute("PRAGMA user_version").fetchone()[0] == 11
    assert table_columns(database, "projects") == {"id", "alias", "root", "created_at"}
    assert table_columns(database, "jobs") == {"id", "project_id", "workflow", "profile", "prompt", "execution_plan_json", "context_key", "state", "result_text", "target_id", "attempts", "error", "config_revision", "fresh_session", "created_at", "updated_at"}
    assert "job_stream_events" in tables
    assert "stages" not in tables and "artifacts" not in tables
    database.close()


def test_v6_migrates_to_v11_preserving_rows_and_support_data(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    create_v6_database(path)
    database = Database(path)
    assert database._connection.execute("PRAGMA user_version").fetchone()[0] == 11
    assert table_columns(database, "projects") == {"id", "alias", "root", "created_at"}
    assert table_columns(database, "jobs") == {"id", "project_id", "workflow", "profile", "prompt", "execution_plan_json", "context_key", "state", "result_text", "target_id", "attempts", "error", "config_revision", "fresh_session", "created_at", "updated_at"}
    assert database.project("project") and database.project("project").root == "/project"
    job = database.job("job")
    assert job and job.result.text == "result text" and job.target_id == "target" and job.attempts == 2
    assert job.config_revision == ""
    assert database.job_record("job")["fresh_session"] == 0
    assert database.events("job")[0]["kind"] == "job.queued"
    assert database._connection.execute("SELECT COUNT(*) FROM context_sessions").fetchone()[0] == 1
    assert database._connection.execute("SELECT COUNT(*) FROM context_turns").fetchone()[0] == 1
    assert database._connection.execute("SELECT COUNT(*) FROM target_health").fetchone()[0] == 1
    assert not {"projects_v6", "jobs_v6"} & {row["name"] for row in database._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    database.close()


def test_v5_migrates_to_v11_preserving_rows_and_support_data(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    create_v5_database(path)
    database = Database(path)
    assert database._connection.execute("PRAGMA user_version").fetchone()[0] == 11
    assert table_columns(database, "projects") == {"id", "alias", "root", "created_at"}
    assert table_columns(database, "jobs") == {"id", "project_id", "workflow", "profile", "prompt", "execution_plan_json", "context_key", "state", "result_text", "target_id", "attempts", "error", "config_revision", "fresh_session", "created_at", "updated_at"}
    assert database.project("project") and database.project("project").root == "/project"
    job = database.job("job")
    assert job and job.result.text == "result text" and job.target_id == "target" and job.attempts == 2
    assert database.job_record("job")["fresh_session"] == 0
    assert database.events("job")[0]["kind"] == "job.queued"
    assert database._connection.execute("SELECT COUNT(*) FROM context_sessions").fetchone()[0] == 1
    assert database._connection.execute("SELECT COUNT(*) FROM context_turns").fetchone()[0] == 1
    assert database._connection.execute("SELECT COUNT(*) FROM target_health").fetchone()[0] == 1
    assert not {"projects_v6", "jobs_v6"} & {row["name"] for row in database._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    database.close()


def test_reopening_v11_is_a_noop(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    first = Database(path)
    first.close()
    second = Database(path)
    assert second._connection.execute("PRAGMA user_version").fetchone()[0] == 11
    second.close()


def test_v9_migrates_to_v11_adding_fresh_session_column(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    create_v9_database(path)
    database = Database(path)
    assert database._connection.execute("PRAGMA user_version").fetchone()[0] == 11
    assert "fresh_session" in table_columns(database, "jobs")
    assert "job_stream_events" in {row["name"] for row in database._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    record = database.job_record("job")
    assert record and record["fresh_session"] == 0
    database.close()


def test_v8_migrates_to_v11_dropping_context_instructions_and_adding_fresh_session(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    create_v8_database(path)

    database = Database(path)
    tables = {row["name"] for row in database._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "context_instructions" not in tables
    assert database._connection.execute("PRAGMA user_version").fetchone()[0] == 11
    assert "fresh_session" in table_columns(database, "jobs")
    assert "job_stream_events" in tables
    record = database.job_record("job")
    assert record and record["fresh_session"] == 0
    database.close()



def test_create_job_persists_fresh_session_flag(tmp_path) -> None:
    database = Database(tmp_path / "openmcp.db")
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


def test_v5_migration_rolls_back_on_integrity_failure(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    create_v5_database(path, invalid_foreign_key=True)
    with pytest.raises(sqlite3.IntegrityError):
        Database(path)
    connection = sqlite3.connect(path)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
    assert {row[1] for row in connection.execute("PRAGMA table_info(projects)")} == {"id", "alias", "root", "head_commit", "clean", "created_at"}
    assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
    connection.close()


def test_legacy_jobs_collapse_to_historical_results(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    create_legacy_database(path)
    database = Database(path)
    completed, interrupted, queued, conflict = (database.job(value) for value in ("completed", "running", "queued", "conflict"))
    assert completed and completed.state == "succeeded"
    assert completed.result.text == "legacy response"
    assert completed.target_id == "legacy-target" and completed.attempts == 2
    assert interrupted and interrupted.state == "interrupted"
    assert queued and queued.state == "interrupted"
    assert conflict and conflict.state == "failed" and conflict.result.error == "conflict"
    assert database.events("completed")[0]["kind"] == "legacy.event"
    assert database._connection.execute("SELECT COUNT(*) FROM context_turns").fetchone()[0] == 1
    database.close()


def test_job_revision_survives_retry_without_plan_changes(tmp_path) -> None:
    database = Database(tmp_path / "openmcp.db")
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
    database = Database(tmp_path / "openmcp.db")
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


def test_context_includes_sessionless_turns_with_fixed_query_count(tmp_path) -> None:
    database = Database(tmp_path / "openmcp.db")
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
    database = Database(tmp_path / "openmcp.db")
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


def create_v10_database(path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE projects (id TEXT PRIMARY KEY, alias TEXT NOT NULL UNIQUE, root TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
        CREATE TABLE jobs (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), workflow TEXT NOT NULL, profile TEXT NOT NULL, prompt TEXT NOT NULL, execution_plan_json TEXT NOT NULL, context_key TEXT NOT NULL, state TEXT NOT NULL, result_text TEXT NOT NULL DEFAULT '', target_id TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', config_revision TEXT NOT NULL DEFAULT '', fresh_session INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE, created_at TEXT NOT NULL, kind TEXT NOT NULL, data_json TEXT NOT NULL);
        CREATE TABLE context_sessions (project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, target_key TEXT NOT NULL, lane TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY(project_id, context_key, role, target_key, lane));
        CREATE TABLE context_turns (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, context_key TEXT NOT NULL, role TEXT NOT NULL, target_id TEXT NOT NULL, prompt TEXT NOT NULL, response TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE target_health (target_id TEXT PRIMARY KEY, consecutive_failures INTEGER NOT NULL DEFAULT 0, circuit_open_until TEXT NOT NULL DEFAULT '', last_success_at TEXT NOT NULL DEFAULT '');
        CREATE INDEX jobs_state_idx ON jobs(state, created_at);
        CREATE INDEX events_job_idx ON events(job_id, id);
        CREATE INDEX context_turns_stream_idx ON context_turns(project_id, context_key, role, id);
        PRAGMA user_version=10;
    """)
    connection.execute("INSERT INTO projects VALUES (?, ?, ?, ?)", ("project", "project", "/project", "2026-01-01"))
    connection.execute("INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("job", "project", "consult", "balanced", "prompt", "{}", "consult", "succeeded", "result text", "target", 2, "", "rev", 0, "2026-01-01", "2026-01-02"))
    connection.execute("INSERT INTO events(job_id, created_at, kind, data_json) VALUES (?, ?, ?, ?)", ("job", "2026-01-01", "job.queued", "{}"))
    connection.commit()
    connection.close()


def test_v10_migrates_to_v11_adding_stream_events_table(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    create_v10_database(path)
    database = Database(path)
    assert database._connection.execute("PRAGMA user_version").fetchone()[0] == 11
    assert "job_stream_events" in {row["name"] for row in database._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected_cols = {
        "id", "job_id", "created_at", "attempt", "target_id",
        "backend", "kind", "entity_id", "parent_entity_id",
        "data_json", "size_bytes",
    }
    assert table_columns(database, "job_stream_events") == expected_cols
    indices = {row["name"] for row in database._connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "job_stream_events_job_idx" in indices
    job = database.job("job")
    assert job and job.result.text == "result text"
    database.close()


def test_append_stream_events_persists_batch_transactionally(tmp_path) -> None:
    database = Database(tmp_path / "openmcp.db")
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
    database = Database(tmp_path / "openmcp.db")
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
    database = Database(tmp_path / "openmcp.db")
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
    database = Database(tmp_path / "openmcp.db")
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
    path = tmp_path / "openmcp.db"
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
    assert reopened._connection.execute("PRAGMA user_version").fetchone()[0] == 11
    assert reopened.stream_high_water("job-1") == event_id
    assert reopened.stream_retained_from("job-1") == event_id
    events = reopened.stream_events("job-1", after=0)
    assert len(events) == 1
    assert events[0].id == event_id
    assert events[0].data == {"text": "persisted token"}
    reopened.close()


def test_stream_totals_computes_event_count_and_bytes(tmp_path) -> None:
    database = Database(tmp_path / "openmcp.db")
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
    database = Database(tmp_path / "openmcp.db")
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
    database = Database(tmp_path / "openmcp.db")
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
