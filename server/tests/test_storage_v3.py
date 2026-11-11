"""Phase 5 storage contract: fresh v3 schema, v2 retirement, flat token columns, result files."""

from __future__ import annotations

import json
import os
from contextlib import closing
import shutil
import sqlite3
import uuid
from pathlib import Path

import pytest

import refract.database as database_module
from refract.database import Database

V3_TABLES = {"projects", "jobs", "sessions", "target_sessions", "target_health", "cards", "card_jobs", "card_moves", "job_metrics", "telemetry_outbox"}
V3_COLUMNS = {
    "job_metrics": {"job_id", "finished_at", "profile", "workflow", "target", "backend", "model", "state", "failure_kind", "duration_ms", "tok_input", "tok_output", "tok_cache_read", "tok_cache_write", "attempts", "skipped_targets", "retry_of"},
    "telemetry_outbox": {"id", "event_key", "created_at", "payload", "send_attempts", "next_attempt_at"},
    "projects": {"id", "root", "created_at"},
    "jobs": {
        "id", "project_id", "workflow", "profile", "target", "session", "fresh", "prompt", "state",
        "retry_of", "failure_kind", "error", "model", "duration_ms", "pgid",
        "tok_context_used", "tok_context_window", "tok_input", "tok_output", "tok_cache_read", "tok_cache_write",
        "created_at", "started_at", "finished_at", "updated_at", "execution_plan_json",
    },
    "sessions": {"project_id", "session", "workflow", "sticky_target", "updated_at"},
    "target_sessions": {"project_id", "session", "workflow", "target_key", "backend_session_id", "updated_at"},
    "cards": {"id", "project_id", "title", "body", "state", "created_at", "updated_at"},
    "card_jobs": {"card_id", "job_id", "linked_at"},
    "card_moves": {"id", "card_id", "from_state", "to_state", "note", "at"},
}
SCHEMA_18_DDL = """
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    root TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    workflow TEXT NOT NULL,
    profile TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    session TEXT NOT NULL,
    fresh INTEGER NOT NULL DEFAULT 0,
    prompt TEXT NOT NULL,
    state TEXT NOT NULL,
    retry_of TEXT NOT NULL DEFAULT '',
    failure_kind TEXT,
    error TEXT NOT NULL DEFAULT '',
    model TEXT,
    duration_ms INTEGER,
    pgid INTEGER,
    tok_context_used INTEGER,
    tok_context_window INTEGER,
    tok_input INTEGER,
    tok_output INTEGER,
    tok_cache_read INTEGER,
    tok_cache_write INTEGER,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL,
    execution_plan_json TEXT NOT NULL
);
CREATE TABLE sessions (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session TEXT NOT NULL,
    workflow TEXT NOT NULL,
    sticky_target TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, session, workflow)
);
CREATE TABLE target_sessions (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session TEXT NOT NULL,
    workflow TEXT NOT NULL,
    target_key TEXT NOT NULL,
    backend_session_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, session, workflow, target_key)
);
CREATE TABLE target_health (
    target_id TEXT PRIMARY KEY,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    circuit_open_until TEXT NOT NULL DEFAULT '',
    last_success_at TEXT NOT NULL DEFAULT '',
    cooldown_s INTEGER NOT NULL DEFAULT 0,
    probe_job_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX jobs_state_idx ON jobs(state, created_at);
CREATE INDEX jobs_project_idx ON jobs(project_id, updated_at);
"""
TOKEN_COLUMNS = ("tok_context_used", "tok_context_window", "tok_input", "tok_output", "tok_cache_read", "tok_cache_write")


def _tables(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    return {row[0] for row in rows}


def _columns(path: Path, table: str) -> set[str]:
    with sqlite3.connect(path) as connection:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _crash_snapshot(source_dir: Path, target: Path) -> None:
    """Copy a WAL database with uncheckpointed rows and live -wal and -shm files, as a crashed v2 daemon leaves it."""
    source = source_dir / "legacy.db"
    writer = sqlite3.connect(source)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, kind TEXT)")
    writer.executemany("INSERT INTO events(kind) VALUES (?)", [("a",), ("b",), ("c",)])
    writer.execute("PRAGMA user_version=16")
    writer.commit()
    for suffix in ("", "-wal", "-shm"):
        shutil.copyfile(f"{source}{suffix}", f"{target}{suffix}")
    writer.close()


