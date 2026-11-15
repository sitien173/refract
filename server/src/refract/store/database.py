"""`Database`: the store modules behind one object with a pool and the transcript files."""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import Executor
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from refract.logging_setup import get_logger
from refract.models import JobResult, JobView, ProjectView
from refract.store import attempts, cards, health, jobs, questions, schema, sessions
from refract.store.attempts import TOKEN_COLUMNS as _TOKEN_COLUMNS
from refract.store.cards import CardError
from refract.store.jobs import decode_cursor, encode_cursor
from refract.store.pool import Pool
from refract.store.transcripts import Transcripts

__all__ = ["CardError", "Database", "decode_cursor", "encode_cursor"]
log = get_logger("database")


class Database:
    def __init__(self, path: Path) -> None:
        schema.initialize(path)
        self._path = path
        self.results_dir = path.parent / "results"
        self.streams_dir = path.parent / "streams"
        self._pool = Pool(path)
        self._transcripts = Transcripts(self.streams_dir, self.results_dir)
        log.info("Database opened", extra={"event": "database.opened", "database": path.as_posix()})

    @property
    def executor(self) -> Executor:
        """The fixed pool of DB threads; hand blocking DB work to it."""
        return self._pool.executor

    @property
    def _connection(self) -> sqlite3.Connection:
        return self._pool.connection

    @property
    def _local(self) -> threading.local:
        return self._pool._local

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._pool.transaction():
            yield

    def close(self) -> None:
        self._pool.close()
        log.info("Database closed", extra={"event": "database.closed"})

    def stream_path(self, job_id: str) -> Path:
        return self._transcripts.stream_path(job_id)

    def result_path(self, job_id: str) -> Path:
        return self._transcripts.result_path(job_id)

    # Projects

    def upsert_project(self, *, project_id: str, root: str) -> ProjectView:
        return ProjectView(**jobs.upsert_project(self._connection, project_id, root))

    def project(self, project_id: str) -> ProjectView | None:
        row = jobs.get_project(self._connection, project_id)
        return ProjectView(**row) if row else None

    def projects(self) -> list[ProjectView]:
        return [ProjectView(**row) for row in jobs.list_projects(self._connection)]

    # Jobs

    def create_job(
        self, *, job_id: str, project_id: str, workflow: str, profile: str, prompt: str,
        plan_json: str, session: str, fresh: bool = False, from_job: str = "",
    ) -> None:
        jobs.create(
            self._connection, job_id=job_id, project_id=project_id, workflow=workflow, profile=profile,
            prompt=prompt, plan_json=plan_json, session=session, fresh=fresh, from_job=from_job,
        )

    def queued_jobs(self) -> list[tuple[str, str]]:
        return jobs.queued(self._connection)

    def active_job_counts(self) -> dict[str, int]:
        return jobs.active_counts(self._connection)

    def job_record(self, job_id: str) -> dict[str, Any] | None:
        return jobs.record(self._connection, job_id)

    def start_job(self, job_id: str) -> bool:
        """Move a queued job to running; false when it is no longer queued."""
        return jobs.start(self._connection, job_id)

    def set_pgid(self, job_id: str, pgid: int) -> None:
        jobs.set_pgid(self._connection, job_id, pgid)

    def record_job_target(self, job_id: str, target: str) -> None:
        """Open an attempt on `target` while the job runs."""
        with self._pool.transaction() as conn:
            row = conn.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is not None and row["state"] == "running":
                attempts.begin(conn, job_id, target)

    def begin_attempt(self, job_id: str, target: str, reason: str) -> int | None:
        """Open an attempt on `target` with the runner's reason; None when the job is no longer running."""
        with self._pool.transaction() as conn:
            row = conn.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None or row["state"] != "running":
                return None
            return attempts.begin_with_reason(conn, job_id, target, reason)

    def finish_attempt(
        self, attempt_id: int, state: str, *, failure_kind: str | None, replay_safe: bool, model: str = "",
        duration_ms: int | None = None, tokens: dict[str, int | None] | None = None,
    ) -> None:
        """Close an attempt the runner follows with another one."""
        attempts.finish(
            self._connection, attempt_id, state, failure_kind=failure_kind, replay_safe=replay_safe, model=model,
            duration_ms=duration_ms, tokens=tokens,
        )

    def attempt_asked_question(self, attempt_id: int) -> bool:
        return questions.asked_during(self._connection, attempt_id)

    def mark_attempt_replay_safe(self, job_id: str, replay_safe: bool) -> None:
        """Record whether the job's open attempt streamed and ran no tool."""
        with self._pool.transaction() as conn:
            attempts.mark_replay_safe(conn, job_id, replay_safe)

    def finish_job(
        self, job_id: str, state: str, *, text: str = "", target: str = "", error: str = "",
        failure_kind: str | None = None, model: str = "", duration_ms: int | None = None,
        tokens: dict[str, int | None] | None = None, attempts: int | None = None,
        skipped_targets: int | None = None, replay_safe: bool | None = None, queued_only: bool = False,
        next_target: str | None = None,
    ) -> bool:
        """Finish the job; report whether this call moved it out of a non-terminal state."""
        changed = jobs.finish(
            self._connection, job_id, state, result=text, error=error, failure_kind=failure_kind, target=target,
            model=model, duration_ms=duration_ms, tokens=tokens, attempts=attempts, replay_safe=replay_safe,
            queued_only=queued_only, next_target=next_target or "",
        )
        if changed:
            self._transcripts.write_result(job_id, text)
        return changed

    def finish_fresh_job_success(
        self, *, job_id: str, project_id: str, session: str, workflow: str, target: str, target_key: str,
        backend_session_id: str, text: str, failure_kind: str | None = None, model: str = "",
        duration_ms: int | None = None, tokens: dict[str, int | None] | None = None,
        attempts: int | None = None, skipped_targets: int | None = None, replay_safe: bool | None = None,
    ) -> bool:
        with self._pool.transaction() as conn:
            changed = jobs.finish(
                conn, job_id, "succeeded", result=text, target=target, failure_kind=failure_kind, model=model,
                duration_ms=duration_ms, tokens=tokens, attempts=attempts, replay_safe=replay_safe,
            )
            if changed:
                sessions.store_backend_session(
                    conn, project_id, session, workflow, target_key, backend_session_id, clear=True
                )
        if changed:
            self._transcripts.write_result(job_id, text)
        return changed

    # Questions

    def ask_question(self, job_id: str, text: str) -> int | None:
        """Open a question; None when the job already has one open; raises `JobNotRunning` unless it is running."""
        return questions.ask_if_none_open(self._connection, job_id, text)

    def question(self, question_id: int) -> dict[str, Any] | None:
        return questions.get(self._connection, question_id)

    def open_question(self, job_id: str) -> dict[str, Any] | None:
        rows = questions.open_for_job(self._connection, job_id)
        return rows[0] if rows else None

    def answer_question(self, question_id: int, text: str) -> bool:
        return questions.answer(self._connection, question_id, text)

    def expire_question(self, question_id: int) -> bool:
        return questions.expire(self._connection, question_id)

    def wait_snapshot(self, job_ids: Sequence[str]) -> list[tuple[JobView | None, bool]]:
        """Read each job and whether it has an open question, for `Runtime.wait_jobs`."""
        return [(self.job(job_id), self.open_question(job_id) is not None) for job_id in job_ids]

    def interrupt_active_jobs(self) -> list[dict[str, Any]]:
        return jobs.interrupt_running(self._connection)

    def job_attempts(self, job_id: str) -> list[dict[str, Any]]:
        return attempts.for_job(self._connection, job_id)

    def job(self, job_id: str) -> JobView | None:
        row = self.job_record(job_id)
        return self.job_view(row) if row else None

    def jobs(self, project_id: str) -> list[JobView]:
        return [self.job_view(row) for row in jobs.for_project(self._connection, project_id)]

    def job_overview(
        self, project_id: str, *, recent_limit: int = 10
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        """Return active job records, the newest terminal records, and the count of older terminal jobs."""
        active, recent, older = jobs.overview(self._connection, project_id, recent_limit)
        return active, recent, older

    def _result_text(self, row: dict[str, Any] | sqlite3.Row) -> str:
        if row["content_pruned"]:
            return ""
        if row["result"] is not None:
            return row["result"]
        try:
            return self.result_path(row["id"]).read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def job_view(self, row: sqlite3.Row | dict[str, Any]) -> JobView:
        result = JobResult(
            text=self._result_text(row),
            error=row["error"],
            failure_kind=row["failure_kind"],
            model=row["model"],
            duration_ms=row["duration_ms"],
            tokens={key: row[column] for key, column in _TOKEN_COLUMNS},
            next_target=row["next_target"] or None,
        )
        return JobView(
            id=row["id"], project_id=row["project_id"], workflow=row["workflow"], profile=row["profile"],
            state=row["state"], session=row["session"], target_id=row["target"], from_job=row["from_job"],
            created_at=row["created_at"], updated_at=row["updated_at"], result=result,
        )

    def job_summaries(
        self, *, state: str | None = None, project_id: str | None = None, workflow: str | None = None,
        target: str | None = None, q: str | None = None, cursor: str | None = None, limit: int = 100,
    ) -> tuple[list[dict[str, Any]], str | None]:
        rows, next_cursor = jobs.summaries(
            self._connection, state=state, project_id=project_id, workflow=workflow, target=target, q=q,
            cursor=cursor, limit=limit,
        )
        return rows, next_cursor

    def job_filter_options(self) -> dict[str, Any]:
        return jobs.filter_options(self._connection)

    def job_detail(self, job_id: str) -> dict[str, Any] | None:
        row = jobs.detail(self._connection, job_id)
        if row is None:
            return None
        result = {
            "text": self._result_text(row),
            "error": row["error"],
            "failure_kind": row["failure_kind"],
            "model": row["model"],
            "duration_ms": row["duration_ms"],
            "tokens": {key: row[column] for key, column in _TOKEN_COLUMNS},
        }
        keys = ("id", "state", "project_id", "project_root", "workflow", "profile", "target", "session",
                "failure_kind", "created_at", "updated_at", "started_at", "finished_at", "prompt")
        return {**{key: row[key] for key in keys}, "from_job": row["from_job"], "result": result}

    # Retention

    def prune_retention(self, *, content_before: str, rows_before: str) -> None:
        """Delete jobs last updated before `rows_before`; drop prompt, result, and files of those before `content_before`."""
        jobs.prune(
            self._connection, content_before=content_before, rows_before=rows_before, remove=self._transcripts.remove
        )

    # Transcripts

    def append_stream(self, job_id: str, events: Sequence[dict[str, Any]]) -> None:
        """Append events as JSON lines; an event's seq is its line number."""
        self._transcripts.append(self._connection, job_id, events)

    def read_stream(self, job_id: str, after: int, limit: int) -> tuple[list[dict[str, Any]], int, bool, bool]:
        """Committed events after line `after`, the last seq, whether more are committed, and whether the file exists."""
        events, last, more = self._transcripts.read(self._connection, job_id, after, limit)
        return events, last, more, self.stream_path(job_id).exists()

    # Sessions

    def sticky_target(self, project_id: str, session: str, workflow: str) -> str:
        return sessions.sticky_target(self._connection, project_id, session, workflow)

    def session(self, project_id: str, session: str, workflow: str, target_key: str) -> str:
        return sessions.backend_session(self._connection, project_id, session, workflow, target_key)

    def store_session(self, *, project_id: str, session: str, workflow: str, target_key: str,
                      backend_session_id: str) -> None:
        sessions.store_backend_session(self._connection, project_id, session, workflow, target_key, backend_session_id)

    # Target health

    def target_health(self, target_id: str) -> dict[str, Any]:
        return health.get(self._connection, target_id)

    def claim_target_probe(self, target_id: str, job_id: str, now: str) -> bool:
        return health.claim_probe(self._connection, target_id, job_id, now)

    def release_target_probe(self, target_id: str, job_id: str = "") -> None:
        health.release_probe(self._connection, target_id, job_id)

    def reset_orphaned_target_probes(self, now: str | None = None) -> int:
        return health.reset_orphaned_probes(self._connection, now)

    def record_target_success(self, target_id: str, base_cooldown_s: int = 60, job_id: str | None = None) -> None:
        health.record_success(self._connection, target_id, base_cooldown_s, job_id)

    def record_target_failure(
        self, target_id: str, circuit_open_until: str = "", *, threshold: int = 3, base_cooldown_s: int = 60,
        max_cooldown_s: int = 900, failed_probe: bool = False, immediate: bool = False,
        job_id: str | None = None,
    ) -> int:
        return health.record_failure(
            self._connection, target_id, circuit_open_until, threshold=threshold, base_cooldown_s=base_cooldown_s,
            max_cooldown_s=max_cooldown_s, failed_probe=failed_probe, immediate=immediate,
            job_id=job_id,
        )

    # Cards

    def create_card(self, *, card_id: str, project_id: str, title: str, body: str,
                    job_ids: Sequence[str]) -> dict[str, Any]:
        return cards.create(self._connection, card_id=card_id, project_id=project_id, title=title, body=body,
                            job_ids=job_ids)

    def move_card(self, *, card_id: str, state: str, job_ids: Sequence[str], note: str) -> dict[str, Any]:
        return cards.move(self._connection, card_id=card_id, state=state, job_ids=job_ids, note=note)

    def list_cards(self, *, project_id: str | None, limit: int | None) -> dict[str, Any]:
        return cards.list_cards(self._connection, project_id=project_id, limit=limit)

    def card_detail(self, card_id: str) -> dict[str, Any] | None:
        return cards.detail(self._connection, card_id)
