"""Schema v1: one DDL, `open` for a fresh file, and the rename of any other schema to `.bak`."""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

from refract.models import FAILURE_KINDS, JobState

log = logging.getLogger("refract.database")
SCHEMA_VERSION = 1
ATTEMPT_REASONS = ("initial", "retry", "fresh_session", "fallback")
QUESTION_STATES = ("open", "answered", "expired")
CARD_STATES = ("todo", "in_progress", "in_review", "done", "cancelled")
SIDECARS = ("", "-wal", "-shm")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


_STATES = _in(get_args(JobState))
DDL = f"""
BEGIN;
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
    target_pin TEXT NOT NULL DEFAULT '',
    session TEXT NOT NULL,
    fresh INTEGER NOT NULL DEFAULT 0 CHECK (fresh IN (0, 1)),
    from_job TEXT NOT NULL DEFAULT '',
    prompt TEXT,
    state TEXT NOT NULL CHECK (state IN ({_STATES})),
    failure_kind TEXT CHECK (failure_kind IS NULL OR failure_kind IN ({_in(FAILURE_KINDS)})),
    error TEXT NOT NULL DEFAULT '',
    next_target TEXT NOT NULL DEFAULT '',
    result TEXT,
    events_committed INTEGER NOT NULL DEFAULT 0 CHECK (events_committed >= 0),
    content_pruned INTEGER NOT NULL DEFAULT 0 CHECK (content_pruned IN (0, 1)),
    pgid INTEGER,
    plan_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE attempts (
    id INTEGER PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL CHECK (seq >= 1),
    reason TEXT NOT NULL CHECK (reason IN ({_in(ATTEMPT_REASONS)})),
    target TEXT NOT NULL,
    backend TEXT NOT NULL DEFAULT '',
    model TEXT,
    state TEXT NOT NULL CHECK (state IN ({_STATES})),
    failure_kind TEXT CHECK (failure_kind IS NULL OR failure_kind IN ({_in(FAILURE_KINDS)})),
    replay_safe INTEGER NOT NULL DEFAULT 0 CHECK (replay_safe IN (0, 1)),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    duration_ms INTEGER,
    tok_context_used INTEGER,
    tok_context_window INTEGER,
    tok_input INTEGER,
    tok_output INTEGER,
    tok_cache_read INTEGER,
    tok_cache_write INTEGER,
    UNIQUE (job_id, seq)
);
CREATE TABLE questions (
    id INTEGER PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    attempt_id INTEGER REFERENCES attempts(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ({_in(QUESTION_STATES)})),
    answer TEXT,
    asked_at TEXT NOT NULL,
    answered_at TEXT
);
CREATE TABLE session_routes (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session TEXT NOT NULL,
    workflow TEXT NOT NULL,
    sticky_target TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (project_id, session, workflow)
);
CREATE TABLE backend_sessions (
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
    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    circuit_open_until TEXT NOT NULL DEFAULT '',
    last_success_at TEXT NOT NULL DEFAULT '',
    cooldown_s INTEGER NOT NULL DEFAULT 0 CHECK (cooldown_s >= 0),
    probe_job_id TEXT NOT NULL DEFAULT ''
);
CREATE TABLE cards (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL CHECK (state IN ({_in(CARD_STATES)})),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE card_jobs (
    card_id TEXT NOT NULL REFERENCES cards(id),
    job_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (card_id, job_id)
);
CREATE TABLE card_moves (
    id INTEGER PRIMARY KEY,
    card_id TEXT NOT NULL REFERENCES cards(id),
    from_state TEXT CHECK (from_state IS NULL OR from_state IN ({_in(CARD_STATES)})),
    to_state TEXT NOT NULL CHECK (to_state IN ({_in(CARD_STATES)})),
    note TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL
);
CREATE INDEX jobs_state_idx ON jobs(state, created_at);
CREATE INDEX jobs_project_idx ON jobs(project_id, updated_at);
CREATE INDEX attempts_job_idx ON attempts(job_id, seq);
CREATE INDEX questions_job_idx ON questions(job_id, state);
CREATE INDEX cards_project_idx ON cards(project_id, updated_at);
CREATE INDEX card_moves_card_idx ON card_moves(card_id, id);
CREATE INDEX card_jobs_job_idx ON card_jobs(job_id);
PRAGMA user_version={SCHEMA_VERSION};
COMMIT;
"""


def initialize(path: Path) -> None:
    """Make `path` a schema v1 database; rename a database on any other user_version first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    version = _probe_version(path)
    if version == SCHEMA_VERSION:
        return
    if version is not None:
        _retire(path, version)
    with closing(sqlite3.connect(path, isolation_level=None)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            connection.executescript(DDL)
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def _probe_version(path: Path) -> int | None:
    """Read user_version from a scratch copy so the database bytes stay untouched; None when missing or empty."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    for attempt in range(3):
        try:
            return _probe_scratch_copy(path)
        except FileNotFoundError:
            # A closing writer checkpointed the -wal into the main file and deleted it; recopy.
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def _probe_scratch_copy(path: Path) -> int:
    with tempfile.TemporaryDirectory(prefix=".version-probe-", dir=path.parent) as scratch:
        copy = Path(scratch) / "probe.db"
        shutil.copyfile(path, copy)
        wal = Path(f"{path}-wal")
        if wal.exists():
            shutil.copyfile(wal, Path(f"{copy}-wal"))
        with closing(sqlite3.connect(f"{copy.as_uri()}?mode=ro", uri=True)) as probe:
            return int(probe.execute("PRAGMA user_version").fetchone()[0])


def _retire(path: Path, version: int) -> None:
    """Back up the database and its -wal and -shm to `<name>.<version>.bak*`, then unlink the originals.

    Every name in SIDECARS is claimed for the backup with mode "xb", an empty file standing in for an absent source
    sidecar. Any existing entry, even a dangling symlink, fails with FileExistsError; the copies this attempt made are
    removed and the whole set retries under the next counter. Originals are unlinked only after every copy and the
    parent directory are fsynced. No existing file is overwritten.
    """
    present = [suffix for suffix in SIDECARS if os.path.lexists(f"{path}{suffix}")]
    counter = 0
    while True:
        backup = f"{path}.{version}.bak" + (f".{counter}" if counter else "")
        counter += 1
        created: list[str] = []
        try:
            for suffix in SIDECARS:
                _copy_exclusive(f"{path}{suffix}" if suffix in present else None, f"{backup}{suffix}", created)
        except BaseException as exc:
            for name in created:
                os.unlink(name)
            if isinstance(exc, FileExistsError):
                continue
            raise
        break
    _fsync_directory(path.parent)
    # A crash between unlinks leaves the main file beside a complete durable backup; a later backup of it loses nothing.
    for suffix in reversed(present):
        os.unlink(f"{path}{suffix}")
    log.warning(
        "Backed up database with schema %s to %s and replaced it with a new database", version, backup,
        extra={"event": "database.retired", "database": path.as_posix(), "schema_version": version, "backup": backup},
    )


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":  # Windows cannot open a directory for fsync; NTFS journals metadata.
        return
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _copy_exclusive(src: str | None, dst: str, created: list[str]) -> None:
    with open(dst, "xb") as out:
        created.append(dst)
        if src is not None:
            with open(src, "rb") as source:
                shutil.copyfileobj(source, out)
        out.flush()
        os.fsync(out.fileno())