def _schema_18(path: Path) -> str:
    """Create a schema 18 database holding one job; return the job ID."""
    job_id = str(uuid.uuid4())
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(SCHEMA_18_DDL)
        connection.execute("INSERT INTO projects(id, root, created_at) VALUES ('p1', '/r', 't0')")
        connection.execute(
            "INSERT INTO jobs(id, project_id, workflow, profile, prompt, state, session, created_at, updated_at, execution_plan_json) "
            "VALUES (?, 'p1', 'implement', 'default', 'hello', 'succeeded', 's', 't1', 't2', '{}')",
            (job_id,),
        )
        connection.execute(
            "UPDATE jobs SET target='target-a', execution_plan_json=? WHERE id=?",
            ('{"targets":[{"id":"target-a","backend":"codex"}]}', job_id),
        )
        connection.execute(
            "INSERT INTO jobs(id, project_id, workflow, profile, prompt, state, session, created_at, updated_at, execution_plan_json) "
            "VALUES ('queued-job', 'p1', 'implement', 'default', 'hello', 'queued', 's2', 't1', 't2', '{}')"
        )
        connection.execute("PRAGMA user_version=18")
        connection.commit()
    return job_id


def _schema_19(path: Path) -> str:
    job_id = _schema_18(path)
    with closing(sqlite3.connect(path)) as connection:
        for statement in database_module._CARD_DDL:
            connection.execute(statement)
        connection.execute("PRAGMA user_version=19")
        connection.commit()
    return job_id


def _job_rows(path: Path) -> list[tuple]:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("SELECT * FROM jobs ORDER BY id").fetchall()


def _user_version(path: Path) -> int:
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute("PRAGMA user_version").fetchone()[0]


def _new_job(database: Database, tmp_path: Path) -> str:
    project = database.upsert_project(project_id=str(uuid.uuid4()), root=tmp_path.as_posix())
    job_id = str(uuid.uuid4())
    database.create_job(
        job_id=job_id, project_id=project.id, workflow="implement", profile="default",
        prompt="p", execution_plan_json="{}", session="s",
    )
    return job_id


def test_v2_database_is_renamed_with_wal_and_shm_and_fresh_schema_created(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    path = tmp_path / "refract.db"
    _crash_snapshot(scratch, path)
    original = {suffix: Path(f"{path}{suffix}").read_bytes() for suffix in ("", "-wal", "-shm")}

    Database(path)

    for suffix, content in original.items():
        assert Path(f"{path}{suffix}.v2.bak").read_bytes() == content
    assert _tables(path) == V3_TABLES
    restored = tmp_path / "restored"
    restored.mkdir()
    for suffix in ("", "-wal", "-shm"):
        shutil.copyfile(f"{path}{suffix}.v2.bak", restored / f"old.db{suffix}")
    with sqlite3.connect(restored / "old.db") as connection:
        assert connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3


def test_v3_database_is_reopened_untouched(tmp_path: Path) -> None:
    path = tmp_path / "refract.db"
    job_id = _new_job(Database(path), tmp_path)

    reopened = Database(path)

    assert not list(tmp_path.glob("*.v2.bak"))
    assert reopened.job_record(job_id) is not None


def test_newer_schema_database_is_refused_without_changes(tmp_path: Path) -> None:
    path = tmp_path / "refract.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE future (id INTEGER)")
        connection.execute("PRAGMA user_version=999")
    before = path.read_bytes()
    try:
        Database(path)
    except ValueError as exc:
        assert "newer" in str(exc)
    else:
        raise AssertionError("a newer schema must be refused")
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.v2.bak"))


def test_fresh_schema_has_exact_v3_tables_and_columns(tmp_path: Path) -> None:
    path = tmp_path / "refract.db"
    Database(path)

    assert _tables(path) == V3_TABLES
    for table, columns in V3_COLUMNS.items():
        assert _columns(path, table) == columns, table


