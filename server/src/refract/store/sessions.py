"""Sticky target routes and per-target backend session IDs."""

from __future__ import annotations

import sqlite3

from refract.store.pool import writes
from refract.store.schema import utc_now


def sticky_target(conn: sqlite3.Connection, project_id: str, session: str, workflow: str) -> str:
    row = conn.execute(
        "SELECT sticky_target FROM session_routes WHERE project_id=? AND session=? AND workflow=?",
        (project_id, session, workflow),
    ).fetchone()
    return row["sticky_target"] if row else ""


@writes
def set_sticky_target(conn: sqlite3.Connection, project_id: str, session: str, workflow: str, target: str) -> None:
    conn.execute(
        """INSERT INTO session_routes(project_id, session, workflow, sticky_target, updated_at) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(project_id, session, workflow) DO UPDATE SET
           sticky_target=excluded.sticky_target, updated_at=excluded.updated_at""",
        (project_id, session, workflow, target, utc_now()),
    )


def backend_session(conn: sqlite3.Connection, project_id: str, session: str, workflow: str, target_key: str) -> str:
    row = conn.execute(
        "SELECT backend_session_id FROM backend_sessions WHERE project_id=? AND session=? AND workflow=? AND target_key=?",
        (project_id, session, workflow, target_key),
    ).fetchone()
    return row["backend_session_id"] if row else ""


@writes
def store_backend_session(
    conn: sqlite3.Connection, project_id: str, session: str, workflow: str, target_key: str,
    backend_session_id: str, *, clear: bool = False,
) -> None:
    """Upsert one target's backend session; `clear` first drops every target's session for this route."""
    if clear:
        conn.execute(
            "DELETE FROM backend_sessions WHERE project_id=? AND session=? AND workflow=?",
            (project_id, session, workflow),
        )
    if backend_session_id:
        conn.execute(
            """INSERT INTO backend_sessions(project_id, session, workflow, target_key, backend_session_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(project_id, session, workflow, target_key) DO UPDATE SET
               backend_session_id=excluded.backend_session_id, updated_at=excluded.updated_at""",
            (project_id, session, workflow, target_key, backend_session_id, utc_now()),
        )
