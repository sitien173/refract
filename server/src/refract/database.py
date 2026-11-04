"""SQLite persistence for direct project jobs."""

from __future__ import annotations

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

log = get_logger("database")
_SCHEMA_VERSION = 18
_TOKEN_COLUMNS = (
    ("context_used", "tok_context_used"),
    ("context_window", "tok_context_window"),
    ("input", "tok_input"),
    ("output", "tok_output"),
    ("cache_read", "tok_cache_read"),
    ("cache_write", "tok_cache_write"),
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
"""


def _token_values(tokens: dict[str, int | None] | None) -> tuple[int | None, ...]:
    """Return token counters in column order; a missing key stays NULL."""
    tokens = tokens or {}
    return tuple(tokens.get(key) for key, _column in _TOKEN_COLUMNS)


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
            self._connection.execute("BEGIN IMMEDIATE")
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
        if version != _SCHEMA_VERSION:
            if version is not None:
                self._retire(version)
            self._create_schema()
        self._connection.execute("PRAGMA journal_mode=WAL")
        log.debug(
            "Database schema is current",
            extra={"event": "database.schema_ready", "schema_version": _SCHEMA_VERSION},
        )

    def _create_schema(self) -> None:
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(_SCHEMA)
        self._connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
        self._connection.commit()

    def _probe_version(self) -> int | None:
        """Read user_version without writing; None when the file is missing or empty."""
        if not self._path.exists() or self._path.stat().st_size == 0:
            return None
        # Probe a scratch copy: even a read-only SQLite connection rewrites the -shm file,
        # which would change the bytes of the v2 backup. The copy includes the -wal.
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
        rows = [
            dict(row)
            for row in self._connection.execute(
                "SELECT * FROM jobs WHERE state='running' ORDER BY created_at"
            ).fetchall()
        ]
        with self._connection:
            self._connection.execute(
                "UPDATE jobs SET state='interrupted', updated_at=? WHERE state='running'",
                (utc_now(),),
            )
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
    ) -> None:
        with self._connection:
            self._finish(
                job_id, state, text=text, target=target, error=error,
                failure_kind=failure_kind, model=model, duration_ms=duration_ms, tokens=tokens,
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
    ) -> None:
        if not self._connection.in_transaction:
            self._connection.execute("BEGIN IMMEDIATE")
        row = self._connection.execute("SELECT project_id, session, workflow, target FROM jobs WHERE id=?", (job_id,)).fetchone()
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
        self._write_result(job_id, text)

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
    ) -> None:
        with self._connection:
            if not self._connection.in_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            self._upsert_target_session(
                project_id=project_id, session=session, workflow=workflow,
                target_key=target_key, backend_session_id=backend_session_id, clear_sessions=True,
            )
            self._finish(
                job_id, "succeeded", text=text, target=target, error="",
                failure_kind=failure_kind, model=model, duration_ms=duration_ms, tokens=tokens,
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

