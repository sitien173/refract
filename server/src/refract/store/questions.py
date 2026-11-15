"""Questions a running job asks its caller; answers use compare-and-set on `open`."""

from __future__ import annotations

import sqlite3
from typing import Any

from refract.store.pool import writes
from refract.store.schema import utc_now


class JobNotRunning(Exception):
    """The job is missing or no longer running, so it cannot register a question."""


@writes
def ask(conn: sqlite3.Connection, job_id: str, text: str, attempt_id: int | None = None) -> int:
    return conn.execute(
        "INSERT INTO questions(job_id, attempt_id, text, state, asked_at) VALUES (?, ?, ?, 'open', ?)",
        (job_id, attempt_id, text, utc_now()),
    ).lastrowid


@writes
def ask_if_none_open(conn: sqlite3.Connection, job_id: str, text: str, attempt_id: int | None = None) -> int | None:
    """Insert an open question unless the job already has one; the checks and the insert share one transaction.

    Raises `JobNotRunning` when the job is not `running`, so a finished job never gains an open question.
    Without an explicit `attempt_id` the question belongs to the job's open attempt, which is how the runner
    learns that an attempt asked a question.
    """
    state = conn.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()
    if state is None or state["state"] != "running":
        raise JobNotRunning(job_id)
    if conn.execute("SELECT 1 FROM questions WHERE job_id=? AND state='open'", (job_id,)).fetchone():
        return None
    if attempt_id is None:
        open_attempt = conn.execute(
            "SELECT id FROM attempts WHERE job_id=? AND state='running' ORDER BY seq DESC LIMIT 1", (job_id,)
        ).fetchone()
        attempt_id = open_attempt["id"] if open_attempt else None
    return ask(conn, job_id, text, attempt_id)


def asked_during(conn: sqlite3.Connection, attempt_id: int) -> bool:
    """Whether the worker asked any question, open, answered, or expired, during the attempt."""
    return conn.execute("SELECT 1 FROM questions WHERE attempt_id=?", (attempt_id,)).fetchone() is not None


def get(conn: sqlite3.Connection, question_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM questions WHERE id=?", (question_id,)).fetchone()
    return dict(row) if row else None


@writes
def answer(conn: sqlite3.Connection, question_id: int, text: str) -> bool:
    """Record the answer; false when the question is not open any more."""
    return conn.execute(
        "UPDATE questions SET state='answered', answer=?, answered_at=? WHERE id=? AND state='open'",
        (text, utc_now(), question_id),
    ).rowcount == 1


@writes
def expire(conn: sqlite3.Connection, question_id: int) -> bool:
    """Expire the question; false when it is not open any more."""
    return conn.execute("UPDATE questions SET state='expired' WHERE id=? AND state='open'", (question_id,)).rowcount == 1


@writes
def expire_all_open(conn: sqlite3.Connection) -> int:
    """Expire every open question; worker tokens do not survive a restart, so none can be answered."""
    return conn.execute("UPDATE questions SET state='expired' WHERE state='open'").rowcount


@writes
def expire_open(conn: sqlite3.Connection, job_id: str) -> int:
    return conn.execute("UPDATE questions SET state='expired' WHERE job_id=? AND state='open'", (job_id,)).rowcount


def open_for_job(conn: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM questions WHERE job_id=? AND state='open' ORDER BY id", (job_id,)).fetchall()
    return [dict(row) for row in rows]
