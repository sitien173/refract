"""Projects and jobs: compare-and-set transitions, one-transaction terminal writes, listings, retention."""

from __future__ import annotations

import base64
import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from refract.models import TERMINAL_STATES
from refract.store import attempts as attempt_rows
from refract.store import health, questions, sessions
from refract.store.pool import tx, writes
from refract.store.schema import utc_now

_TERMINAL = tuple(sorted(TERMINAL_STATES))
_TERMINAL_SQL = ",".join("?" for _ in _TERMINAL)
_LATEST = "SELECT a.{column} FROM attempts a WHERE a.job_id=j.id {extra} ORDER BY a.seq DESC LIMIT 1"
_TARGET = "COALESCE((" + _LATEST.format(column="target", extra="") + "), '')"
# Model, duration, and token totals live on attempts; the job row reports them through these columns.
DERIVED = ", ".join([
    f"{_TARGET} AS target",
    "(" + _LATEST.format(column="model", extra="") + ") AS model",
    "(SELECT SUM(a.duration_ms) FROM attempts a WHERE a.job_id=j.id) AS duration_ms",
    *(f"(SELECT SUM(a.{column}) FROM attempts a WHERE a.job_id=j.id) AS {column}"
      for column in ("tok_input", "tok_output", "tok_cache_read", "tok_cache_write")),
    *(f"({_LATEST.format(column=column, extra=f'AND a.{column} IS NOT NULL')}) AS {column}"
      for column in ("tok_context_used", "tok_context_window")),
])
RECORD = f"SELECT j.*, {DERIVED} FROM jobs j"


