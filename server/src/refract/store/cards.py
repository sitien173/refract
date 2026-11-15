"""Kanban cards linked to jobs."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any

from refract.store.pool import writes
from refract.store.schema import utc_now

TITLE_MAX = 200
BODY_MAX = 4000
NOTE_MAX = 1000
CALL_LINKS_MAX = 16
LINKS_MAX = 64
EDGES = {
    "todo": {"in_progress", "cancelled"},
    "in_progress": {"in_review", "cancelled"},
    "in_review": {"done", "in_progress", "cancelled"},
    "done": set(),
    "cancelled": set(),
}
_SELECT = (
    "SELECT c.id, c.project_id, p.root AS project_root, c.title, c.state, c.created_at, c.updated_at "
    "FROM cards c JOIN projects p ON p.id=c.project_id"
)


class CardError(ValueError):
    """A card request the store refuses; code is one of unknown_card, invalid_state, unknown_job, invalid_request."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _call_job_ids(job_ids: Sequence[str]) -> list[str]:
    """Validate the per-call job IDs and drop duplicates, keeping order."""
    if len(job_ids) > CALL_LINKS_MAX:
        raise CardError("invalid_request", f"at most {CALL_LINKS_MAX} job_ids per call")
    if any(not 1 <= len(job_id) <= 64 for job_id in job_ids):
        raise CardError("invalid_request", "each job ID must be 1 to 64 characters")
    return list(dict.fromkeys(job_ids))


@writes
def create(conn: sqlite3.Connection, *, card_id: str, project_id: str, title: str, body: str,
           job_ids: Sequence[str]) -> dict[str, Any]:
    if not 1 <= len(title) <= TITLE_MAX or not title.strip():
        raise CardError("invalid_request", f"title must be 1 to {TITLE_MAX} characters and not blank")
    if len(body) > BODY_MAX:
        raise CardError("invalid_request", f"body must be at most {BODY_MAX} characters")
    job_ids = _call_job_ids(job_ids)
    now = utc_now()
    if conn.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
        raise CardError("invalid_request", f"unknown project {project_id}")
    if conn.execute("SELECT 1 FROM cards WHERE id=?", (card_id,)).fetchone() is not None:
        raise CardError("invalid_request", f"card {card_id} already exists")
    conn.execute(
        "INSERT INTO cards(id, project_id, title, body, state, created_at, updated_at) VALUES (?, ?, ?, ?, 'todo', ?, ?)",
        (card_id, project_id, title, body, now, now),
    )
    conn.execute(
        "INSERT INTO card_moves(card_id, from_state, to_state, note, at) VALUES (?, NULL, 'todo', '', ?)", (card_id, now)
    )
    _link_jobs(conn, card_id, job_ids, now)
    return _row(conn, card_id)


@writes
def move(conn: sqlite3.Connection, *, card_id: str, state: str, job_ids: Sequence[str], note: str) -> dict[str, Any]:
    if len(note) > NOTE_MAX:
        raise CardError("invalid_request", f"note must be at most {NOTE_MAX} characters")
    job_ids = _call_job_ids(job_ids)
    now = utc_now()
    row = conn.execute("SELECT state FROM cards WHERE id=?", (card_id,)).fetchone()
    if row is None:
        raise CardError("unknown_card", f"unknown card {card_id}")
    current = row["state"]
    moved = state != current
    if moved and state not in EDGES[current]:
        raise CardError("invalid_state", f"cannot move from {current} to {state}; current state {current}")
    linked = _link_jobs(conn, card_id, job_ids, now)
    if moved:
        if conn.execute(
            "UPDATE cards SET state=?, updated_at=? WHERE id=? AND state=?", (state, now, card_id, current)
        ).rowcount == 0:
            latest = conn.execute("SELECT state FROM cards WHERE id=?", (card_id,)).fetchone()["state"]
            raise CardError("invalid_state", f"card changed; current state {latest}")
        conn.execute(
            "INSERT INTO card_moves(card_id, from_state, to_state, note, at) VALUES (?, ?, ?, ?, ?)",
            (card_id, current, state, note, now),
        )
    elif linked:
        conn.execute("UPDATE cards SET updated_at=? WHERE id=?", (now, card_id))
    return {"card": _row(conn, card_id), "moved": moved}


