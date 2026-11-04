"""Phase 5 storage contract: fresh v3 schema, v2 retirement, flat token columns, result files."""

from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from pathlib import Path

from refract.database import Database

V3_TABLES = {"projects", "jobs", "sessions", "target_sessions", "target_health"}
V3_COLUMNS = {
    "projects": {"id", "root", "created_at"},
    "jobs": {
        "id", "project_id", "workflow", "profile", "target", "session", "fresh", "prompt", "state",
        "retry_of", "failure_kind", "error", "model", "duration_ms", "pgid",
        "tok_context_used", "tok_context_window", "tok_input", "tok_output", "tok_cache_read", "tok_cache_write",
        "created_at", "started_at", "finished_at", "updated_at", "execution_plan_json",
    },
    "sessions": {"project_id", "session", "workflow", "sticky_target", "updated_at"},
    "target_sessions": {"project_id", "session", "workflow", "target_key", "backend_session_id", "updated_at"},
}
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
    assert path.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "streams").stat().st_mode & 0o777 == 0o700
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [line["kind"] for line in lines] == ["text", "text", "tool"]
    assert not hasattr(database, "stream_tail")


def test_result_file_is_private_and_pruning_deletes_job_stream_and_result(tmp_path: Path) -> None:
    database = Database(tmp_path / "refract.db")
    job_id = _new_job(database, tmp_path)
    database.append_stream(job_id, [{"kind": "text", "data": {"text": "a"}}])
    database.finish_job(job_id, "succeeded", text="answer", target="primary")
    assert database.result_path(job_id).stat().st_mode & 0o777 == 0o600

    database.prune_history("9999-01-01T00:00:00Z")

    assert database.job_record(job_id) is None
    assert not database.stream_path(job_id).exists()
    assert not database.result_path(job_id).exists()
