"""SQLite persistence for projects, jobs, events, and context streams."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openmcp.models import (
    ArtifactView,
    ContextStreamView,
    JobResult,
    JobView,
    ProjectView,
    StageView,
)


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

    def close(self) -> None:
        self._connection.close()

    def _migrate(self) -> None:
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY
            );
            INSERT OR IGNORE INTO schema_migrations(version) VALUES (1);

            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                alias TEXT NOT NULL UNIQUE,
                root TEXT NOT NULL UNIQUE,
                head_commit TEXT NOT NULL,
                clean INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                workflow TEXT NOT NULL,
                routing_profile TEXT NOT NULL DEFAULT '',
                workflow_json TEXT NOT NULL,
                inputs_json TEXT NOT NULL,
                context_key TEXT NOT NULL,
                parent_job_id TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL,
                base_commit TEXT NOT NULL,
                integration_base TEXT NOT NULL DEFAULT '',
                branch TEXT NOT NULL,
                worktree TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                result_text TEXT NOT NULL DEFAULT '',
                result_commit TEXT NOT NULL DEFAULT '',
                error TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS stages (
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                mode TEXT NOT NULL,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                target_id TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL DEFAULT '',
                outputs_json TEXT NOT NULL DEFAULT '[]',
                error TEXT NOT NULL DEFAULT '',
                commit_sha TEXT NOT NULL DEFAULT '',
                start_commit TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(job_id, id)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                data_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                path TEXT NOT NULL,
                PRIMARY KEY(job_id, kind, path)
            );

            CREATE TABLE IF NOT EXISTS context_sessions (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                context_key TEXT NOT NULL,
                role TEXT NOT NULL,
                target_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                PRIMARY KEY(project_id, context_key, role, target_id)
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
            """
        )
        columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "parent_job_id" not in columns:
            self._connection.execute(
                "ALTER TABLE jobs ADD COLUMN parent_job_id TEXT NOT NULL DEFAULT ''"
            )
        if "integration_base" not in columns:
            self._connection.execute(
                "ALTER TABLE jobs ADD COLUMN integration_base TEXT NOT NULL DEFAULT ''"
            )
        if "routing_profile" not in columns:
            self._connection.execute(
                "ALTER TABLE jobs ADD COLUMN routing_profile TEXT NOT NULL DEFAULT ''"
            )
        self._connection.execute(
            "UPDATE jobs SET integration_base=base_commit WHERE integration_base=''"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (2)"
        )
        self._connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (3)"
        )
        self._connection.commit()

    def interrupt_active_jobs(self) -> int:
        now = utc_now()
        with self._connection:
            stages = self._connection.execute(
                "UPDATE stages SET state='interrupted' WHERE state='running'"
            ).rowcount
            jobs = self._connection.execute(
                "UPDATE jobs SET state='interrupted', updated_at=? WHERE state='running'",
                (now,),
            ).rowcount
        return max(jobs, stages)

    def upsert_project(
        self,
        *,
        project_id: str,
        alias: str,
        root: str,
        head_commit: str,
        clean: bool,
    ) -> ProjectView:
        existing = self._connection.execute(
            "SELECT id, created_at FROM projects WHERE root=?", (root,)
        ).fetchone()
        created_at = existing["created_at"] if existing else utc_now()
        resolved_id = existing["id"] if existing else project_id
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO projects(id, alias, root, head_commit, clean, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    alias=excluded.alias,
                    root=excluded.root,
                    head_commit=excluded.head_commit,
                    clean=excluded.clean
                """,
                (resolved_id, alias, root, head_commit, int(clean), created_at),
            )
        return ProjectView(
            id=resolved_id,
            alias=alias,
            root=root,
            head_commit=head_commit,
            clean=clean,
            created_at=created_at,
        )

    def project(self, project_id: str) -> ProjectView | None:
        row = self._connection.execute(
            "SELECT * FROM projects WHERE id=? OR alias=?", (project_id, project_id)
        ).fetchone()
        return self._project_view(row) if row else None

    def projects(self) -> list[ProjectView]:
        rows = self._connection.execute("SELECT * FROM projects ORDER BY alias").fetchall()
        return [self._project_view(row) for row in rows]

    @staticmethod
    def _project_view(row: sqlite3.Row) -> ProjectView:
        return ProjectView(
            id=row["id"],
            alias=row["alias"],
            root=row["root"],
            head_commit=row["head_commit"],
            clean=bool(row["clean"]),
            created_at=row["created_at"],
        )

    def create_job(
        self,
        *,
        job_id: str,
        project_id: str,
        workflow: str,
        routing_profile: str,
        workflow_json: str,
        inputs: dict[str, Any],
        context_key: str,
        parent_job_id: str,
        base_commit: str,
        integration_base: str,
        branch: str,
        worktree: str,
        stages: Iterable[tuple[str, int, str]],
    ) -> None:
        now = utc_now()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO jobs(
                    id, project_id, workflow, routing_profile, workflow_json, inputs_json,
                    context_key, parent_job_id, state, base_commit,
                    integration_base, branch, worktree,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    project_id,
                    workflow,
                    routing_profile,
                    workflow_json,
                    json.dumps(inputs, ensure_ascii=False),
                    context_key,
                    parent_job_id,
                    base_commit,
                    integration_base,
                    branch,
                    worktree,
                    now,
                    now,
                ),
            )
            self._connection.executemany(
                "INSERT INTO stages(job_id, id, ordinal, mode, state) VALUES (?, ?, ?, ?, 'pending')",
                ((job_id, stage_id, ordinal, mode) for stage_id, ordinal, mode in stages),
            )
        self.event(
            job_id,
            "job.queued",
            {"workflow": workflow, "routing_profile": routing_profile},
        )

    def queued_job_ids(self) -> list[str]:
        rows = self._connection.execute(
            "SELECT id FROM jobs WHERE state='queued' ORDER BY created_at"
        ).fetchall()
        return [row["id"] for row in rows]

    def job_record(self, job_id: str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def stage_records(self, job_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM stages WHERE job_id=? ORDER BY ordinal", (job_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def set_job_state(self, job_id: str, state: str, *, error: str = "") -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE jobs SET state=?, error=?, updated_at=? WHERE id=?",
                (state, error, utc_now(), job_id),
            )
        self.event(job_id, f"job.{state}", {"error": error} if error else {})

    def set_job_result(self, job_id: str, *, text: str, commit: str) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE jobs SET result_text=?, result_commit=?, updated_at=? WHERE id=?",
                (text, commit, utc_now(), job_id),
            )

    def set_job_routing_profile(self, job_id: str, routing_profile: str) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE jobs SET routing_profile=?, updated_at=? WHERE id=?",
                (routing_profile, utc_now(), job_id),
            )

    def set_stage_state(
        self,
        job_id: str,
        stage_id: str,
        state: str,
        *,
        target_id: str | None = None,
        text: str | None = None,
        outputs: list[dict[str, Any]] | None = None,
        error: str | None = None,
        commit: str | None = None,
        start_commit: str | None = None,
        increment_attempts: bool = False,
    ) -> None:
        assignments = ["state=?"]
        values: list[Any] = [state]
        for column, value in (
            ("target_id", target_id),
            ("text", text),
            ("outputs_json", json.dumps(outputs, ensure_ascii=False) if outputs is not None else None),
            ("error", error),
            ("commit_sha", commit),
            ("start_commit", start_commit),
        ):
            if value is not None:
                assignments.append(f"{column}=?")
                values.append(value)
        if increment_attempts:
            assignments.append("attempts=attempts+1")
        values.extend((job_id, stage_id))
        with self._connection:
            self._connection.execute(
                f"UPDATE stages SET {', '.join(assignments)} WHERE job_id=? AND id=?",
                values,
            )
        self.event(job_id, f"stage.{state}", {"stage": stage_id, "target": target_id or ""})

    def reset_retry(self, job_id: str, from_ordinal: int) -> None:
        with self._connection:
            self._connection.execute(
                """
                UPDATE stages SET state='pending', target_id='', text='', outputs_json='[]',
                    error='', commit_sha='', start_commit=''
                WHERE job_id=? AND ordinal>=?
                """,
                (job_id, from_ordinal),
            )
            self._connection.execute(
                "UPDATE jobs SET state='queued', error='', result_text='', result_commit='', updated_at=? WHERE id=?",
                (utc_now(), job_id),
            )
        self.event(job_id, "job.retried", {"from_ordinal": from_ordinal})

    def add_artifact(self, job_id: str, kind: str, path: str) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT OR IGNORE INTO artifacts(job_id, kind, path) VALUES (?, ?, ?)",
                (job_id, kind, path),
            )

    def event(self, job_id: str, kind: str, data: dict[str, Any]) -> None:
        with self._connection:
            self._connection.execute(
                "INSERT INTO events(job_id, created_at, kind, data_json) VALUES (?, ?, ?, ?)",
                (job_id, utc_now(), kind, json.dumps(data, ensure_ascii=False)),
            )

    def events(self, job_id: str) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT id, created_at, kind, data_json FROM events WHERE job_id=? ORDER BY id",
            (job_id,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "kind": row["kind"],
                "data": json.loads(row["data_json"]),
            }
            for row in rows
        ]

    def job(self, job_id: str) -> JobView | None:
        row = self._connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return None
        stage_rows = self._connection.execute(
            "SELECT * FROM stages WHERE job_id=? ORDER BY ordinal", (job_id,)
        ).fetchall()
        artifacts = self._connection.execute(
            "SELECT kind, path FROM artifacts WHERE job_id=? ORDER BY kind, path", (job_id,)
        ).fetchall()
        stages = [
            StageView(
                id=stage["id"],
                state=stage["state"],
                mode=stage["mode"],
                attempts=stage["attempts"],
                target_id=stage["target_id"],
                text=stage["text"],
                error=stage["error"],
                commit=stage["commit_sha"],
            )
            for stage in stage_rows
        ]
        return JobView(
            id=row["id"],
            project_id=row["project_id"],
            workflow=row["workflow"],
            routing_profile=row["routing_profile"],
            state=row["state"],
            context_key=row["context_key"],
            parent_job_id=row["parent_job_id"],
            base_commit=row["base_commit"],
            integration_base=row["integration_base"],
            branch=row["branch"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            stages=stages,
            result=JobResult(
                text=row["result_text"],
                commit=row["result_commit"],
                error=row["error"],
                artifacts=[ArtifactView(kind=value["kind"], path=value["path"]) for value in artifacts],
            ),
        )

    def jobs(self, project_id: str) -> list[JobView]:
        rows = self._connection.execute(
            "SELECT id FROM jobs WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
        return [job for row in rows if (job := self.job(row["id"])) is not None]

    def session(self, project_id: str, context_key: str, role: str, target_id: str) -> str:
        row = self._connection.execute(
            """
            SELECT session_id FROM context_sessions
            WHERE project_id=? AND context_key=? AND role=? AND target_id=?
            """,
            (project_id, context_key, role, target_id),
        ).fetchone()
        return row["session_id"] if row else ""

    def append_turn(
        self,
        *,
        project_id: str,
        context_key: str,
        role: str,
        target_id: str,
        session_id: str,
        prompt: str,
        response: str,
    ) -> None:
        with self._connection:
            if session_id:
                self._connection.execute(
                    """
                    INSERT INTO context_sessions(project_id, context_key, role, target_id, session_id)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, context_key, role, target_id)
                    DO UPDATE SET session_id=excluded.session_id
                    """,
                    (project_id, context_key, role, target_id, session_id),
                )
            self._connection.execute(
                """
                INSERT INTO context_turns(
                    project_id, context_key, role, target_id, prompt, response, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, context_key, role, target_id, prompt, response, utc_now()),
            )

    def recent_turns(
        self,
        project_id: str,
        context_key: str,
        role: str,
        limit: int,
    ) -> list[dict[str, str]]:
        rows = self._connection.execute(
            """
            SELECT target_id, prompt, response FROM context_turns
            WHERE project_id=? AND context_key=? AND role=?
            ORDER BY id DESC LIMIT ?
            """,
            (project_id, context_key, role, limit),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def context(self, project_id: str, context_key: str) -> list[ContextStreamView]:
        rows = self._connection.execute(
            """
            SELECT role, target_id, session_id FROM context_sessions
            WHERE project_id=? AND context_key=? ORDER BY role, target_id
            """,
            (project_id, context_key),
        ).fetchall()
        roles: dict[str, dict[str, str]] = {}
        for row in rows:
            roles.setdefault(row["role"], {})[row["target_id"]] = row["session_id"]
        views: list[ContextStreamView] = []
        for role, sessions in roles.items():
            count = self._connection.execute(
                """
                SELECT COUNT(*) AS count FROM context_turns
                WHERE project_id=? AND context_key=? AND role=?
                """,
                (project_id, context_key, role),
            ).fetchone()["count"]
            views.append(
                ContextStreamView(
                    project_id=project_id,
                    context_key=context_key,
                    role=role,
                    turns=count,
                    sessions=sessions,
                )
            )
        return views

    def target_health(self, target_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM target_health WHERE target_id=?", (target_id,)
        ).fetchone()
        return dict(row) if row else {
            "target_id": target_id,
            "consecutive_failures": 0,
            "circuit_open_until": "",
            "last_success_at": "",
        }

    def record_target_success(self, target_id: str) -> None:
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, last_success_at)
                VALUES (?, 0, '', ?)
                ON CONFLICT(target_id) DO UPDATE SET
                    consecutive_failures=0,
                    circuit_open_until='',
                    last_success_at=excluded.last_success_at
                """,
                (target_id, utc_now()),
            )

    def record_target_failure(self, target_id: str, circuit_open_until: str = "") -> int:
        health = self.target_health(target_id)
        failures = int(health["consecutive_failures"]) + 1
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until)
                VALUES (?, ?, ?)
                ON CONFLICT(target_id) DO UPDATE SET
                    consecutive_failures=excluded.consecutive_failures,
                    circuit_open_until=excluded.circuit_open_until
                """,
                (target_id, failures, circuit_open_until),
            )
        return failures


__all__ = ["Database", "utc_now"]