def test_finish_stores_flat_tokens_and_leaves_unknown_counters_null(tmp_path: Path) -> None:
    database = Database(tmp_path / "refract.db")
    known = _new_job(database, tmp_path)
    unknown = _new_job(database, tmp_path)

    database.finish_job(known, "succeeded", text="done", target="primary", model="m", duration_ms=12, tokens={"input": 5, "output": 7, "cache_read": 0})
    database.finish_job(unknown, "failed", target="primary", failure_kind="transient", error="boom")

    known_row = database.job_record(known)
    unknown_row = database.job_record(unknown)
    assert {column: known_row[column] for column in TOKEN_COLUMNS} == {
        "tok_context_used": None, "tok_context_window": None, "tok_input": 5,
        "tok_output": 7, "tok_cache_read": 0, "tok_cache_write": None,
    }
    assert all(unknown_row[column] is None for column in TOKEN_COLUMNS)
    assert (known_row["model"], known_row["duration_ms"], known_row["failure_kind"]) == ("m", 12, None)
    assert (unknown_row["failure_kind"], unknown_row["error"]) == ("transient", "boom")


def test_job_view_reads_result_text_from_result_file(tmp_path: Path) -> None:
    database = Database(tmp_path / "refract.db")
    job_id = _new_job(database, tmp_path)
    database.finish_job(job_id, "succeeded", text="full answer", target="primary")

    view = database.job_view(database.job_record(job_id))

    assert database.result_path(job_id).read_text(encoding="utf-8") == "full answer"
    assert view.result.text == "full answer"
    assert view.result.tokens == {"context_used": None, "context_window": None, "input": None, "output": None, "cache_read": None, "cache_write": None}


def test_stream_events_append_to_private_jsonl_file(tmp_path: Path) -> None:
    database = Database(tmp_path / "refract.db")
    job_id = _new_job(database, tmp_path)

    database.append_stream(job_id, [{"kind": "text", "data": {"text": "a"}}, {"kind": "text", "data": {"text": "b"}}])
    database.append_stream(job_id, [{"kind": "tool", "data": {"name": "c"}}])

    path = database.stream_path(job_id)
    assert path == tmp_path / "streams" / f"{job_id}.jsonl"
    # File modes are POSIX-only.
    assert os.name == "nt" or path.stat().st_mode & 0o777 == 0o600
    assert os.name == "nt" or (tmp_path / "streams").stat().st_mode & 0o777 == 0o700
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [line["kind"] for line in lines] == ["text", "text", "tool"]
    assert not hasattr(database, "stream_tail")


def test_result_file_is_private_and_pruning_deletes_job_stream_and_result(tmp_path: Path) -> None:
    database = Database(tmp_path / "refract.db")
    job_id = _new_job(database, tmp_path)
    database.append_stream(job_id, [{"kind": "text", "data": {"text": "a"}}])
    database.finish_job(job_id, "succeeded", text="answer", target="primary")
    assert os.name == "nt" or database.result_path(job_id).stat().st_mode & 0o777 == 0o600  # file modes are POSIX-only

    database.prune_history("9999-01-01T00:00:00Z")

    assert database.job_record(job_id) is None
    assert not database.stream_path(job_id).exists()
    assert not database.result_path(job_id).exists()


def test_schema_18_database_upgrades_to_21_and_keeps_job_rows(tmp_path: Path) -> None:
    path = tmp_path / "refract.db"
    job_id = _schema_18(path)
    before = _job_rows(path)

    Database(path).close()

    assert _user_version(path) == 21
    assert _job_rows(path) == before
    assert before[0][0] == job_id
    with closing(sqlite3.connect(path)) as connection:
        metric = connection.execute(
            "SELECT job_id, finished_at, attempts, skipped_targets FROM job_metrics"
        ).fetchone()
    assert metric == (job_id, "t2", None, None)
    with closing(sqlite3.connect(path)) as connection:
        all_metrics = connection.execute("SELECT job_id FROM job_metrics").fetchall()
        resolved = connection.execute(
            "SELECT target, backend FROM job_metrics WHERE job_id=?", (job_id,),
        ).fetchone()
    assert all_metrics == [(job_id,)]
    assert resolved == ("target-a", "codex")
    assert _tables(path) == V3_TABLES


