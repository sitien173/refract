"""SQLite persistence for direct project jobs."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from refract.config_inspection import utc_now
from refract.logging_setup import get_logger
from refract.models import (
    TERMINAL_STATES,
    ContextStreamView,
    JobResult,
    JobStreamEvent,
    JobView,
    ProjectView,
    StreamTotals,
)
from refract.telemetry import TelemetryData, merge_telemetry, prepare_telemetry_for_retry
from refract.result_metadata import convert_schema15_metadata, JobResultMetadata, PublicTelemetry, project_telemetry

log = get_logger("database")
_SCHEMA_VERSION = 16


class Database:
    def __init__(self, path: Path, *, history_turns: int = 8) -> None:
        self.history_turns = history_turns
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
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
        if self._path.exists():
            # A writable connection can checkpoint an unsupported WAL on close.
            with closing(sqlite3.connect(f"{self._path.resolve().as_uri()}?mode=ro", uri=True)) as probe:
                empty_probe = self._validate_schema(probe)
                if not empty_probe and int(probe.execute("PRAGMA user_version").fetchone()[0]) == 15:
                    self._preflight_schema15(probe)
        connection = self._connection
        empty = self._validate_schema(connection)
        if empty:
            connection.execute("PRAGMA journal_mode=WAL")
            self._create_schema()
        elif int(connection.execute("PRAGMA user_version").fetchone()[0]) == 15:
            self._migrate_schema15(connection)
        connection.execute("PRAGMA journal_mode=WAL")
        log.debug(
            "Database schema is current",
            extra={"event": "database.schema_ready", "schema_version": _SCHEMA_VERSION},
        )

    def _validate_schema(self, connection: sqlite3.Connection) -> bool:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        schema = connection.execute("SELECT name, type FROM sqlite_master").fetchall()
        empty = version == 0 and not schema
        if not empty and version not in (15, _SCHEMA_VERSION):
            recovery = (
                "Back up the database and upgrade it to schema 16 using a migration-capable "
                "Refract version, or select a new state directory with REFRACT_HOME."
                if version < _SCHEMA_VERSION
                else f"Use a Refract version that supports schema {version}."
            )
            raise ValueError(
                f"Unsupported database schema {version} at {self._path}; "
                f"this version supports schema 15 or {_SCHEMA_VERSION} only. {recovery} "
                "The database was not modified."
            )
        if not empty:
            tables = {name for name, kind in schema if kind == "table"}
            expected_tables = {"projects", "jobs", "events", "context_sessions", "context_turns", "target_health", "job_stream_events"}
            if "jobs" not in tables:
                raise ValueError(
                    f"Database schema {version} at {self._path} is incomplete: jobs table missing. "
                    "Restore a compatible backup. The database was not modified."
                )
            if not expected_tables <= tables:
                missing = sorted(expected_tables - tables)
                raise ValueError(
                    f"Database schema {version} at {self._path} is incomplete: required tables missing ({', '.join(missing)}). "
                    "Restore a compatible backup. The database was not modified."
                )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
            required_jobs = {"id", "project_id", "workflow", "profile", "prompt", "execution_plan_json", "context_key", "state", "result_text", "target_id", "attempts", "error", "config_revision", "fresh_session", "result_metadata_json", "created_at", "updated_at"}
            if not required_jobs <= columns:
                raise ValueError(
                    f"Database schema {version} at {self._path} is incomplete: jobs columns missing. "
                    "Restore a compatible backup. The database was not modified."
                )
            if version == 15 and "telemetry_state_json" in columns:
                raise ValueError(
                    f"Database schema 15 at {self._path} is incomplete: unexpected column telemetry_state_json. "
                    "Restore a compatible backup. The database was not modified."
                )
            if version == 16 and "telemetry_state_json" not in columns:
                raise ValueError(
                    f"Database schema 16 at {self._path} is incomplete: telemetry_state_json column missing. "
                    "Restore a compatible backup. The database was not modified."
                )
            expected_columns = {
                "projects": {"id", "alias", "root", "created_at"},
                "jobs": required_jobs | ({"telemetry_state_json"} if version == 16 else set()),
                "events": {"id", "job_id", "created_at", "kind", "data_json"},
                "context_sessions": {"project_id", "context_key", "role", "target_id", "target_key", "lane", "session_id", "updated_at"},
                "context_turns": {"id", "project_id", "context_key", "role", "target_id", "prompt", "response", "created_at"},
                "target_health": {"target_id", "consecutive_failures", "circuit_open_until", "last_success_at", "cooldown_s", "probe_job_id"},
                "job_stream_events": {"id", "job_id", "created_at", "attempt", "target_id", "backend", "kind", "entity_id", "parent_entity_id", "data_json", "size_bytes"},
            }
            for table, expected in expected_columns.items():
                actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                if actual != expected:
                    raise ValueError(f"Database schema {version} at {self._path} is incomplete: {table} columns are invalid. The database was not modified.")
            expected_indexes = {
                "jobs_state_idx": ("jobs", ("state", "created_at")),
                "jobs_project_idx": ("jobs", ("project_id", "updated_at")),
                "events_job_idx": ("events", ("job_id", "id")),
                "context_turns_stream_idx": ("context_turns", ("project_id", "context_key", "role", "id")),
                "job_stream_events_job_idx": ("job_stream_events", ("job_id", "id")),
            }
            index_rows = {row[1]: row for row in connection.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE type='index'")}
            for name, (table, expected) in expected_indexes.items():
                index = index_rows.get(name)
                columns = tuple(row[2] for row in connection.execute(f"PRAGMA index_info({name})")) if index else ()
                unique = bool(connection.execute(f"PRAGMA index_list({table})").fetchall() and next((row[2] for row in connection.execute(f"PRAGMA index_list({table})") if row[1] == name), 0))
                if index is None or index[2] != table or columns != expected or unique:
                    raise ValueError(f"Database schema {version} at {self._path} is incomplete: index definition {name} is invalid. The database was not modified.")
            not_null_columns = {
                "projects": {"alias", "root", "created_at"},
                "jobs": {"project_id", "workflow", "profile", "prompt", "execution_plan_json", "context_key", "state", "result_text", "target_id", "attempts", "error", "config_revision", "fresh_session", "result_metadata_json", "created_at", "updated_at"} | ({"telemetry_state_json"} if version == 16 else set()),
                "events": {"job_id", "created_at", "kind", "data_json"},
                "context_sessions": {"project_id", "context_key", "role", "target_id", "target_key", "lane", "session_id", "updated_at"},
                "context_turns": {"project_id", "context_key", "role", "target_id", "prompt", "response", "created_at"},
                "target_health": {"consecutive_failures", "circuit_open_until", "last_success_at", "cooldown_s", "probe_job_id"},
                "job_stream_events": {"job_id", "created_at", "attempt", "target_id", "backend", "kind", "entity_id", "parent_entity_id", "data_json", "size_bytes"},
            }
            for table, expected in not_null_columns.items():
                actual = {row[1] for row in connection.execute(f"PRAGMA table_info({table})") if row[3]}
                if not expected <= actual:
                    raise ValueError(f"Database schema {version} at {self._path} is incomplete: {table} NOT NULL constraint is missing. The database was not modified.")
            primary_keys = {
                "projects": ("id",), "jobs": ("id",), "events": ("id",),
                "context_sessions": ("project_id", "context_key", "role", "target_key", "lane"),
                "context_turns": ("id",), "target_health": ("target_id",),
                "job_stream_events": ("id",),
            }
            for table, expected in primary_keys.items():
                actual = tuple(row[1] for row in sorted(connection.execute(f"PRAGMA table_info({table})"), key=lambda row: row[5]) if row[5])
                if actual != expected:
                    raise ValueError(f"Database schema {version} at {self._path} is incomplete: {table} primary-key constraint is invalid. The database was not modified.")
            required_unique = {"projects": {("alias",), ("root",)}}
            for table, expected_sets in required_unique.items():
                actual_sets = set()
                for index_row in connection.execute(f"PRAGMA index_list({table})"):
                    if index_row[2]:
                        actual_sets.add(tuple(row[2] for row in connection.execute(f"PRAGMA index_info({index_row[1]})")))
                if not expected_sets <= actual_sets:
                    raise ValueError(f"Database schema {version} at {self._path} is incomplete: {table} uniqueness constraint is missing. The database was not modified.")
            foreign_keys = {
                "jobs": {("projects", "project_id", "id", "NO ACTION")},
                "events": {("jobs", "job_id", "id", "CASCADE")},
                "context_sessions": {("projects", "project_id", "id", "CASCADE")},
                "context_turns": {("projects", "project_id", "id", "CASCADE")},
                "job_stream_events": {("jobs", "job_id", "id", "CASCADE")},
            }
            for table, expected in foreign_keys.items():
                actual = {(row[2], row[3], row[4], row[6].upper()) for row in connection.execute(f"PRAGMA foreign_key_list({table})")}
                if not expected <= actual:
                    raise ValueError(f"Database schema {version} at {self._path} is incomplete: {table} foreign-key constraint is invalid. The database was not modified.")
        return empty

    def _preflight_schema15(self, connection: sqlite3.Connection) -> list[tuple[str, str, str]]:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        required = {"id", "project_id", "workflow", "profile", "prompt", "execution_plan_json", "context_key", "state", "result_text", "target_id", "attempts", "error", "config_revision", "fresh_session", "result_metadata_json", "created_at", "updated_at"}
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected_tables = {"projects", "jobs", "events", "context_sessions", "context_turns", "target_health", "job_stream_events"}
        if not required <= columns or not expected_tables <= tables or "telemetry_state_json" in columns:
            raise ValueError("Database schema 15 is incomplete: required table or jobs structure is invalid. The database was not modified.")
        prepared = []
        for row in connection.execute("SELECT id, result_metadata_json FROM jobs ORDER BY id"):
            try:
                raw = json.loads(row[1] or "{}")
                metadata, internal = convert_schema15_metadata(raw)
                public_json = json.dumps(metadata.model_dump(mode="json"), ensure_ascii=False)
                state_json = json.dumps(internal.model_dump(mode="json"), ensure_ascii=False) if internal else ""
            except Exception as exc:
                diagnostic = str(exc).splitlines()[0][:120]
                raise ValueError(f"Schema 15 migration rejected job {row[0]} metadata field: {diagnostic}") from None
            prepared.append((row[0], public_json, state_json))
        return prepared

    def _migrate_schema15(self, connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            prepared = self._preflight_schema15(connection)
            connection.execute("ALTER TABLE jobs ADD COLUMN telemetry_state_json TEXT NOT NULL DEFAULT ''")
            for job_id, public_json, state_json in prepared:
                connection.execute("UPDATE jobs SET result_metadata_json=?, telemetry_state_json=? WHERE id=?", (public_json, state_json, job_id))
            connection.execute("PRAGMA user_version=16")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def _create_schema(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                alias TEXT NOT NULL UNIQUE,
                root TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                workflow TEXT NOT NULL,
                profile TEXT NOT NULL,
                prompt TEXT NOT NULL,
                execution_plan_json TEXT NOT NULL,
                context_key TEXT NOT NULL,
                state TEXT NOT NULL,
                result_text TEXT NOT NULL DEFAULT '',
                target_id TEXT NOT NULL DEFAULT '',
                attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                config_revision TEXT NOT NULL DEFAULT '',
                fresh_session INTEGER NOT NULL DEFAULT 0,
                result_metadata_json TEXT NOT NULL DEFAULT '{}',
                telemetry_state_json TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        self._create_support_tables()
        self._connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
        self._connection.commit()

    def _create_support_tables(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                data_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS context_sessions (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                context_key TEXT NOT NULL,
                role TEXT NOT NULL,
                target_id TEXT NOT NULL,
                target_key TEXT NOT NULL,
                lane TEXT NOT NULL DEFAULT '',
                session_id TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id, context_key, role, target_key, lane)
            );
            CREATE TABLE IF NOT EXISTS context_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                context_key TEXT NOT NULL,
                role TEXT NOT NULL,
                target_id TEXT NOT NULL,
                prompt TEXT NOT NULL,
                response TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS target_health (
                target_id TEXT PRIMARY KEY,
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                circuit_open_until TEXT NOT NULL DEFAULT '',
                last_success_at TEXT NOT NULL DEFAULT '',
                cooldown_s INTEGER NOT NULL DEFAULT 0,
                probe_job_id TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS jobs_state_idx ON jobs(state, created_at);
            CREATE INDEX IF NOT EXISTS jobs_project_idx ON jobs(project_id, updated_at);
            CREATE INDEX IF NOT EXISTS events_job_idx ON events(job_id, id);
            CREATE INDEX IF NOT EXISTS context_turns_stream_idx
                ON context_turns(project_id, context_key, role, id);
            CREATE TABLE IF NOT EXISTS job_stream_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                target_id TEXT NOT NULL,
                backend TEXT NOT NULL,
                kind TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                parent_entity_id TEXT NOT NULL,
                data_json TEXT NOT NULL,
                size_bytes INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS job_stream_events_job_idx
                ON job_stream_events(job_id, id);
            """
        )


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
        for row in rows:
            self.event(row["id"], "job.interrupted", {})
        return rows

    def upsert_project(self, *, project_id: str, alias: str, root: str) -> ProjectView:
        existing = self._connection.execute("SELECT id, created_at FROM projects WHERE root=?", (root,)).fetchone()
        created_at = existing["created_at"] if existing else utc_now()
        resolved_id = existing["id"] if existing else project_id
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO projects(id, alias, root, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET alias=excluded.alias, root=excluded.root
                """,
                (resolved_id, alias, root, created_at),
            )
        return ProjectView(id=resolved_id, alias=alias, root=root, created_at=created_at)

    def project(self, project_id: str) -> ProjectView | None:
        row = self._connection.execute("SELECT * FROM projects WHERE id=? OR alias=?", (project_id, project_id)).fetchone()
        return self._project_view(row) if row else None

    def projects(self) -> list[ProjectView]:
        return [self._project_view(row) for row in self._connection.execute("SELECT * FROM projects ORDER BY alias").fetchall()]

    @staticmethod
    def _project_view(row: sqlite3.Row) -> ProjectView:
        return ProjectView(id=row["id"], alias=row["alias"], root=row["root"], created_at=row["created_at"])

    def create_job(
        self,
        *,
        job_id: str,
        project_id: str,
        workflow: str,
        profile: str,
        prompt: str,
        execution_plan_json: str,
        context_key: str,
        config_revision: str = "",
        fresh_session: bool = False,
    ) -> None:
        now = utc_now()
        with self._connection:
            self._connection.execute(
                """INSERT INTO jobs(id, project_id, workflow, profile, prompt,
                   execution_plan_json, context_key, state, config_revision,
                   fresh_session, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
                (
                    job_id, project_id, workflow, profile, prompt,
                    execution_plan_json, context_key, config_revision,
                    1 if fresh_session else 0, now, now,
                ),
            )
            self._event(job_id, "job.queued", {"workflow": workflow, "profile": profile})

    def queued_jobs(self) -> list[tuple[str, str]]:
        return [(row["id"], row["project_id"]) for row in self._connection.execute("SELECT id, project_id FROM jobs WHERE state='queued' ORDER BY created_at, id").fetchall()]

    def job_record(self, job_id: str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def start_job(self, job_id: str) -> None:
        with self._connection:
            self._connection.execute(
                """UPDATE jobs SET state='running', result_text='',
                   target_id='', error='', updated_at=? WHERE id=?""",
                (utc_now(), job_id),
            )
            self._event(job_id, "job.running", {})

    def record_job_attempt(self, job_id: str, target_id: str) -> int:
        with self._connection:
            self._connection.execute(
                "UPDATE jobs SET target_id=?, attempts=attempts+1, updated_at=? WHERE id=?",
                (target_id, utc_now(), job_id),
            )
            row = self._connection.execute(
                "SELECT attempts FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            return int(row["attempts"]) if row else 1

    def merge_job_telemetry(self, job_id: str, telemetry: dict[str, Any] | TelemetryData) -> None:
        try:
            incoming = telemetry if isinstance(telemetry, TelemetryData) else TelemetryData.model_validate(telemetry)
        except Exception:
            return
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute("SELECT state, result_metadata_json, telemetry_state_json FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None or row["state"] in TERMINAL_STATES:
                return
            state = TelemetryData.model_validate_json(row["telemetry_state_json"]) if row["telemetry_state_json"] else TelemetryData()
            merged_state = TelemetryData.model_validate(merge_telemetry(state.model_dump(mode="json"), incoming.model_dump(mode="json")))
            metadata = JobResultMetadata.model_validate_json(row["result_metadata_json"] or "{}")
            metadata.telemetry = project_telemetry(merged_state)
            self._connection.execute("UPDATE jobs SET result_metadata_json=?, telemetry_state_json=?, updated_at=? WHERE id=?", (metadata.model_dump_json(), merged_state.model_dump_json(), utc_now(), job_id))

    def finish_job(self, job_id: str, state: str, *, text: str = "", target_id: str = "", error: str = "", metadata: dict[str, Any] | None = None) -> None:
        with self._connection:
            self._finish(job_id, state, text=text, target_id=target_id, error=error, metadata=metadata)

    def _finish(self, job_id: str, state: str, *, text: str = "", target_id: str = "", error: str = "", metadata: dict[str, Any] | None = None) -> None:
        if not self._connection.in_transaction:
            self._connection.execute("BEGIN IMMEDIATE")
        row = self._connection.execute("SELECT result_metadata_json, telemetry_state_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        current = JobResultMetadata.model_validate_json(row["result_metadata_json"] or "{}") if row else JobResultMetadata()
        if metadata is not None:
            incoming = metadata if isinstance(metadata, JobResultMetadata) else JobResultMetadata.model_validate(metadata)
            current.execution = incoming.execution
            current.failure = incoming.failure
            current.retry = incoming.retry.model_copy(update={"next_target": None})
            if incoming.telemetry.completeness != "unavailable":
                current.telemetry = incoming.telemetry
        state_json = row["telemetry_state_json"] if row else ""
        if state_json:
            stored_state = TelemetryData.model_validate_json(state_json)
            incoming_state_data = current.telemetry.model_dump(mode="json")
            incoming_state_data["attribution"] = stored_state.attribution.model_dump(mode="json")
            incoming_state_data["completed_attempts"] = stored_state.completed_attempts.model_dump(mode="json")
            incoming_state = TelemetryData.model_validate(incoming_state_data)
            retained = TelemetryData.model_validate(merge_telemetry(stored_state.model_dump(mode="json"), incoming_state.model_dump(mode="json")))
            current.telemetry = project_telemetry(retained)
            state_json = retained.model_dump_json()
        elif current.telemetry.completeness != "unavailable":
            state_json = TelemetryData.model_validate(current.telemetry.model_dump(mode="json")).model_dump_json()
        self._connection.execute(
            """UPDATE jobs SET state=?, result_text=?, target_id=CASE WHEN ?='' THEN target_id ELSE ? END,
               error=?, result_metadata_json=?, telemetry_state_json=?, updated_at=? WHERE id=?""",
            (state, text, target_id, target_id, error, current.model_dump_json(), state_json, utc_now(), job_id),
        )
        self._connection.execute("UPDATE target_health SET probe_job_id='' WHERE probe_job_id=?", (job_id,))
        self._event(job_id, f"job.{state}", {"error": error} if error else {})

    def finish_fresh_job_success(
        self,
        *,
        job_id: str,
        project_id: str,
        context_key: str,
        role: str,
        target_id: str,
        target_key: str,
        lane: str = "",
        session_id: str,
        prompt: str,
        response: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connection:
            if not self._connection.in_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            self._append_turn(
                project_id=project_id, context_key=context_key, role=role,
                target_id=target_id, target_key=target_key, lane=lane,
                session_id=session_id, prompt=prompt, response=response,
                clear_sessions=True,
            )
            self._finish(job_id, "succeeded", text=response, target_id=target_id, metadata=metadata)

    def reset_retry(self, job_id: str) -> None:
        with self._connection:
            if not self._connection.in_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute("SELECT result_metadata_json, telemetry_state_json FROM jobs WHERE id=?", (job_id,)).fetchone()
            current = JobResultMetadata.model_validate_json(row["result_metadata_json"] or "{}") if row else JobResultMetadata()
            state_json = row["telemetry_state_json"] if row else ""
            if state_json:
                state = TelemetryData.model_validate_json(state_json)
                state = TelemetryData.model_validate(prepare_telemetry_for_retry(state.model_dump(mode="json")))
                state_json = state.model_dump_json()
                current.telemetry = project_telemetry(state)
            current.execution = current.execution.model_copy(update={"duration_ms": None})
            current.failure = None
            current.retry = current.retry.model_copy(update={"retryable": None, "next_target": None})
            self._connection.execute(
                """UPDATE jobs SET state='queued', result_text='', target_id='', error='',
                   result_metadata_json=?, telemetry_state_json=?, updated_at=? WHERE id=?""",
                (current.model_dump_json(), state_json, utc_now(), job_id),
            )
            self._event(job_id, "job.retried", {})

    def event(self, job_id: str, kind: str, data: dict[str, Any]) -> None:
        with self._connection:
            self._event(job_id, kind, data)

    def _event(self, job_id: str, kind: str, data: dict[str, Any]) -> None:
        self._connection.execute("INSERT INTO events(job_id, created_at, kind, data_json) VALUES (?, ?, ?, ?)", (job_id, utc_now(), kind, json.dumps(data, ensure_ascii=False)))

    def events(self, job_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute("SELECT id, created_at, kind, data_json FROM events WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
        return [{"id": row["id"], "created_at": row["created_at"], "kind": row["kind"], "data": json.loads(row["data_json"])} for row in rows]

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

    def job_listing(
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

    @staticmethod
    def job_view(row: sqlite3.Row | dict[str, Any]) -> JobView:
        try:
            metadata = json.loads(row["result_metadata_json"] or "{}")
            if not isinstance(metadata, dict):
                metadata = {}
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        return JobView(id=row["id"], project_id=row["project_id"], workflow=row["workflow"], profile=row["profile"], config_revision=row["config_revision"], state=row["state"], context_key=row["context_key"], target_id=row["target_id"], attempts=row["attempts"], created_at=row["created_at"], updated_at=row["updated_at"], result=JobResult(text=row["result_text"], error=row["error"], metadata=metadata))

    def session(self, project_id: str, context_key: str, role: str, target_key: str, lane: str = "") -> str:
        row = self._connection.execute("SELECT session_id FROM context_sessions WHERE project_id=? AND context_key=? AND role=? AND target_key=? AND lane=?", (project_id, context_key, role, target_key, lane)).fetchone()
        return row["session_id"] if row else ""

    def append_turn(self, *, project_id: str, context_key: str, role: str, target_id: str, target_key: str, lane: str = "", session_id: str, prompt: str, response: str, clear_sessions: bool = False) -> None:
        with self._connection:
            self._append_turn(
                project_id=project_id, context_key=context_key, role=role,
                target_id=target_id, target_key=target_key, lane=lane,
                session_id=session_id, prompt=prompt, response=response,
                clear_sessions=clear_sessions,
            )

    def _upsert_session(self, *, project_id: str, context_key: str, role: str, target_id: str, target_key: str, lane: str, session_id: str, clear_sessions: bool) -> None:
        if clear_sessions:
            self._connection.execute(
                "DELETE FROM context_sessions WHERE project_id=? AND context_key=? AND role=?",
                (project_id, context_key, role),
            )
        if session_id:
            self._connection.execute(
                """INSERT INTO context_sessions(project_id, context_key, role, target_id, target_key, lane, session_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, context_key, role, target_key, lane) DO UPDATE SET
                target_id=excluded.target_id, session_id=excluded.session_id, updated_at=excluded.updated_at""",
                (project_id, context_key, role, target_id, target_key, lane, session_id, utc_now()),
            )

    def _append_turn(self, *, project_id: str, context_key: str, role: str, target_id: str, target_key: str, lane: str, session_id: str, prompt: str, response: str, clear_sessions: bool) -> None:
        self._upsert_session(
            project_id=project_id, context_key=context_key, role=role,
            target_id=target_id, target_key=target_key, lane=lane,
            session_id=session_id, clear_sessions=clear_sessions,
        )
        self._connection.execute("INSERT INTO context_turns(project_id, context_key, role, target_id, prompt, response, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (project_id, context_key, role, target_id, prompt, response, utc_now()))

        self._connection.execute(
            """DELETE FROM context_turns WHERE project_id=? AND context_key=? AND role=?
               AND id NOT IN (SELECT id FROM context_turns
                              WHERE project_id=? AND context_key=? AND role=?
                              ORDER BY id DESC LIMIT ?)""",
            (project_id, context_key, role, project_id, context_key, role, self.history_turns),
        )

    def recent_turns(self, project_id: str, context_key: str, role: str, limit: int) -> list[dict[str, str]]:
        rows = self._connection.execute("SELECT target_id, prompt, response FROM context_turns WHERE project_id=? AND context_key=? AND role=? ORDER BY id DESC LIMIT ?", (project_id, context_key, role, limit)).fetchall()
        return [dict(row) for row in reversed(rows)]

    def context(self, project_id: str, context_key: str) -> list[ContextStreamView]:
        rows = self._connection.execute("SELECT role, target_id, lane, session_id FROM context_sessions WHERE project_id=? AND context_key=? ORDER BY role, target_id, updated_at", (project_id, context_key)).fetchall()
        roles: dict[str, dict[str, str]] = {}
        for row in rows:
            target = f"{row['target_id']}#{row['lane']}" if row["lane"] else row["target_id"]
            roles.setdefault(row["role"], {})[target] = row["session_id"]
        turn_rows = self._connection.execute(
            """SELECT role, COUNT(*) AS turns FROM context_turns
               WHERE project_id=? AND context_key=? GROUP BY role""",
            (project_id, context_key),
        ).fetchall()
        turns = {row["role"]: row["turns"] for row in turn_rows}
        return [ContextStreamView(project_id=project_id, context_key=context_key, role=role, turns=turns.get(role, 0), sessions=roles.get(role, {})) for role in sorted(roles.keys() | turns.keys())]

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

    def append_stream_events(
        self,
        job_id: str,
        events: Sequence[dict[str, Any]],
    ) -> list[JobStreamEvent]:
        if not events:
            return []
        persisted: list[JobStreamEvent] = []
        now = utc_now()
        with self._connection:
            for item in events:
                created_at = item.get("created_at") or now
                attempt = int(item.get("attempt", 1))
                target_id = str(item.get("target_id", ""))
                backend = str(item.get("backend", ""))
                kind = str(item.get("kind", ""))
                entity_id = str(item.get("entity_id", ""))
                parent_entity_id = str(item.get("parent_entity_id", ""))
                data = item.get("data", {})
                data_json = json.dumps(data, ensure_ascii=False)
                size_bytes = len(data_json.encode("utf-8"))
                cursor = self._connection.execute(
                    """INSERT INTO job_stream_events(
                        job_id, created_at, attempt, target_id, backend,
                        kind, entity_id, parent_entity_id, data_json, size_bytes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job_id,
                        created_at,
                        attempt,
                        target_id,
                        backend,
                        kind,
                        entity_id,
                        parent_entity_id,
                        data_json,
                        size_bytes,
                    ),
                )
                event_id = int(cursor.lastrowid)
                persisted.append(
                    JobStreamEvent(
                        id=event_id,
                        version=1,
                        job_id=job_id,
                        created_at=created_at,
                        attempt=attempt,
                        target_id=target_id,
                        backend=backend,
                        kind=kind,
                        entity_id=entity_id,
                        parent_entity_id=parent_entity_id,
                        data=data,
                    )
                )
        return persisted

    def stream_events(
        self,
        job_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> list[JobStreamEvent]:
        safe_limit = max(1, min(limit, 500))
        rows = self._connection.execute(
            """SELECT id, job_id, created_at, attempt, target_id, backend,
                      kind, entity_id, parent_entity_id, data_json
               FROM job_stream_events
               WHERE job_id=? AND id > ?
               ORDER BY id ASC
               LIMIT ?""",
            (job_id, after, safe_limit),
        ).fetchall()
        return [
            JobStreamEvent(
                id=row["id"],
                version=1,
                job_id=row["job_id"],
                created_at=row["created_at"],
                attempt=row["attempt"],
                target_id=row["target_id"],
                backend=row["backend"],
                kind=row["kind"],
                entity_id=row["entity_id"],
                parent_entity_id=row["parent_entity_id"],
                data=json.loads(row["data_json"]),
            )
            for row in rows
        ]

    def stream_metadata(self, job_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            """SELECT COALESCE(MAX(id), 0) AS high_water,
                      COALESCE(MIN(id), 0) AS retained_from,
                      EXISTS(SELECT 1 FROM job_stream_events
                             WHERE job_id=:job_id AND kind='stream.truncated') AS truncated,
                      EXISTS(SELECT 1 FROM events
                             WHERE job_id=:job_id AND kind='stream.persistence_failed') AS failed
               FROM job_stream_events WHERE job_id=:job_id""",
            {"job_id": job_id},
        ).fetchone()
        return {"high_water": int(row["high_water"]), "retained_from": int(row["retained_from"]),
                "truncated": bool(row["truncated"]), "failed": bool(row["failed"])}

    def stream_high_water(self, job_id: str) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(id), 0) AS high_water FROM job_stream_events WHERE job_id=?",
            (job_id,),
        ).fetchone()
        return int(row["high_water"]) if row else 0

    def stream_retained_from(self, job_id: str) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MIN(id), 0) AS retained_from FROM job_stream_events WHERE job_id=?",
            (job_id,),
        ).fetchone()
        return int(row["retained_from"]) if row else 0

    def stream_totals(self, job_id: str) -> StreamTotals:
        row = self._connection.execute(
            """SELECT COUNT(*) AS event_count, COALESCE(SUM(size_bytes), 0) AS total_bytes
               FROM job_stream_events WHERE job_id=?""",
            (job_id,),
        ).fetchone()
        if not row:
            return StreamTotals(events=0, bytes=0)
        return StreamTotals(events=int(row["event_count"]), bytes=int(row["total_bytes"]))

    def stream_is_truncated(self, job_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM job_stream_events WHERE job_id=? AND kind='stream.truncated' LIMIT 1",
            (job_id,),
        ).fetchone()
        return row is not None

    def prune_history(self, older_than: str) -> None:
        placeholders = ",".join("?" for _ in TERMINAL_STATES)
        with self._connection:
            self._connection.execute(
                f"""DELETE FROM events WHERE job_id IN (
                    SELECT id FROM jobs WHERE state IN ({placeholders}) AND updated_at < ?
                )""",
                (*TERMINAL_STATES, older_than),
            )
            self._connection.execute(
                """DELETE FROM context_turns WHERE id IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY project_id, context_key, role ORDER BY id DESC
                        ) AS position FROM context_turns
                    ) WHERE position > ?
                )""",
                (self.history_turns,),
            )

    def prune_terminal_stream_events(self, older_than: str) -> int:
        terminal_states_tuple = tuple(TERMINAL_STATES)
        placeholders = ",".join("?" for _ in terminal_states_tuple)
        with self._connection:
            cursor = self._connection.execute(
                f"""DELETE FROM job_stream_events
                    WHERE job_id IN (
                        SELECT id FROM jobs
                        WHERE state IN ({placeholders}) AND updated_at < ?
                    )""",
                (*terminal_states_tuple, older_than),
            )
            return cursor.rowcount


__all__ = ["Database", "utc_now"]
