"""SQLite persistence for direct project jobs."""

from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import tempfile
import threading
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from refract.config_inspection import utc_now
from refract.logging_setup import get_logger
from refract.models import TERMINAL_STATES, JobResult, JobView, ProjectView
from refract.product_telemetry import MAX_OUTBOX_AGE_DAYS, MAX_OUTBOX_ROWS

log = get_logger("database")
_BEGIN_IMMEDIATE = "BEGIN IMMEDIATE"
_JOURNAL_MODE_WAL = "PRAGMA journal_mode=WAL"
_SCHEMA_VERSION = 21
_TOKEN_COLUMNS = (
    ("context_used", "tok_context_used"),
    ("context_window", "tok_context_window"),
    ("input", "tok_input"),
    ("output", "tok_output"),
    ("cache_read", "tok_cache_read"),
    ("cache_write", "tok_cache_write"),
)
_METRICS_DDL = (
    """CREATE TABLE job_metrics (
    job_id TEXT PRIMARY KEY,
    finished_at TEXT NOT NULL,
    profile TEXT NOT NULL DEFAULT '',
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
_CARD_DDL = (
    """CREATE TABLE cards (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL CHECK (state IN ('todo','in_progress','in_review','done','cancelled')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)""",
    """CREATE TABLE card_jobs (
    card_id TEXT NOT NULL REFERENCES cards(id),
    job_id TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (card_id, job_id)
)""",
    """CREATE TABLE card_moves (
    id INTEGER PRIMARY KEY,
    card_id TEXT NOT NULL REFERENCES cards(id),
    from_state TEXT,
    to_state TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    at TEXT NOT NULL
)""",
    "CREATE INDEX cards_project_idx ON cards(project_id, updated_at)",
    "CREATE INDEX card_moves_card_idx ON card_moves(card_id, id)",
)
_CARD_TITLE_MAX = 200
_CARD_BODY_MAX = 4000
_CARD_NOTE_MAX = 1000
_CARD_CALL_LINKS_MAX = 16
_CARD_LINKS_MAX = 64
_CARD_EDGES = {
    "todo": {"in_progress", "cancelled"},
    "in_progress": {"in_review", "cancelled"},
    "in_review": {"done", "in_progress", "cancelled"},
    "done": set(),
    "cancelled": set(),
}
_CARD_SELECT = (
    "SELECT c.id, c.project_id, p.root AS project_root, c.title, c.state, c.created_at, c.updated_at "
    "FROM cards c JOIN projects p ON p.id=c.project_id"
)
_SCHEMA = """
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
""" + "".join(f"{statement};\n" for statement in (*_CARD_DDL, *_METRICS_DDL))


def _backend_for_target(plan_json: str, target: str) -> str:
    try:
        targets = json.loads(plan_json).get("targets", [])
        if isinstance(targets, list):
            backend = next((item.get("backend") for item in targets
                            if isinstance(item, dict) and item.get("id") == target), "")
            return backend if isinstance(backend, str) else ""
    except (ValueError, TypeError, AttributeError):
        pass
    return ""


def _token_values(tokens: dict[str, int | None] | None) -> tuple[int | None, ...]:
    """Return token counters in column order; a missing key stays NULL."""
    tokens = tokens or {}
    return tuple(tokens.get(key) for key, _column in _TOKEN_COLUMNS)


def encode_cursor(created_at: str, job_id: str) -> str:
    raw = json.dumps([created_at, job_id]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
        if (
            isinstance(data, list)
            and len(data) == 2
            and isinstance(data[0], str)
            and isinstance(data[1], str)
        ):
            return data[0], data[1]
    except Exception:
        pass
    raise ValueError("Invalid cursor")


def _card_job_ids(job_ids: Sequence[str]) -> list[str]:
    """Validate the per-call job IDs and drop duplicates, keeping order."""
    if len(job_ids) > _CARD_CALL_LINKS_MAX:
        raise CardError("invalid_request", f"at most {_CARD_CALL_LINKS_MAX} job_ids per call")
    if any(not 1 <= len(job_id) <= 64 for job_id in job_ids):
        raise CardError("invalid_request", "each job ID must be 1 to 64 characters")
    return list(dict.fromkeys(job_ids))


class CardError(ValueError):
    """A card request the store refuses; code is one of unknown_card, invalid_state, unknown_job, invalid_request."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self.results_dir = path.parent / "results"
        self.streams_dir = path.parent / "streams"
        self._local = threading.local()
        self._connections: list[sqlite3.Connection] = []
        self._connections_lock = threading.Lock()
        self._closed = False
        try:
            self._initialize()
        except Exception:
            self.close()
            raise
        log.info(
            "Database opened",
            extra={"event": "database.opened", "database": path.as_posix()},
        )

    @property
    def _connection(self) -> sqlite3.Connection:
        if self._closed:
            raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
        connection = getattr(self._local, "connection", None)
        if connection is None:
            with self._connections_lock:
                if self._closed:
                    raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
                # Each thread exclusively uses its own connection. Disabling
                # affinity permits the application owner to close all workers.
                connection = sqlite3.connect(self._path, check_same_thread=False)
                connection.row_factory = sqlite3.Row
                try:
                    connection.execute("PRAGMA synchronous=NORMAL")
                    connection.execute("PRAGMA foreign_keys=ON")
                except Exception:
                    connection.close()
                    raise
                self._connections.append(connection)
                self._local.connection = connection
        return connection

    @contextmanager
    def transaction(self):
        with self._connection:
            self._connection.execute(_BEGIN_IMMEDIATE)
            yield

    def close(self) -> None:
        with self._connections_lock:
            self._closed = True
            for connection in self._connections:
                connection.close()
            self._connections.clear()
        log.info("Database closed", extra={"event": "database.closed"})

    def _initialize(self) -> None:
        version = self._probe_version()
        if version is not None and version > _SCHEMA_VERSION:
            raise ValueError(
                f"The database at {self._path} uses schema {version}, which is newer than this Refract "
                f"supports ({_SCHEMA_VERSION}). The database was not modified."
            )
        if version in (18, 19):
            self._migrate_from_18_or_19(version)
        elif version == 20:
            self._migrate_to_21()
        elif version != _SCHEMA_VERSION:
            if version is not None:
                self._retire(version)
            self._create_schema()
        self._connection.execute(_JOURNAL_MODE_WAL)
        log.debug(
            "Database schema is current",
            extra={"event": "database.schema_ready", "schema_version": _SCHEMA_VERSION},
        )

    def _create_schema(self) -> None:
        self._connection.execute(_JOURNAL_MODE_WAL)
        self._connection.executescript(_SCHEMA)
        self._connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
        self._connection.commit()

    def _migrate_from_18_or_19(self, version: int) -> None:
        """Add the card tables from schema 18, then the metrics tables and backfill, in one transaction.

        Any error rolls back and leaves the original schema version.
        """
        connection = self._connection
        connection.execute(_JOURNAL_MODE_WAL)
        connection.execute(_BEGIN_IMMEDIATE)
        try:
            if version == 18:
                for statement in _CARD_DDL:
                    connection.execute(statement)
            for statement in _METRICS_DDL:
                connection.execute(statement)
            terminal_jobs = connection.execute(
                "SELECT * FROM jobs WHERE state IN ('succeeded', 'failed', 'interrupted', 'cancelled')"
            ).fetchall()
            for job in terminal_jobs:
                connection.execute(
                    """INSERT INTO job_metrics(job_id, finished_at, profile, workflow, target, backend, model,
                       state, failure_kind, duration_ms, tok_input, tok_output, tok_cache_read, tok_cache_write,
                       attempts, skipped_targets, retry_of)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)""",
                    (job["id"], job["finished_at"] or job["updated_at"], job["profile"], job["workflow"],
                     job["target"] or "", _backend_for_target(job["execution_plan_json"], job["target"] or ""),
                     job["model"] or "", job["state"], job["failure_kind"], job["duration_ms"],
                     job["tok_input"], job["tok_output"], job["tok_cache_read"],
                     job["tok_cache_write"], job["retry_of"]),
                )
            connection.execute("PRAGMA user_version=21")
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def _migrate_to_21(self) -> None:
        """Add job_metrics.profile and backfill it from jobs still stored, in one transaction.

        Metrics rows whose job was already pruned keep an empty profile. Any error rolls back and
        leaves schema 20.
        """
        connection = self._connection
        connection.execute(_JOURNAL_MODE_WAL)
        connection.execute(_BEGIN_IMMEDIATE)
        try:
            connection.execute("ALTER TABLE job_metrics ADD COLUMN profile TEXT NOT NULL DEFAULT ''")
            connection.execute(
                "UPDATE job_metrics SET profile = (SELECT profile FROM jobs WHERE jobs.id = job_metrics.job_id) "
                "WHERE job_id IN (SELECT id FROM jobs)"
            )
            connection.execute("PRAGMA user_version=21")
            connection.execute("COMMIT")
        except BaseException:
            connection.execute("ROLLBACK")
            raise

    def create_card(self, *, card_id: str, project_id: str, title: str, body: str, job_ids: Sequence[str]) -> dict[str, Any]:
        if not 1 <= len(title) <= _CARD_TITLE_MAX or not title.strip():
            raise CardError("invalid_request", f"title must be 1 to {_CARD_TITLE_MAX} characters and not blank")
        if len(body) > _CARD_BODY_MAX:
            raise CardError("invalid_request", f"body must be at most {_CARD_BODY_MAX} characters")
        job_ids = _card_job_ids(job_ids)
        now = utc_now()
        with self.transaction():
            if self._connection.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
                raise CardError("invalid_request", f"unknown project {project_id}")
            if self._connection.execute("SELECT 1 FROM cards WHERE id=?", (card_id,)).fetchone() is not None:
                raise CardError("invalid_request", f"card {card_id} already exists")
            self._connection.execute(
                "INSERT INTO cards(id, project_id, title, body, state, created_at, updated_at) VALUES (?, ?, ?, ?, 'todo', ?, ?)",
                (card_id, project_id, title, body, now, now),
            )
            self._connection.execute(
                "INSERT INTO card_moves(card_id, from_state, to_state, note, at) VALUES (?, NULL, 'todo', '', ?)",
                (card_id, now),
            )
            self._link_jobs(card_id, job_ids, now)
            return self._card_row(card_id)

    def move_card(self, *, card_id: str, state: str, job_ids: Sequence[str], note: str) -> dict[str, Any]:
        if len(note) > _CARD_NOTE_MAX:
            raise CardError("invalid_request", f"note must be at most {_CARD_NOTE_MAX} characters")
        job_ids = _card_job_ids(job_ids)
        now = utc_now()
        with self.transaction():
            row = self._connection.execute("SELECT state FROM cards WHERE id=?", (card_id,)).fetchone()
            if row is None:
                raise CardError("unknown_card", f"unknown card {card_id}")
            current = row["state"]
            moved = state != current
            if moved and state not in _CARD_EDGES[current]:
                raise CardError("invalid_state", f"cannot move from {current} to {state}; current state {current}")
            linked = self._link_jobs(card_id, job_ids, now)
            if moved:
                changed = self._connection.execute(
                    "UPDATE cards SET state=?, updated_at=? WHERE id=? AND state=?", (state, now, card_id, current)
                ).rowcount
                if changed == 0:
                    latest = self._connection.execute("SELECT state FROM cards WHERE id=?", (card_id,)).fetchone()["state"]
                    raise CardError("invalid_state", f"card changed; current state {latest}")
                self._connection.execute(
                    "INSERT INTO card_moves(card_id, from_state, to_state, note, at) VALUES (?, ?, ?, ?, ?)",
                    (card_id, current, state, note, now),
                )
            elif linked:
                self._connection.execute("UPDATE cards SET updated_at=? WHERE id=?", (now, card_id))
            return {"card": self._card_row(card_id), "moved": moved}

    def list_cards(self, *, project_id: str | None, limit: int | None) -> dict[str, Any]:
        sql = _CARD_SELECT + (" WHERE c.project_id=?" if project_id is not None else "")
        sql += " ORDER BY c.state IN ('done','cancelled'), c.updated_at DESC, c.id DESC"
        params: list[Any] = [] if project_id is None else [project_id]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit + 1)
        cards = [dict(row) for row in self._connection.execute(sql, params).fetchall()]
        truncated = limit is not None and len(cards) > limit
        cards = cards[:limit] if truncated else cards
        links: dict[str, list[str]] = {}
        for link in self._connection.execute(
            "SELECT cj.card_id, cj.job_id FROM card_jobs cj JOIN cards c ON c.id=cj.card_id"
            + (" WHERE c.project_id=?" if project_id is not None else "")
            + " ORDER BY cj.linked_at, cj.job_id",
            [] if project_id is None else [project_id],
        ):
            links.setdefault(link["card_id"], []).append(link["job_id"])
        for card in cards:
            card["job_ids"] = links.get(card["id"], [])
        return {"cards": cards, "truncated": truncated}

    def card_detail(self, card_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT c.id, c.project_id, p.root AS project_root, c.title, c.body, c.state, c.created_at, c.updated_at "
            "FROM cards c JOIN projects p ON p.id=c.project_id WHERE c.id=?",
            (card_id,),
        ).fetchone()
        if row is None:
            return None
        moves = self._connection.execute(
            "SELECT id, from_state, to_state, note, at FROM card_moves WHERE card_id=? ORDER BY id", (card_id,)
        ).fetchall()
        jobs = self._connection.execute(
            "SELECT cj.job_id, cj.linked_at, j.id IS NOT NULL AS available, j.workflow, j.state, j.target "
            "FROM card_jobs cj LEFT JOIN jobs j ON j.id=cj.job_id WHERE cj.card_id=? ORDER BY cj.linked_at, cj.job_id",
            (card_id,),
        ).fetchall()
        return {
            "card": dict(row),
            "moves": [dict(move) for move in moves],
            "jobs": [{**dict(job), "available": bool(job["available"])} for job in jobs],
        }

    def _card_row(self, card_id: str) -> dict[str, Any]:
        row = dict(self._connection.execute(_CARD_SELECT + " WHERE c.id=?", (card_id,)).fetchone())
        row["job_ids"] = [
            link["job_id"]
            for link in self._connection.execute(
                "SELECT job_id FROM card_jobs WHERE card_id=? ORDER BY linked_at, job_id", (card_id,)
            )
        ]
        return row

    def _link_jobs(self, card_id: str, job_ids: Sequence[str], now: str) -> int:
        """Link jobs not yet linked; return how many are new. Runs inside a transaction."""
        for job_id in job_ids:
            if self._connection.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone() is None:
                raise CardError("unknown_job", f"unknown job {job_id}")
        added = 0
        for job_id in job_ids:
            added += self._connection.execute(
                "INSERT OR IGNORE INTO card_jobs(card_id, job_id, linked_at) VALUES (?, ?, ?)", (card_id, job_id, now)
            ).rowcount
        total = self._connection.execute("SELECT COUNT(*) FROM card_jobs WHERE card_id=?", (card_id,)).fetchone()[0]
        if total > _CARD_LINKS_MAX:
            raise CardError("invalid_request", f"a card holds at most {_CARD_LINKS_MAX} job links")
        return added

    def _probe_version(self) -> int | None:
        """Read user_version without writing; None when the file is missing or empty."""
        if not self._path.exists() or self._path.stat().st_size == 0:
            return None
        # Probe a scratch copy: even a read-only SQLite connection rewrites the -shm file,
        # which would change the bytes of the v2 backup. The copy includes the -wal.
        for attempt in range(3):
            try:
                return self._probe_scratch_copy()
            except FileNotFoundError:
                # A closing writer checkpointed the -wal into the main file, then deleted it.
                # Recopy the main file so the probe sees the checkpointed pages.
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")

    def _probe_scratch_copy(self) -> int:
        with tempfile.TemporaryDirectory(prefix=".version-probe-", dir=self._path.parent) as scratch:
            copy = Path(scratch) / "probe.db"
            shutil.copyfile(self._path, copy)
            wal = Path(f"{self._path}-wal")
            if wal.exists():
                shutil.copyfile(wal, Path(f"{copy}-wal"))
            with closing(sqlite3.connect(f"{copy.as_uri()}?mode=ro", uri=True)) as probe:
                return int(probe.execute("PRAGMA user_version").fetchone()[0])

    def _retire(self, version: int) -> None:
        """Rename a pre-v3 database and its -wal and -shm files to *.v2.bak, never deleting data."""
        sources = [Path(f"{self._path}{suffix}") for suffix in ("", "-wal", "-shm")]
        present = [source for source in sources if source.exists()]
        backups = {source: Path(f"{source}.v2.bak") for source in present}
        clashes = [backup for backup in backups.values() if backup.exists()]
        if clashes:
            raise ValueError(
                f"Cannot retire the schema {version} database at {self._path}: backup {clashes[0]} already exists. "
                "The database was not modified."
            )
        # Sidecars move first so a crash never leaves a -wal beside a missing database.
        for source in reversed(present):
            os.replace(source, backups[source])
        log.info(
            "Retired pre-v3 database",
            extra={
                "event": "database.v2_retired",
                "database": self._path.as_posix(),
                "schema_version": version,
                "backups": [backup.as_posix() for backup in backups.values()],
            },
        )

    def stream_path(self, job_id: str) -> Path:
        return self.streams_dir / f"{job_id}.jsonl"

    def result_path(self, job_id: str) -> Path:
        return self.results_dir / f"{job_id}.md"

    def interrupt_active_jobs(self) -> list[dict[str, Any]]:
        with self._connection:
            if not self._connection.in_transaction:
                self._connection.execute(_BEGIN_IMMEDIATE)
            rows = [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM jobs WHERE state='running' ORDER BY created_at"
                ).fetchall()
            ]
            updated_at = utc_now()
            for row in rows:
                changed = self._connection.execute(
                    "UPDATE jobs SET state='interrupted', updated_at=? WHERE id=? AND state='running'",
                    (updated_at, row["id"]),
                ).rowcount
                if changed:
                    self._write_job_metrics(row["id"], updated_at, "interrupted", None, None, None)
        return rows

    def upsert_project(self, *, project_id: str, root: str) -> ProjectView:
        existing = self._connection.execute("SELECT id, created_at FROM projects WHERE root=?", (root,)).fetchone()
        created_at = existing["created_at"] if existing else utc_now()
        resolved_id = existing["id"] if existing else project_id
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO projects(id, root, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET root=excluded.root
                """,
                (resolved_id, root, created_at),
            )
        return ProjectView(id=resolved_id, root=root, created_at=created_at)

    def project(self, project_id: str) -> ProjectView | None:
        row = self._connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return self._project_view(row) if row else None

    def projects(self) -> list[ProjectView]:
        return [self._project_view(row) for row in self._connection.execute("SELECT * FROM projects ORDER BY root").fetchall()]

    @staticmethod
    def _project_view(row: sqlite3.Row) -> ProjectView:
        return ProjectView(id=row["id"], root=row["root"], created_at=row["created_at"])

    def create_job(
        self,
        *,
        job_id: str,
        project_id: str,
        workflow: str,
        profile: str,
        prompt: str,
        execution_plan_json: str,
        session: str,
        fresh: bool = False,
        retry_of: str = "",
    ) -> None:
        now = utc_now()
        with self._connection:
            self._connection.execute(
                """INSERT INTO jobs(id, project_id, workflow, profile, prompt,
                   execution_plan_json, session, state, fresh, retry_of, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
                (
                    job_id, project_id, workflow, profile, prompt,
                    execution_plan_json, session,
                    1 if fresh else 0, retry_of, now, now,
                ),
            )

    def queued_jobs(self) -> list[tuple[str, str]]:
        return [(row["id"], row["project_id"]) for row in self._connection.execute("SELECT id, project_id FROM jobs WHERE state='queued' ORDER BY created_at, id").fetchall()]

    def active_job_counts(self) -> dict[str, int]:
        rows = self._connection.execute("SELECT state, COUNT(*) FROM jobs WHERE state IN ('queued', 'running') GROUP BY state").fetchall()
        counts = {row[0]: row[1] for row in rows}
        return {"queued": counts.get("queued", 0), "running": counts.get("running", 0)}

    def job_record(self, job_id: str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def start_job(self, job_id: str) -> None:
        now = utc_now()
        with self._connection:
            self._connection.execute(
                """UPDATE jobs SET state='running', target='', error='',
                   started_at=?, updated_at=? WHERE id=?""",
                (now, now, job_id),
            )

    def set_pgid(self, job_id: str, pgid: int) -> None:
        with self._connection:
            self._connection.execute("UPDATE jobs SET pgid=? WHERE id=?", (pgid, job_id))

    def record_job_target(self, job_id: str, target: str) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE jobs SET target=?, updated_at=? WHERE id=?",
                (target, utc_now(), job_id),
            )

    def finish_job(
        self,
        job_id: str,
        state: str,
        *,
        text: str = "",
        target: str = "",
        error: str = "",
        failure_kind: str | None = None,
        model: str = "",
        duration_ms: int | None = None,
        tokens: dict[str, int | None] | None = None,
        attempts: int | None = None,
        skipped_targets: int | None = None,
    ) -> bool:
        """Finish the job; report whether this call moved it out of a non-terminal state."""
        with self._connection:
            return self._finish(
                job_id, state, text=text, target=target, error=error,
                failure_kind=failure_kind, model=model, duration_ms=duration_ms, tokens=tokens,
                attempts=attempts, skipped_targets=skipped_targets,
            )

    def _finish(
        self,
        job_id: str,
        state: str,
        *,
        text: str,
        target: str,
        error: str,
        failure_kind: str | None,
        model: str,
        duration_ms: int | None,
        tokens: dict[str, int | None] | None,
        attempts: int | None = None,
        skipped_targets: int | None = None,
    ) -> bool:
        if not self._connection.in_transaction:
            self._connection.execute(_BEGIN_IMMEDIATE)
        row = self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        transitioned = row is not None and row["state"] not in TERMINAL_STATES
        self._connection.execute(
            """UPDATE jobs SET state=?, target=CASE WHEN ?='' THEN target ELSE ? END,
               error=?, failure_kind=?, model=?, duration_ms=?,
               tok_context_used=?, tok_context_window=?, tok_input=?, tok_output=?, tok_cache_read=?, tok_cache_write=?,
               finished_at=?, updated_at=? WHERE id=?""",
            (
                state, target, target, error, failure_kind, model or None, duration_ms,
                *_token_values(tokens), utc_now(), utc_now(), job_id,
            ),
        )
        self._connection.execute("UPDATE target_health SET probe_job_id='' WHERE probe_job_id=?", (job_id,))
        if state == "succeeded" and row and (target or row["target"]):
            self._connection.execute(
                """INSERT INTO sessions(project_id, session, workflow, sticky_target, updated_at) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id, session, workflow) DO UPDATE SET
                sticky_target=excluded.sticky_target, updated_at=excluded.updated_at""",
                (row["project_id"], row["session"], row["workflow"], target or row["target"], utc_now()),
            )
        metrics_row = self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if metrics_row:
            self._write_job_metrics(job_id, metrics_row["finished_at"], state, attempts, skipped_targets, metrics_row)
        self._write_result(job_id, text)
        return transitioned

    def _write_job_metrics(
        self, job_id: str, finished_at: str, state: str, attempts: int | None,
        skipped_targets: int | None, row: sqlite3.Row | None = None,
    ) -> None:
        row = row or self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return
        target = row["target"] or ""
        backend = _backend_for_target(row["execution_plan_json"], target)
        self._connection.execute(
            """INSERT OR REPLACE INTO job_metrics(job_id, finished_at, profile, workflow, target, backend,
               model, state, failure_kind, duration_ms, tok_input, tok_output, tok_cache_read, tok_cache_write,
               attempts, skipped_targets, retry_of) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, finished_at, row["profile"], row["workflow"], target, backend, row["model"] or "", state,
             row["failure_kind"], row["duration_ms"], row["tok_input"], row["tok_output"],
             row["tok_cache_read"], row["tok_cache_write"], attempts, skipped_targets, row["retry_of"]),
        )

    def _write_result(self, job_id: str, text: str) -> None:
        self.results_dir.mkdir(mode=0o700, exist_ok=True)
        descriptor = os.open(self.result_path(job_id), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)

    def sticky_target(self, project_id: str, session: str, workflow: str) -> str:
        row = self._connection.execute(
            "SELECT sticky_target FROM sessions WHERE project_id=? AND session=? AND workflow=?",
            (project_id, session, workflow),
        ).fetchone()
        return row["sticky_target"] if row else ""

    def finish_fresh_job_success(
        self,
        *,
        job_id: str,
        project_id: str,
        session: str,
        workflow: str,
        target: str,
        target_key: str,
        backend_session_id: str,
        text: str,
        failure_kind: str | None = None,
        model: str = "",
        duration_ms: int | None = None,
        tokens: dict[str, int | None] | None = None,
        attempts: int | None = None,
        skipped_targets: int | None = None,
    ) -> bool:
        with self._connection:
            if not self._connection.in_transaction:
                self._connection.execute(_BEGIN_IMMEDIATE)
            self._upsert_target_session(
                project_id=project_id, session=session, workflow=workflow,
                target_key=target_key, backend_session_id=backend_session_id, clear_sessions=True,
            )
            return self._finish(
                job_id, "succeeded", text=text, target=target, error="",
                failure_kind=failure_kind, model=model, duration_ms=duration_ms, tokens=tokens,
                attempts=attempts, skipped_targets=skipped_targets,
            )

    def job(self, job_id: str) -> JobView | None:
        row = self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        return self.job_view(row)

    def jobs(self, project_id: str) -> list[JobView]:
        rows = self._connection.execute(
            "SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        return [self.job_view(row) for row in rows]

    def job_overview(
        self, project_id: str, *, recent_limit: int = 10
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        """Return active job records, the newest terminal records, and the count of older terminal jobs."""
        terminal = tuple(TERMINAL_STATES)
        placeholders = ",".join("?" for _ in terminal)
        active = self._connection.execute(
            f"SELECT * FROM jobs WHERE project_id=? AND state NOT IN ({placeholders}) ORDER BY created_at DESC",
            (project_id, *terminal),
        ).fetchall()
        recent = self._connection.execute(
            f"""SELECT * FROM jobs WHERE project_id=? AND state IN ({placeholders})
                ORDER BY updated_at DESC, id DESC LIMIT ?""",
            (project_id, *terminal, recent_limit),
        ).fetchall()
        total = self._connection.execute(
            f"SELECT COUNT(*) FROM jobs WHERE project_id=? AND state IN ({placeholders})",
            (project_id, *terminal),
        ).fetchone()[0]
        return [dict(row) for row in active], [dict(row) for row in recent], max(0, int(total) - len(recent))

    def job_view(self, row: sqlite3.Row | dict[str, Any]) -> JobView:
        try:
            text = self.result_path(row["id"]).read_text(encoding="utf-8")
        except FileNotFoundError:
            text = ""
        tokens = {key: row[column] for key, column in _TOKEN_COLUMNS}
        result = JobResult(
            text=text,
            error=row["error"],
            failure_kind=row["failure_kind"],
            model=row["model"],
            duration_ms=row["duration_ms"],
            tokens=tokens,
        )
        return JobView(id=row["id"], project_id=row["project_id"], workflow=row["workflow"], profile=row["profile"], state=row["state"], session=row["session"], target_id=row["target"], retry_of=row["retry_of"], created_at=row["created_at"], updated_at=row["updated_at"], result=result)

    def session(self, project_id: str, session: str, workflow: str, target_key: str) -> str:
        row = self._connection.execute(
            "SELECT backend_session_id FROM target_sessions WHERE project_id=? AND session=? AND workflow=? AND target_key=?",
            (project_id, session, workflow, target_key),
        ).fetchone()
        return row["backend_session_id"] if row else ""

    def store_session(self, *, project_id: str, session: str, workflow: str, target_key: str, backend_session_id: str) -> None:
        with self._connection:
            self._upsert_target_session(
                project_id=project_id, session=session, workflow=workflow,
                target_key=target_key, backend_session_id=backend_session_id, clear_sessions=False,
            )

    def _upsert_target_session(self, *, project_id: str, session: str, workflow: str, target_key: str, backend_session_id: str, clear_sessions: bool) -> None:
        if clear_sessions:
            self._connection.execute(
                "DELETE FROM target_sessions WHERE project_id=? AND session=? AND workflow=?",
                (project_id, session, workflow),
            )
        if backend_session_id:
            self._connection.execute(
                """INSERT INTO target_sessions(project_id, session, workflow, target_key, backend_session_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, session, workflow, target_key) DO UPDATE SET
                backend_session_id=excluded.backend_session_id, updated_at=excluded.updated_at""",
                (project_id, session, workflow, target_key, backend_session_id, utc_now()),
            )

    def target_health(self, target_id: str) -> dict[str, Any]:
        row = self._connection.execute("SELECT * FROM target_health WHERE target_id=?", (target_id,)).fetchone()
        return dict(row) if row else {"target_id": target_id, "consecutive_failures": 0, "circuit_open_until": "", "last_success_at": "", "cooldown_s": 0, "probe_job_id": ""}

    def claim_target_probe(self, target_id: str, job_id: str, now: str) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE target_health SET probe_job_id=:job WHERE target_id=:key AND circuit_open_until<>'' AND circuit_open_until<=:now AND probe_job_id=''",
                {"job": job_id, "key": target_id, "now": now},
            )
        return cursor.rowcount == 1

    def release_target_probe(self, target_id: str, job_id: str = "") -> None:
        with self._connection:
            if job_id:
                self._connection.execute("UPDATE target_health SET probe_job_id='' WHERE target_id=? AND probe_job_id=?", (target_id, job_id))
            else:
                self._connection.execute("UPDATE target_health SET probe_job_id='' WHERE target_id=?", (target_id,))

    def reset_orphaned_target_probes(self, now: str | None = None) -> int:
        with self._connection:
            cursor = self._connection.execute("UPDATE target_health SET probe_job_id='', circuit_open_until=? WHERE probe_job_id<>''", (now or utc_now(),))
        return cursor.rowcount

    def record_target_success(self, target_id: str, base_cooldown_s: int = 60) -> None:
        with self._connection:
            self._connection.execute("""INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, last_success_at, cooldown_s, probe_job_id) VALUES (?, 0, '', ?, ?, '')
                ON CONFLICT(target_id) DO UPDATE SET consecutive_failures=0, circuit_open_until='', last_success_at=excluded.last_success_at, cooldown_s=excluded.cooldown_s, probe_job_id=''""", (target_id, utc_now(), base_cooldown_s))

    def record_target_failure(self, target_id: str, circuit_open_until: str = "", *, threshold: int = 3, base_cooldown_s: int = 60, max_cooldown_s: int = 900, failed_probe: bool = False, immediate: bool = False) -> int:
        with self._connection:
            row = self._connection.execute("SELECT consecutive_failures, cooldown_s FROM target_health WHERE target_id=?", (target_id,)).fetchone()
            failures = (int(row["consecutive_failures"]) if row else 0) + 1
            cooldown = int(row["cooldown_s"] or 0) if row else 0
            if cooldown == 0:
                cooldown = base_cooldown_s
            if failed_probe:
                cooldown = min(max_cooldown_s, cooldown * 2)
            opened = immediate or failed_probe or failures >= threshold
            until = circuit_open_until or ((datetime.now(timezone.utc) + timedelta(seconds=cooldown)).isoformat() if opened else "")
            self._connection.execute("""INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, ?, ?, ?, '')
                ON CONFLICT(target_id) DO UPDATE SET consecutive_failures=excluded.consecutive_failures, circuit_open_until=excluded.circuit_open_until, cooldown_s=excluded.cooldown_s, probe_job_id=''""", (target_id, failures, until, cooldown))
        return failures

    def append_stream(self, job_id: str, events: Sequence[dict[str, Any]]) -> None:
        """Append events as JSON lines; an event's seq is its line number."""
        if not events:
            return
        self.streams_dir.mkdir(mode=0o700, exist_ok=True)
        payload = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)
        descriptor = os.open(self.stream_path(job_id), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(payload)

    def job_metrics_row(self, job_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM job_metrics WHERE job_id=?", (job_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def enqueue_telemetry(self, event_key: str, payload: str, now: str) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO telemetry_outbox(event_key, created_at, payload, next_attempt_at) VALUES (?, ?, ?, ?)",
                (event_key, now, payload, now),
            )
            self._connection.execute(
                "DELETE FROM telemetry_outbox WHERE id IN (SELECT id FROM telemetry_outbox ORDER BY id DESC LIMIT -1 OFFSET ?)",
                (MAX_OUTBOX_ROWS,),
            )
            cutoff = (datetime.fromisoformat(now) - timedelta(days=MAX_OUTBOX_AGE_DAYS)).isoformat()
            self._connection.execute("DELETE FROM telemetry_outbox WHERE created_at < ?", (cutoff,))

    def telemetry_batch(self, limit: int) -> list[dict[str, Any]]:
        return [dict(row) for row in self._connection.execute(
            "SELECT * FROM telemetry_outbox WHERE next_attempt_at <= ? ORDER BY id LIMIT ?",
            (utc_now(), limit),
        ).fetchall()]

    def telemetry_queue_count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM telemetry_outbox").fetchone()[0])

    def delete_telemetry(self, row_ids: list[int]) -> None:
        with self._connection:
            self._connection.executemany("DELETE FROM telemetry_outbox WHERE id=?", [(item,) for item in row_ids])

    def defer_telemetry(self, row_ids: list[int], delays: list[int]) -> None:
        with self._connection:
            for row_id, delay in zip(row_ids, delays):
                self._connection.execute(
                    "UPDATE telemetry_outbox SET send_attempts=send_attempts+1, next_attempt_at=? WHERE id=?",
                    ((datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(), row_id),
                )

    def clear_telemetry_outbox(self) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM telemetry_outbox")

    def prune_job_metrics(self, cutoff: str) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM job_metrics WHERE finished_at < ?", (cutoff,))

    def prune_history(self, older_than: str) -> None:
        """Delete terminal jobs older than the cutoff with their stream and result files."""
        placeholders = ",".join("?" for _ in TERMINAL_STATES)
        with self._connection:
            job_ids = [
                row["id"]
                for row in self._connection.execute(
                    f"SELECT id FROM jobs WHERE state IN ({placeholders}) AND updated_at < ?",
                    (*TERMINAL_STATES, older_than),
                ).fetchall()
            ]
            self._connection.executemany("DELETE FROM jobs WHERE id=?", [(job_id,) for job_id in job_ids])
        for job_id in job_ids:
            self.stream_path(job_id).unlink(missing_ok=True)
            self.result_path(job_id).unlink(missing_ok=True)

    def job_summaries(
        self,
        *,
        state: str | None = None,
        project_id: str | None = None,
        workflow: str | None = None,
        target: str | None = None,
        q: str | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if limit <= 0 or limit > 200:
            raise ValueError("limit must be between 1 and 200")

        query = """
            SELECT
                j.id,
                j.state,
                j.project_id,
                COALESCE(p.root, '') AS project_root,
                j.workflow,
                j.profile,
                j.target,
                j.session,
                j.retry_of,
                j.failure_kind,
                j.created_at,
                j.updated_at
            FROM jobs j
            LEFT JOIN projects p ON j.project_id = p.id
        """
        where_clauses: list[str] = []
        params: list[Any] = []

        if state is not None:
            where_clauses.append("j.state = ?")
            params.append(state)

        if project_id is not None:
            where_clauses.append("j.project_id = ?")
            params.append(project_id)

        if workflow is not None:
            where_clauses.append("j.workflow = ?")
            params.append(workflow)

        if target is not None:
            where_clauses.append("j.target = ?")
            params.append(target)

        if q is not None and q != "":
            escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            where_clauses.append("j.id LIKE ? ESCAPE '\\' COLLATE NOCASE")
            params.append(f"%{escaped_q}%")

        if cursor is not None and cursor != "":
            cursor_created_at, cursor_id = decode_cursor(cursor)
            where_clauses.append("(j.created_at < ? OR (j.created_at = ? AND j.id < ?))")
            params.extend([cursor_created_at, cursor_created_at, cursor_id])

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY j.created_at DESC, j.id DESC LIMIT ?"
        params.append(limit + 1)

        rows = self._connection.execute(query, tuple(params)).fetchall()
        has_more = len(rows) > limit
        result_rows = rows[:limit] if has_more else rows
        next_cursor = (
            encode_cursor(result_rows[-1]["created_at"], result_rows[-1]["id"])
            if has_more and result_rows
            else None
        )
        return [dict(row) for row in result_rows], next_cursor

    def job_filter_options(self) -> dict[str, Any]:
        states = [
            row[0]
            for row in self._connection.execute(
                "SELECT DISTINCT state FROM jobs WHERE state != '' ORDER BY state"
            ).fetchall()
        ]
        projects = [
            {"id": row["id"], "root": row["root"]}
            for row in self._connection.execute(
                """
                SELECT DISTINCT p.id, p.root
                FROM jobs j
                JOIN projects p ON j.project_id = p.id
                ORDER BY p.root, p.id
                """
            ).fetchall()
        ]
        workflows = [
            row[0]
            for row in self._connection.execute(
                "SELECT DISTINCT workflow FROM jobs WHERE workflow != '' ORDER BY workflow"
            ).fetchall()
        ]
        targets = [
            row[0]
            for row in self._connection.execute(
                "SELECT DISTINCT target FROM jobs WHERE target != '' ORDER BY target"
            ).fetchall()
        ]
        return {
            "states": states,
            "projects": projects,
            "workflows": workflows,
            "targets": targets,
        }

    def job_detail(self, job_id: str) -> dict[str, Any] | None:
        query = """
            SELECT
                j.*,
                COALESCE(p.root, '') AS project_root
            FROM jobs j
            LEFT JOIN projects p ON j.project_id = p.id
            WHERE j.id = ?
        """
        row = self._connection.execute(query, (job_id,)).fetchone()
        if row is None:
            return None
        try:
            result_text = self.result_path(job_id).read_text(encoding="utf-8")
        except FileNotFoundError:
            result_text = ""
        tokens = {key: row[column] for key, column in _TOKEN_COLUMNS}
        result = {
            "text": result_text,
            "error": row["error"],
            "failure_kind": row["failure_kind"],
            "model": row["model"],
            "duration_ms": row["duration_ms"],
            "tokens": tokens,
        }
        return {
            "id": row["id"],
            "state": row["state"],
            "project_id": row["project_id"],
            "project_root": row["project_root"],
            "workflow": row["workflow"],
            "profile": row["profile"],
            "target": row["target"],
            "session": row["session"],
            "retry_of": row["retry_of"],
            "failure_kind": row["failure_kind"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "prompt": row["prompt"],
            "result": result,
        }