def test_schema_19_database_backfills_terminal_jobs_and_skips_nonterminal(tmp_path: Path) -> None:
    path = tmp_path / "refract.db"
    job_id = _schema_19(path)

    Database(path).close()

    assert _user_version(path) == 21
    with closing(sqlite3.connect(path)) as connection:
        rows = connection.execute(
            "SELECT job_id, finished_at, backend, attempts, skipped_targets FROM job_metrics"
        ).fetchall()
    assert rows == [(job_id, "t2", "codex", None, None)]


def test_failed_schema_19_migration_rolls_back_without_new_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "refract.db"
    _schema_19(path)
    monkeypatch.setattr(database_module, "_METRICS_DDL", (*database_module._METRICS_DDL[:1], "CREATE TABLE broken ("))

    with pytest.raises(sqlite3.Error):
        Database(path)

    assert _user_version(path) == 19
    assert "job_metrics" not in _tables(path)
    assert "telemetry_outbox" not in _tables(path)


def test_failed_schema_20_step_from_schema_18_leaves_schema_18_without_new_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "refract.db"
    _schema_18(path)
    before = _job_rows(path)
    monkeypatch.setattr(database_module, "_METRICS_DDL", (*database_module._METRICS_DDL[:1], "CREATE TABLE broken ("))

    with pytest.raises(sqlite3.Error):
        Database(path)

    assert _user_version(path) == 18
    assert _job_rows(path) == before
    assert not {"cards", "job_metrics", "telemetry_outbox"} & set(_tables(path))


def test_schema_18_upgrade_succeeds_with_existing_backup_and_creates_none(tmp_path: Path) -> None:
    path = tmp_path / "refract.db"
    _schema_18(path)
    (tmp_path / "refract.db.v2.bak").write_bytes(b"old")

    Database(path).close()

    assert _user_version(path) == 21
    assert sorted(p.name for p in tmp_path.glob("*.v2.bak")) == ["refract.db.v2.bak"]
    assert (tmp_path / "refract.db.v2.bak").read_bytes() == b"old"


def test_failed_schema_18_migration_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "refract.db"
    _schema_18(path)
    before = _job_rows(path)
    first = database_module._CARD_DDL[0]
    monkeypatch.setattr(database_module, "_CARD_DDL", (first, "CREATE TABLE broken ("))

    with pytest.raises(sqlite3.Error):
        Database(path)

    assert _user_version(path) == 18
    assert _job_rows(path) == before
    assert "cards" not in _tables(path)


def test_schema_21_database_reopens_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "refract.db"
    _schema_18(path)
    Database(path).close()
    before = _job_rows(path)

    Database(path).close()

    assert _user_version(path) == 21
    assert _job_rows(path) == before
    assert not list(tmp_path.glob("*.v2.bak"))


def test_fresh_database_reports_schema_21(tmp_path: Path) -> None:
    path = tmp_path / "refract.db"
    Database(path).close()

    assert _user_version(path) == 21


def test_cards_survive_close_and_reopen(tmp_path: Path) -> None:
    path = tmp_path / "refract.db"
    database = Database(path)
    project = database.upsert_project(project_id="p1", root=tmp_path.as_posix())
    with database.transaction():
        database._connection.execute(
            "INSERT INTO cards(id, project_id, title, state, created_at, updated_at) VALUES ('c1', ?, 't', 'todo', 'a', 'a')",
            (project.id,),
        )
    database.close()

    reopened = Database(path)

    assert reopened._connection.execute("SELECT id FROM cards").fetchall()[0]["id"] == "c1"


def test_card_jobs_has_only_the_foreign_key_to_cards(tmp_path: Path) -> None:
    path = tmp_path / "refract.db"
    Database(path).close()

    with closing(sqlite3.connect(path)) as connection:
        keys = connection.execute("PRAGMA foreign_key_list(card_jobs)").fetchall()

    assert [key[2] for key in keys] == ["cards"]