def encode_cursor(created_at: str, job_id: str) -> str:
    raw = json.dumps([created_at, job_id]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
        if isinstance(data, list) and len(data) == 2 and all(isinstance(item, str) for item in data):
            return data[0], data[1]
    except Exception:
        pass
    raise ValueError("Invalid cursor")


@dataclass
class Pruned:
    content: list[str] = field(default_factory=list)
    rows: list[str] = field(default_factory=list)


@writes
def upsert_project(conn: sqlite3.Connection, project_id: str, root: str) -> dict[str, Any]:
    existing = conn.execute("SELECT id, created_at FROM projects WHERE root=?", (root,)).fetchone()
    created_at = existing["created_at"] if existing else utc_now()
    resolved_id = existing["id"] if existing else project_id
    conn.execute(
        "INSERT INTO projects(id, root, created_at) VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET root=excluded.root",
        (resolved_id, root, created_at),
    )
    return {"id": resolved_id, "root": root, "created_at": created_at}


def get_project(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return dict(row) if row else None


def list_projects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute("SELECT * FROM projects ORDER BY root")]


@writes
def create(
    conn: sqlite3.Connection, *, job_id: str, project_id: str, workflow: str, profile: str, prompt: str,
    plan_json: str, session: str, fresh: bool = False, from_job: str = "", target_pin: str = "",
) -> None:
    now = utc_now()
    conn.execute(
        """INSERT INTO jobs(id, project_id, workflow, profile, target_pin, session, fresh, from_job, prompt,
           state, plan_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)""",
        (job_id, project_id, workflow, profile, target_pin, session, 1 if fresh else 0, from_job, prompt,
         plan_json, now, now),
    )


def record(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    row = conn.execute(f"{RECORD} WHERE j.id=?", (job_id,)).fetchone()
    return dict(row) if row else None


@writes
def start(conn: sqlite3.Connection, job_id: str) -> bool:
    """Move a queued job to running; false when it is not queued."""
    now = utc_now()
    return conn.execute(
        "UPDATE jobs SET state='running', error='', started_at=?, updated_at=? WHERE id=? AND state='queued'",
        (now, now, job_id),
    ).rowcount == 1


@writes
def set_pgid(conn: sqlite3.Connection, job_id: str, pgid: int) -> None:
    conn.execute("UPDATE jobs SET pgid=? WHERE id=?", (pgid, job_id))


def finish(
    conn: sqlite3.Connection, job_id: str, state: str, *, result: str = "", error: str = "",
    failure_kind: str | None = None, target: str = "", model: str = "", duration_ms: int | None = None,
    tokens: dict[str, int | None] | None = None, attempts: int | None = None, replay_safe: bool | None = None,
    queued_only: bool = False, next_target: str = "",
) -> bool:
    """Compare-and-set a job to a terminal state; `queued_only` matches a `queued` job and nothing else.

    State, result, final attempt row, probe release, and sticky route commit in one transaction. A job that is
    already terminal or missing changes nothing and the call returns false.
    """
    with tx(conn):
        now = utc_now()
        changed = conn.execute(
            """UPDATE jobs SET state=?, result=?, error=?, failure_kind=?, next_target=?, finished_at=?, updated_at=?
               WHERE id=? AND state IN ({states})""".format(states="'queued'" if queued_only else "'queued', 'running'"),
            (state, result, error, failure_kind, next_target, now, now, job_id),
        ).rowcount == 1
        if not changed:
            return False
        questions.expire_open(conn, job_id)
        attempt_rows.finish_job_attempts(
            conn, job_id, state, target=target, failure_kind=failure_kind, model=model,
            duration_ms=duration_ms, tokens=tokens, attempts=attempts, replay_safe=replay_safe,
        )
        health.release_job_probes(conn, job_id)
        if state == "succeeded":
            row = conn.execute(f"{RECORD} WHERE j.id=?", (job_id,)).fetchone()
            if row["target"]:
                sessions.set_sticky_target(conn, row["project_id"], row["session"], row["workflow"], row["target"])
        return True


@writes
def interrupt_running(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Mark every running job interrupted and return the rows as they were."""
    rows = [dict(row) for row in conn.execute(f"{RECORD} WHERE j.state='running' ORDER BY j.created_at").fetchall()]
    now = utc_now()
    questions.expire_all_open(conn)
    for row in rows:
        if conn.execute(
            "UPDATE jobs SET state='interrupted', updated_at=?, finished_at=? WHERE id=? AND state='running'",
            (now, now, row["id"]),
        ).rowcount:
            attempt_rows.close_running(conn, row["id"], "interrupted")
    return rows


def queued(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    rows = conn.execute("SELECT id, project_id FROM jobs WHERE state='queued' ORDER BY created_at, id")
    return [(row["id"], row["project_id"]) for row in rows]


def active_counts(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT state, COUNT(*) FROM jobs WHERE state IN ('queued', 'running') GROUP BY state")
    counts = {row[0]: row[1] for row in rows}
    return {"queued": counts.get("queued", 0), "running": counts.get("running", 0)}


def for_project(conn: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(f"{RECORD} WHERE j.project_id=? ORDER BY j.created_at DESC", (project_id,))
    return [dict(row) for row in rows]


def overview(
    conn: sqlite3.Connection, project_id: str, recent_limit: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Active records, the newest terminal records, and the count of older terminal jobs."""
    active = conn.execute(
        f"{RECORD} WHERE j.project_id=? AND j.state NOT IN ({_TERMINAL_SQL}) ORDER BY j.created_at DESC",
        (project_id, *_TERMINAL),
    ).fetchall()
    recent = conn.execute(
        f"{RECORD} WHERE j.project_id=? AND j.state IN ({_TERMINAL_SQL}) ORDER BY j.updated_at DESC, j.id DESC LIMIT ?",
        (project_id, *_TERMINAL, recent_limit),
    ).fetchall()
    total = conn.execute(
        f"SELECT COUNT(*) FROM jobs WHERE project_id=? AND state IN ({_TERMINAL_SQL})", (project_id, *_TERMINAL)
    ).fetchone()[0]
    return [dict(row) for row in active], [dict(row) for row in recent], max(0, int(total) - len(recent))


def summaries(
    conn: sqlite3.Connection, *, state: str | None, project_id: str | None, workflow: str | None,
    target: str | None, q: str | None, cursor: str | None, limit: int,
) -> tuple[list[dict[str, Any]], str | None]:
    if limit <= 0 or limit > 200:
        raise ValueError("limit must be between 1 and 200")
    clauses: list[str] = []
    params: list[Any] = []
    for column, value in (("j.state", state), ("j.project_id", project_id), ("j.workflow", workflow), (_TARGET, target)):
        if value is not None:
            clauses.append(f"{column} = ?")
            params.append(value)
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("j.id LIKE ? ESCAPE '\\' COLLATE NOCASE")
        params.append(f"%{escaped}%")
    if cursor:
        created_at, cursor_id = decode_cursor(cursor)
        clauses.append("(j.created_at < ? OR (j.created_at = ? AND j.id < ?))")
        params.extend([created_at, created_at, cursor_id])
    sql = (
        f"SELECT j.id, j.state, j.project_id, COALESCE(p.root, '') AS project_root, j.workflow, j.profile, "
        f"{_TARGET} AS target, j.session, j.from_job, j.failure_kind, j.created_at, j.updated_at "
        "FROM jobs j LEFT JOIN projects p ON j.project_id = p.id"
        + (" WHERE " + " AND ".join(clauses) if clauses else "")
        + " ORDER BY j.created_at DESC, j.id DESC LIMIT ?"
    )
    rows = conn.execute(sql, (*params, limit + 1)).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1]["created_at"], page[-1]["id"]) if has_more and page else None
    return [dict(row) for row in page], next_cursor


def filter_options(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "states": [row[0] for row in conn.execute("SELECT DISTINCT state FROM jobs ORDER BY state")],
        "projects": [
            {"id": row["id"], "root": row["root"]}
            for row in conn.execute(
                "SELECT DISTINCT p.id, p.root FROM jobs j JOIN projects p ON j.project_id = p.id ORDER BY p.root, p.id"
            )
        ],
        "workflows": [
            row[0] for row in conn.execute("SELECT DISTINCT workflow FROM jobs WHERE workflow != '' ORDER BY workflow")
        ],
        "targets": [
            row[0] for row in conn.execute("SELECT DISTINCT target FROM attempts WHERE target != '' ORDER BY target")
        ],
    }


def detail(conn: sqlite3.Connection, job_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        f"SELECT j.*, {DERIVED}, COALESCE(p.root, '') AS project_root "
        "FROM jobs j LEFT JOIN projects p ON j.project_id = p.id WHERE j.id = ?",
        (job_id,),
    ).fetchone()
    return dict(row) if row else None


@writes
def prune(
    conn: sqlite3.Connection, *, content_before: str, rows_before: str, remove: Callable[[str], None],
) -> Pruned:
    """Two-tier retention: delete terminal jobs last updated before `rows_before`; null the content of those before
    `content_before`. `remove` deletes a job's files and treats a missing file as removed; a job whose `remove`
    raises OSError keeps its row and `content_pruned=0`, so the next sweep retries it."""
    pruned = Pruned()
    expired = [row["id"] for row in conn.execute(
        f"SELECT id FROM jobs WHERE state IN ({_TERMINAL_SQL}) AND updated_at < ?", (*_TERMINAL, rows_before))]
    pruned.rows = [job_id for job_id in expired if _removed(remove, job_id)]
    conn.executemany("DELETE FROM jobs WHERE id=?", [(job_id,) for job_id in pruned.rows])
    stale = [row["id"] for row in conn.execute(
        f"SELECT id FROM jobs WHERE state IN ({_TERMINAL_SQL}) AND updated_at < ? AND content_pruned=0",
        (*_TERMINAL, content_before))]
    pruned.content = [job_id for job_id in stale if _removed(remove, job_id)]
    conn.executemany(
        "UPDATE jobs SET prompt=NULL, result=NULL, content_pruned=1 WHERE id=?", [(job_id,) for job_id in pruned.content]
    )
    return pruned


def _removed(remove: Callable[[str], None], job_id: str) -> bool:
    try:
        remove(job_id)
    except OSError:
        return False
    return True
