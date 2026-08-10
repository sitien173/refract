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


def table_columns(database: Database, table: str) -> set[str]:
    return database._columns(table)


def test_fresh_database_uses_v6_schema(tmp_path) -> None:
    database = Database(tmp_path / "openmcp.db")
    tables = {row["name"] for row in database._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert database._connection.execute("PRAGMA user_version").fetchone()[0] == 6
    assert table_columns(database, "projects") == {"id", "alias", "root", "created_at"}
    assert table_columns(database, "jobs") == {"id", "project_id", "workflow", "profile", "prompt", "execution_plan_json", "context_key", "state", "result_text", "target_id", "attempts", "error", "created_at", "updated_at"}
    assert "stages" not in tables and "artifacts" not in tables
    database.close()


def test_v5_migrates_to_v6_preserving_rows_and_support_data(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    create_v5_database(path)
    database = Database(path)
    assert database._connection.execute("PRAGMA user_version").fetchone()[0] == 6
    assert table_columns(database, "projects") == {"id", "alias", "root", "created_at"}
    assert table_columns(database, "jobs") == {"id", "project_id", "workflow", "profile", "prompt", "execution_plan_json", "context_key", "state", "result_text", "target_id", "attempts", "error", "created_at", "updated_at"}
    assert database.project("project") and database.project("project").root == "/project"
    job = database.job("job")
    assert job and job.result.text == "result text" and job.target_id == "target" and job.attempts == 2
    assert database.events("job")[0]["kind"] == "job.queued"
    assert database._connection.execute("SELECT COUNT(*) FROM context_sessions").fetchone()[0] == 1
    assert database._connection.execute("SELECT COUNT(*) FROM context_turns").fetchone()[0] == 1
    assert database._connection.execute("SELECT COUNT(*) FROM target_health").fetchone()[0] == 1
    assert not {"projects_v6", "jobs_v6"} & {row["name"] for row in database._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    database.close()


def test_reopening_v6_is_a_noop(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    first = Database(path)
    first.close()
    second = Database(path)
    assert second._connection.execute("PRAGMA user_version").fetchone()[0] == 6
    second.close()


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
