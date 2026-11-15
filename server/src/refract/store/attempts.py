"""Attempt rows: one per target try of a job."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from refract.store.pool import writes
from refract.store.schema import utc_now

TOKEN_COLUMNS = (
    ("context_used", "tok_context_used"),
    ("context_window", "tok_context_window"),
    ("input", "tok_input"),
    ("output", "tok_output"),
    ("cache_read", "tok_cache_read"),
    ("cache_write", "tok_cache_write"),
)


def token_values(tokens: dict[str, int | None] | None) -> tuple[int | None, ...]:
    """Token counters in column order; a missing key stays NULL."""
    tokens = tokens or {}
    return tuple(tokens.get(key) for key, _column in TOKEN_COLUMNS)


def backend_for_target(plan_json: str, target: str) -> str:
    try:
        targets = json.loads(plan_json).get("targets", [])
        if isinstance(targets, list):
            backend = next((item.get("backend") for item in targets
                            if isinstance(item, dict) and item.get("id") == target), "")
            return backend if isinstance(backend, str) else ""
    except (ValueError, TypeError, AttributeError):
        pass
    return ""


def for_job(conn: sqlite3.Connection, job_id: str) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM attempts WHERE job_id=? ORDER BY seq", (job_id,)).fetchall()
    return [dict(row) for row in rows]


def counts_by_reason(conn: sqlite3.Connection, since: str) -> dict[str, int]:
    """Attempts started at or after `since`, counted by reason."""
    rows = conn.execute(
        "SELECT reason, COUNT(*) FROM attempts WHERE started_at >= ? GROUP BY reason ORDER BY reason", (since,)
    ).fetchall()
    return {row[0]: row[1] for row in rows}


@writes
def begin(conn: sqlite3.Connection, job_id: str, target: str) -> int:
    """Open an attempt on `target`; an open attempt on the same target is reused. Returns the attempt id."""
    rows = conn.execute("SELECT * FROM attempts WHERE job_id=? ORDER BY seq", (job_id,)).fetchall()
    last = rows[-1] if rows else None
    if last is not None and last["state"] == "running":
        if last["target"] == target:
            return last["id"]
        _close(conn, last["id"], "failed", "transient")
    reason = "initial" if last is None else "fallback" if last["target"] != target else "retry"
    return _insert(conn, job_id, len(rows) + 1, reason, target, "running", None)


@writes
def begin_with_reason(conn: sqlite3.Connection, job_id: str, target: str, reason: str) -> int:
    """Open a `running` attempt on `target` with the reason the runner chose. Returns the attempt id."""
    seq = conn.execute("SELECT COUNT(*) FROM attempts WHERE job_id=?", (job_id,)).fetchone()[0] + 1
    return _insert(conn, job_id, seq, reason, target, "running", None)


@writes
def finish(
    conn: sqlite3.Connection, attempt_id: int, state: str, *, failure_kind: str | None, replay_safe: bool,
    model: str, duration_ms: int | None, tokens: dict[str, int | None] | None,
) -> None:
    """Close one attempt with its own outcome, duration, and tokens."""
    conn.execute(
        """UPDATE attempts SET state=?, failure_kind=?, model=?, finished_at=?, duration_ms=?, replay_safe=?,
           tok_context_used=?, tok_context_window=?, tok_input=?, tok_output=?, tok_cache_read=?, tok_cache_write=?
           WHERE id=?""",
        (state, failure_kind, model or None, utc_now(), duration_ms, int(bool(replay_safe)),
         *token_values(tokens), attempt_id),
    )


def finish_job_attempts(
    conn: sqlite3.Connection, job_id: str, state: str, *, target: str, failure_kind: str | None,
    model: str, duration_ms: int | None, tokens: dict[str, int | None] | None, attempts: int | None,
    replay_safe: bool | None = None,
) -> None:
    """Close the job's attempt rows; the last one carries the final state and the job totals.

    With nothing to record (no attempt rows and no target) no row is written. An `attempts` count above the rows
    present adds `retry` rows so the table holds that many. `replay_safe` is the final attempt's value; rows closed
    before it were followed by a retry or fallback, which the runtime allows only for replay-safe attempts.
    """
    rows = conn.execute("SELECT * FROM attempts WHERE job_id=? ORDER BY seq", (job_id,)).fetchall()
    target = target or (rows[-1]["target"] if rows else "")
    if not rows and not target:
        return
    open_row = rows[-1] if rows and rows[-1]["state"] == "running" else None
    total = max(attempts or 1, len(rows) + (0 if open_row else 1))
    if open_row is not None and total == len(rows):
        final_id = open_row["id"]
    else:
        if open_row is not None:
            _close(conn, open_row["id"], "failed", "transient")
        for seq in range(len(rows) + 1, total + 1):
            final_id = _insert(conn, job_id, seq, "initial" if seq == 1 else "retry", target, "running", None)
            if seq < total:
                _close(conn, final_id, "failed", "transient")
    conn.execute(
        """UPDATE attempts SET state=?, failure_kind=?, target=?, model=?, finished_at=?, duration_ms=?, replay_safe=?,
           tok_context_used=?, tok_context_window=?, tok_input=?, tok_output=?, tok_cache_read=?, tok_cache_write=?
           WHERE id=?""",
        (state, failure_kind, target, model or None, utc_now(), duration_ms, int(bool(replay_safe)),
         *token_values(tokens), final_id),
    )


def mark_replay_safe(conn: sqlite3.Connection, job_id: str, replay_safe: bool) -> None:
    """Record the evidence for the job's open attempt: it streamed and ran no tool."""
    conn.execute("UPDATE attempts SET replay_safe=? WHERE job_id=? AND state='running'", (int(replay_safe), job_id))


def close_running(conn: sqlite3.Connection, job_id: str, state: str) -> None:
    conn.execute(
        "UPDATE attempts SET state=?, finished_at=? WHERE job_id=? AND state='running'", (state, utc_now(), job_id)
    )


def _close(conn: sqlite3.Connection, attempt_id: int, state: str, failure_kind: str | None) -> None:
    conn.execute(
        "UPDATE attempts SET state=?, failure_kind=?, finished_at=? WHERE id=?",
        (state, failure_kind, utc_now(), attempt_id),
    )


def _insert(conn: sqlite3.Connection, job_id: str, seq: int, reason: str, target: str, state: str,
            model: str | None) -> int:
    plan = conn.execute("SELECT plan_json FROM jobs WHERE id=?", (job_id,)).fetchone()
    backend = backend_for_target(plan["plan_json"], target) if plan else ""
    return conn.execute(
        "INSERT INTO attempts(job_id, seq, reason, target, backend, model, state, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (job_id, seq, reason, target, backend, model, state, utc_now()),
    ).lastrowid