def list_cards(conn: sqlite3.Connection, *, project_id: str | None, limit: int | None) -> dict[str, Any]:
    sql = _SELECT + (" WHERE c.project_id=?" if project_id is not None else "")
    sql += " ORDER BY c.state IN ('done','cancelled'), c.updated_at DESC, c.id DESC"
    params: list[Any] = [] if project_id is None else [project_id]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit + 1)
    cards = [dict(row) for row in conn.execute(sql, params).fetchall()]
    truncated = limit is not None and len(cards) > limit
    cards = cards[:limit] if truncated else cards
    links: dict[str, list[str]] = {}
    for link in conn.execute(
        "SELECT cj.card_id, cj.job_id FROM card_jobs cj JOIN cards c ON c.id=cj.card_id"
        + (" WHERE c.project_id=?" if project_id is not None else "")
        + " ORDER BY cj.linked_at, cj.job_id",
        [] if project_id is None else [project_id],
    ):
        links.setdefault(link["card_id"], []).append(link["job_id"])
    for card in cards:
        card["job_ids"] = links.get(card["id"], [])
    return {"cards": cards, "truncated": truncated}


def detail(conn: sqlite3.Connection, card_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT c.id, c.project_id, p.root AS project_root, c.title, c.body, c.state, c.created_at, c.updated_at "
        "FROM cards c JOIN projects p ON p.id=c.project_id WHERE c.id=?",
        (card_id,),
    ).fetchone()
    if row is None:
        return None
    moves = conn.execute(
        "SELECT id, from_state, to_state, note, at FROM card_moves WHERE card_id=? ORDER BY id", (card_id,)
    ).fetchall()
    # A job's target is the one its latest attempt ran on.
    jobs = conn.execute(
        "SELECT cj.job_id, cj.linked_at, j.id IS NOT NULL AS available, j.workflow, j.state, "
        "CASE WHEN j.id IS NULL THEN NULL ELSE COALESCE("
        "(SELECT a.target FROM attempts a WHERE a.job_id=j.id ORDER BY a.seq DESC LIMIT 1), '') END AS target "
        "FROM card_jobs cj LEFT JOIN jobs j ON j.id=cj.job_id WHERE cj.card_id=? ORDER BY cj.linked_at, cj.job_id",
        (card_id,),
    ).fetchall()
    return {
        "card": dict(row),
        "moves": [dict(move) for move in moves],
        "jobs": [{**dict(job), "available": bool(job["available"])} for job in jobs],
    }


def _row(conn: sqlite3.Connection, card_id: str) -> dict[str, Any]:
    row = dict(conn.execute(_SELECT + " WHERE c.id=?", (card_id,)).fetchone())
    row["job_ids"] = [
        link["job_id"]
        for link in conn.execute("SELECT job_id FROM card_jobs WHERE card_id=? ORDER BY linked_at, job_id", (card_id,))
    ]
    return row


def _link_jobs(conn: sqlite3.Connection, card_id: str, job_ids: Sequence[str], now: str) -> int:
    """Link jobs not yet linked; return how many are new. Runs inside a transaction."""
    for job_id in job_ids:
        if conn.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone() is None:
            raise CardError("unknown_job", f"unknown job {job_id}")
    added = 0
    for job_id in job_ids:
        added += conn.execute(
            "INSERT OR IGNORE INTO card_jobs(card_id, job_id, linked_at) VALUES (?, ?, ?)", (card_id, job_id, now)
        ).rowcount
    total = conn.execute("SELECT COUNT(*) FROM card_jobs WHERE card_id=?", (card_id,)).fetchone()[0]
    if total > LINKS_MAX:
        raise CardError("invalid_request", f"a card holds at most {LINKS_MAX} job links")
    return added
