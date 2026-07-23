from __future__ import annotations

import inspect
import json
import sqlite3

from openmcp.database import Database


def test_create_job_signature_omits_commit_message() -> None:
    assert "commit_message" not in inspect.signature(Database.create_job).parameters


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


def test_fresh_database_uses_job_level_schema(tmp_path) -> None:
    database = Database(tmp_path / "openmcp.db")
    columns = {row["name"] for row in database._connection.execute("PRAGMA table_info(jobs)")}
    tables = {row["name"] for row in database._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert database._connection.execute("PRAGMA user_version").fetchone()[0] == 5
    assert {"prompt", "commit_message", "result_text", "target_id", "attempts"} <= columns
    assert {"workflow_json", "parent_job_id", "branch", "worktree"}.isdisjoint(columns)
    assert "stages" not in tables and "artifacts" not in tables
    database.close()


def test_create_job_uses_empty_commit_message_default(tmp_path) -> None:
    database = Database(tmp_path / "openmcp.db")
    project = database.upsert_project(project_id="project", alias="project", root="/project", head_commit="", clean=True)
    database.create_job(
        job_id="job",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="inspect",
        execution_plan_json="{}",
        context_key="consult",
    )
    value = database._connection.execute("SELECT commit_message FROM jobs WHERE id='job'").fetchone()[0]
    assert value == ""
    database.close()


def test_legacy_jobs_collapse_to_historical_results(tmp_path) -> None:
    path = tmp_path / "openmcp.db"
    create_legacy_database(path)
    database = Database(path)
    completed, interrupted, queued, conflict = (database.job(value) for value in ("completed", "running", "queued", "conflict"))
    assert completed and completed.state == "succeeded"
    assert completed.result.text == "legacy response" and completed.result.commit == "result-sha"
    assert completed.target_id == "legacy-target" and completed.attempts == 2
    assert interrupted and interrupted.state == "interrupted"
    assert queued and queued.state == "interrupted"
    assert conflict and conflict.state == "failed" and conflict.result.error == "conflict"
    assert database.events("completed")[0]["kind"] == "legacy.event"
    assert database._connection.execute("SELECT COUNT(*) FROM context_turns").fetchone()[0] == 1
    database.close()
