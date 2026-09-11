"""SQLite persistence for direct project jobs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from openmcp.logging_setup import get_logger
from openmcp.models import (
    ContextStreamView,
    JobResult,
    JobStreamEvent,
    JobView,
    ProjectView,
    StreamTotals,
    TERMINAL_STATES,
)


log = get_logger("database")
_SCHEMA_VERSION = 11


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._migrate()
        log.info(
            "Database opened",
            extra={"event": "database.opened", "database": path.as_posix()},
        )

    def close(self) -> None:
        self._connection.close()
        log.info("Database closed", extra={"event": "database.closed"})

    def _migrate(self) -> None:
        tables = self._tables()
        if "jobs" not in tables:
            self._create_schema()
        else:
            version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
            columns = self._columns("jobs")
            if version == 0:
                self._migrate_legacy_jobs()
                self._create_support_tables()
                self._migrate_v7_to_v8()
            elif version == 5:
                self._migrate_v5_to_v6()
                self._create_support_tables()
                self._migrate_v7_to_v8()
            elif version == 6:
                self._create_support_tables()
                self._connection.execute("PRAGMA user_version=7")
                self._connection.commit()
                self._migrate_v7_to_v8()
            elif version == 7 and "config_revision" not in columns:
                self._migrate_v7_to_v8()
            else:
                # Schema version, rather than an exact column-set guess, gates
                # migrations. This keeps a reopened database from treating a
                # newly added column as legacy and dropping it.
                self._create_support_tables()
            self._migrate_v8_to_v9()
            self._migrate_v9_to_v10()
            self._migrate_v10_to_v11()
        log.debug(
            "Database schema is current",
            extra={"event": "database.migrated", "schema_version": _SCHEMA_VERSION},
        )

    def _migrate_v7_to_v8(self) -> None:
        """Add revision identity without rewriting historical job rows."""
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.execute(
                "ALTER TABLE jobs ADD COLUMN config_revision TEXT NOT NULL DEFAULT ''"
            )
            self._connection.execute("PRAGMA user_version=8")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _migrate_v8_to_v9(self) -> None:
        """Drop stored context instructions after the feature was removed."""
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version >= 9:
            return
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.execute("DROP TABLE IF EXISTS context_instructions")
            self._connection.execute("PRAGMA user_version=9")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _migrate_v9_to_v10(self) -> None:
        """Add fresh_session flag to jobs table."""
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version >= 10:
            return
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            if "fresh_session" not in self._columns("jobs"):
                self._connection.execute(
                    "ALTER TABLE jobs ADD COLUMN fresh_session INTEGER NOT NULL DEFAULT 0"
                )
            self._connection.execute("PRAGMA user_version=10")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _migrate_v10_to_v11(self) -> None:
        """Add job_stream_events table for durable worker transcripts."""
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version >= 11:
            return
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._connection.executescript(
                """
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
            self._connection.execute("PRAGMA user_version=11")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise

    def _tables(self) -> set[str]:
        return {
            row["name"]
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    def _columns(self, table: str) -> set[str]:
        statements = {
            "jobs": "PRAGMA table_info(jobs)",
            "projects": "PRAGMA table_info(projects)",
            "context_sessions": "PRAGMA table_info(context_sessions)",
            "job_stream_events": "PRAGMA table_info(job_stream_events)",
        }

        try:
            statement = statements[table]
        except KeyError as exc:
            raise ValueError(f"Unsupported schema table: {table}") from exc
        return {
            row["name"]
            for row in self._connection.execute(statement)
        }

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
                last_success_at TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS jobs_state_idx ON jobs(state, created_at);
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


    def _normalize_legacy_columns(self) -> None:
        columns = self._columns("jobs")
        additions = {
            "profile": "ALTER TABLE jobs ADD COLUMN profile TEXT NOT NULL DEFAULT ''",
            "execution_plan_json": (
                "ALTER TABLE jobs ADD COLUMN execution_plan_json TEXT NOT NULL DEFAULT ''"
            ),
            "result_stage": "ALTER TABLE jobs ADD COLUMN result_stage TEXT NOT NULL DEFAULT ''",
            "inputs_json": "ALTER TABLE jobs ADD COLUMN inputs_json TEXT NOT NULL DEFAULT '{}'",
            "error": "ALTER TABLE jobs ADD COLUMN error TEXT NOT NULL DEFAULT ''",
        }
        for name, statement in additions.items():
            if name not in columns:
                self._connection.execute(statement)
        columns = self._columns("jobs")
        if "routing_profile" in columns:
            self._connection.execute(
                "UPDATE jobs SET profile=routing_profile WHERE profile='' AND routing_profile!=''"
            )
        if "stages" in self._tables() and "result_stage" in self._columns("jobs"):
            self._connection.execute(
                """
                UPDATE jobs SET result_stage=(
                    SELECT id FROM stages
                    WHERE stages.job_id=jobs.id
                    ORDER BY ordinal DESC LIMIT 1
                ) WHERE result_stage=''
                """
            )
        if "context_sessions" in self._tables():
            columns = self._columns("context_sessions")
            if not {"target_key", "lane", "updated_at"} <= columns:
                self._connection.execute(
                    "ALTER TABLE context_sessions RENAME TO context_sessions_legacy"
                )
                self._connection.execute(
                    """CREATE TABLE context_sessions (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    context_key TEXT NOT NULL, role TEXT NOT NULL,
                    target_id TEXT NOT NULL, target_key TEXT NOT NULL,
                    lane TEXT NOT NULL DEFAULT '', session_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, context_key, role, target_key, lane)
                    )"""
                )
                self._connection.execute(
                    """INSERT INTO context_sessions(
                    project_id, context_key, role, target_id, target_key,
                    lane, session_id, updated_at
                    ) SELECT project_id, context_key, role, target_id, '', '', session_id, ''
                    FROM context_sessions_legacy"""
                )
                self._connection.execute("DROP TABLE context_sessions_legacy")

    def _migrate_v5_to_v6(self) -> None:
        self._connection.execute("PRAGMA foreign_keys=OFF")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                """CREATE TABLE projects_v6 (
                    id TEXT PRIMARY KEY,
                    alias TEXT NOT NULL UNIQUE,
                    root TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                )"""
            )
            self._connection.execute(
                """INSERT INTO projects_v6(id, alias, root, created_at)
                   SELECT id, alias, root, created_at FROM projects"""
            )
            self._connection.execute(
                """CREATE TABLE jobs_v6 (
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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            self._connection.execute(
                """INSERT INTO jobs_v6(
                    id, project_id, workflow, profile, prompt,
                    execution_plan_json, context_key, state, result_text,
                    target_id, attempts, error, created_at, updated_at
                ) SELECT id, project_id, workflow, profile, prompt,
                    execution_plan_json, context_key, state, result_text,
                    target_id, attempts, error, created_at, updated_at
                FROM jobs"""
            )
            self._connection.execute("DROP TABLE jobs")
            self._connection.execute("DROP TABLE projects")
            self._connection.execute("ALTER TABLE projects_v6 RENAME TO projects")
            self._connection.execute("ALTER TABLE jobs_v6 RENAME TO jobs")
            self._connection.execute("CREATE INDEX jobs_state_idx ON jobs(state, created_at)")
            self._connection.execute("PRAGMA user_version=7")
            if self._connection.execute("PRAGMA foreign_key_check").fetchall():
                raise sqlite3.IntegrityError("Foreign-key violations during v5 migration")
            integrity = self._connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise sqlite3.IntegrityError(f"Integrity check failed: {integrity}")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            self._connection.execute("PRAGMA foreign_keys=ON")

    def _migrate_legacy_jobs(self) -> None:
        self._connection.execute("PRAGMA foreign_keys=OFF")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._normalize_legacy_columns()
            state_map = {
                "integrated": "succeeded",
                "integration_conflict": "failed",
                "queued": "interrupted",
                "running": "interrupted",
            }
            if "stages" in self._tables():
                rows = self._connection.execute(
                    """
                    SELECT j.*, s.text AS stage_text,
                           s.target_id AS stage_target_id,
                           s.attempts AS stage_attempts,
                           s.error AS stage_error
                    FROM jobs AS j
                    LEFT JOIN stages AS s
                      ON s.job_id=j.id
                     AND s.id=COALESCE(
                         NULLIF(j.result_stage, ''),
                         (SELECT fallback.id FROM stages AS fallback
                          WHERE fallback.job_id=j.id
                          ORDER BY fallback.ordinal DESC LIMIT 1)
                     )
                    ORDER BY j.created_at
                    """
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT j.*, '' AS stage_text, '' AS stage_target_id,
                           0 AS stage_attempts, '' AS stage_error
                    FROM jobs AS j
                    ORDER BY j.created_at
                    """
                ).fetchall()
            self._connection.execute(
                """CREATE TABLE projects_v6 (
                    id TEXT PRIMARY KEY,
                    alias TEXT NOT NULL UNIQUE,
                    root TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                )"""
            )
            self._connection.execute(
                """INSERT INTO projects_v6(id, alias, root, created_at)
                   SELECT id, alias, root, created_at FROM projects"""
            )
            self._connection.execute(
                """CREATE TABLE jobs_v6 (
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
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            converted_rows = []
            for row in rows:
                try:
                    inputs = json.loads(row["inputs_json"] or "{}")
                except json.JSONDecodeError:
                    inputs = {}
                if not isinstance(inputs, dict):
                    inputs = {}
                converted_rows.append(
                    (
                        row["id"], row["project_id"], row["workflow"], row["profile"],
                        str(inputs.get("prompt", "")), row["execution_plan_json"] or "{}",
                        row["context_key"], state_map.get(row["state"], row["state"]),
                        row["stage_text"] or "", row["stage_target_id"] or "",
                        int(row["stage_attempts"] or 0), row["error"] or row["stage_error"] or "",
                        row["created_at"], row["updated_at"],
                    )
                )
            self._connection.executemany(
                "INSERT INTO jobs_v6 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                converted_rows,
            )
            drops = {
                "artifacts": "DROP TABLE artifacts",
                "stages": "DROP TABLE stages",
                "jobs": "DROP TABLE jobs",
                "projects": "DROP TABLE projects",
            }
            for table, statement in drops.items():
                if table in self._tables():
                    self._connection.execute(statement)
            self._connection.execute("ALTER TABLE projects_v6 RENAME TO projects")
            self._connection.execute("ALTER TABLE jobs_v6 RENAME TO jobs")
            self._connection.execute("CREATE INDEX jobs_state_idx ON jobs(state, created_at)")
            self._connection.execute("PRAGMA user_version=7")
            if self._connection.execute("PRAGMA foreign_key_check").fetchall():
                raise sqlite3.IntegrityError("Foreign-key violations during legacy migration")
            integrity = self._connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise sqlite3.IntegrityError(f"Integrity check failed: {integrity}")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        finally:
            self._connection.execute("PRAGMA foreign_keys=ON")

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
        self.event(job_id, "job.queued", {"workflow": workflow, "profile": profile})

    def queued_jobs(self) -> list[tuple[str, str]]:
        return [(row["id"], row["project_id"]) for row in self._connection.execute("SELECT id, project_id FROM jobs WHERE state='queued' ORDER BY created_at, id").fetchall()]

    def job_record(self, job_id: str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def set_job_state(self, job_id: str, state: str, *, error: str = "") -> None:
        with self._connection:
            self._connection.execute("UPDATE jobs SET state=?, error=?, updated_at=? WHERE id=?", (state, error, utc_now(), job_id))
        self.event(job_id, f"job.{state}", {"error": error} if error else {})

    def start_job(self, job_id: str) -> None:
        with self._connection:
            self._connection.execute(
                """UPDATE jobs SET state='running', result_text='',
                   target_id='', error='', updated_at=? WHERE id=?""",
                (utc_now(), job_id),
            )
        self.event(job_id, "job.running", {})

    def record_job_attempt(self, job_id: str, target_id: str) -> None:
        with self._connection:
            self._connection.execute("UPDATE jobs SET target_id=?, attempts=attempts+1, updated_at=? WHERE id=?", (target_id, utc_now(), job_id))

    def finish_job(self, job_id: str, state: str, *, text: str = "", target_id: str = "", error: str = "") -> None:
        with self._connection:
            self._connection.execute(
                """UPDATE jobs SET state=?, result_text=?,
                   target_id=CASE WHEN ?='' THEN target_id ELSE ? END, error=?, updated_at=?
                   WHERE id=?""",
                (state, text, target_id, target_id, error, utc_now(), job_id),
            )
        self.event(job_id, f"job.{state}", {"error": error} if error else {})

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
    ) -> None:
        now = utc_now()
        with self._connection:
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
                    (project_id, context_key, role, target_id, target_key, lane, session_id, now),
                )
            self._connection.execute(
                "INSERT INTO context_turns(project_id, context_key, role, target_id, prompt, response, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (project_id, context_key, role, target_id, prompt, response, now),
            )
            self._connection.execute(
                """UPDATE jobs SET state='succeeded', result_text=?,
                   target_id=CASE WHEN ?='' THEN target_id ELSE ? END, error='', updated_at=?
                   WHERE id=?""",
                (response, target_id, target_id, now, job_id),
            )
            self._connection.execute(
                "INSERT INTO events(job_id, created_at, kind, data_json) VALUES (?, ?, 'job.succeeded', '{}')",
                (job_id, now),
            )

    def reset_retry(self, job_id: str) -> None:
        with self._connection:
            self._connection.execute(
                """UPDATE jobs SET state='queued', result_text='',
                   target_id='', error='', updated_at=? WHERE id=?""",
                (utc_now(), job_id),
            )
        self.event(job_id, "job.retried", {})

    def event(self, job_id: str, kind: str, data: dict[str, Any]) -> None:
        with self._connection:
            self._connection.execute("INSERT INTO events(job_id, created_at, kind, data_json) VALUES (?, ?, ?, ?)", (job_id, utc_now(), kind, json.dumps(data, ensure_ascii=False)))

    def events(self, job_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute("SELECT id, created_at, kind, data_json FROM events WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
        return [{"id": row["id"], "created_at": row["created_at"], "kind": row["kind"], "data": json.loads(row["data_json"])} for row in rows]

    def job(self, job_id: str) -> JobView | None:
        row = self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        return self._job_view(row)

    def jobs(self, project_id: str) -> list[JobView]:
        rows = self._connection.execute(
            "SELECT * FROM jobs WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        return [self._job_view(row) for row in rows]

    @staticmethod
    def _job_view(row: sqlite3.Row) -> JobView:
        return JobView(id=row["id"], project_id=row["project_id"], workflow=row["workflow"], profile=row["profile"], config_revision=row["config_revision"], state=row["state"], context_key=row["context_key"], target_id=row["target_id"], attempts=row["attempts"], created_at=row["created_at"], updated_at=row["updated_at"], result=JobResult(text=row["result_text"], error=row["error"]))

    def session(self, project_id: str, context_key: str, role: str, target_key: str, lane: str = "") -> str:
        row = self._connection.execute("SELECT session_id FROM context_sessions WHERE project_id=? AND context_key=? AND role=? AND target_key=? AND lane=?", (project_id, context_key, role, target_key, lane)).fetchone()
        return row["session_id"] if row else ""

    def append_turn(self, *, project_id: str, context_key: str, role: str, target_id: str, target_key: str, lane: str = "", session_id: str, prompt: str, response: str, clear_sessions: bool = False) -> None:
        with self._connection:
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
            self._connection.execute("INSERT INTO context_turns(project_id, context_key, role, target_id, prompt, response, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (project_id, context_key, role, target_id, prompt, response, utc_now()))

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
        return dict(row) if row else {"target_id": target_id, "consecutive_failures": 0, "circuit_open_until": "", "last_success_at": ""}

    def record_target_success(self, target_id: str) -> None:
        with self._connection:
            self._connection.execute("""INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, last_success_at) VALUES (?, 0, '', ?)
                ON CONFLICT(target_id) DO UPDATE SET consecutive_failures=0, circuit_open_until='', last_success_at=excluded.last_success_at""", (target_id, utc_now()))

    def record_target_failure(self, target_id: str, circuit_open_until: str = "") -> int:
        failures = int(self.target_health(target_id)["consecutive_failures"]) + 1
        with self._connection:
            self._connection.execute("""INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until) VALUES (?, ?, ?)
                ON CONFLICT(target_id) DO UPDATE SET consecutive_failures=excluded.consecutive_failures, circuit_open_until=excluded.circuit_open_until""", (target_id, failures, circuit_open_until))
        return failures

    def append_stream_events(
        self,
        job_id: str,
        events: Sequence[JobStreamEvent | dict[str, Any]],
    ) -> list[JobStreamEvent]:
        if not events:
            return []
        persisted: list[JobStreamEvent] = []
        now = utc_now()
        with self._connection:
            for item in events:
                if isinstance(item, JobStreamEvent):
                    created_at = item.created_at or now
                    attempt = item.attempt
                    target_id = item.target_id
                    backend = item.backend
                    kind = item.kind
                    entity_id = item.entity_id
                    parent_entity_id = item.parent_entity_id
                    data = item.data
                elif isinstance(item, dict):
                    created_at = item.get("created_at") or now
                    attempt = int(item.get("attempt", 1))
                    target_id = str(item.get("target_id", ""))
                    backend = str(item.get("backend", ""))
                    kind = str(item.get("kind", ""))
                    entity_id = str(item.get("entity_id", ""))
                    parent_entity_id = str(item.get("parent_entity_id", ""))
                    data = item.get("data", {})
                else:
                    raise TypeError(f"Unsupported event type: {type(item)}")
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
