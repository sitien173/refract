"""Contract tests for DB schema v1, .bak migration, transcript cursor, and SSE events."""

from __future__ import annotations

import http.client
import json
import re
import sqlite3
import time
from typing import get_args

import pytest

from refract.models import JobState

from tests.contract.conftest import ContractDaemon, call_tool_json, wait_for_job


def test_schema_v1_user_version_and_old_db_renamed_to_bak(daemon: ContractDaemon) -> None:
    """Fresh DB has user_version=1 without job_metrics; an old DB is renamed to .<ver>.bak."""
    assert daemon.query_db("PRAGMA user_version")[0]["user_version"] == 1
    tables = {
        r["name"]
        for r in daemon.query_db("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "job_metrics" not in tables
    assert "telemetry_outbox" not in tables
    assert "attempts" in tables
    assert "questions" in tables

    daemon.stop()
    daemon.db_path.unlink(missing_ok=True)
    for suffix in ("-wal", "-shm"):
        daemon.db_path.with_name(daemon.db_path.name + suffix).unlink(missing_ok=True)

    conn = sqlite3.connect(daemon.db_path)
    try:
        conn.execute("PRAGMA user_version = 21")
        conn.execute("CREATE TABLE legacy (id INTEGER PRIMARY KEY)")
        conn.commit()
    finally:
        conn.close()

    daemon.start()
    bak_path = daemon.home / "refract.db.21.bak"
    assert bak_path.exists()
    assert daemon.query_db("PRAGMA user_version")[0]["user_version"] == 1


_REQUIRED_CHECKS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("jobs", "state", get_args(JobState)),
    ("attempts", "state", get_args(JobState)),
    ("attempts", "reason", ("initial", "retry", "fresh_session", "fallback")),
    ("questions", "state", ("open", "answered", "expired")),
)
_CARD_STATES = ("todo", "in_progress", "in_review", "done", "cancelled")


def _check_bodies_for_column(sql: str, column: str) -> list[str]:
    """Return the parenthesized body of every CHECK in sql that references column as an identifier."""
    bodies: list[str] = []
    for keyword in re.finditer(r"\bCHECK\b", sql, re.IGNORECASE):
        start = sql.find("(", keyword.end())
        if start == -1 or sql[keyword.end() : start].strip():
            continue
        depth = 0
        in_string = False
        for index in range(start, len(sql)):
            char = sql[index]
            if char == "'":
                in_string = not in_string
            elif in_string:
                continue
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    bodies.append(sql[start + 1 : index])
                    break
    unquoted = [re.sub(r"'[^']*'", "''", body) for body in bodies]
    pattern = re.compile(rf"\b{re.escape(column)}\b", re.IGNORECASE)
    return [body for body, plain in zip(bodies, unquoted, strict=True) if pattern.search(plain)]


def test_check_body_extractor_handles_in_or_and_prefix_forms() -> None:
    in_form = "CREATE TABLE t (state TEXT CHECK (state IN ('a', 'b')))"
    or_form = "CREATE TABLE t (\"state\" TEXT, CHECK (\"state\" = 'a' OR state = 'b'))"
    prefix = "CREATE TABLE t (substate TEXT CHECK (substate IN ('x')), state TEXT)"
    assert _check_bodies_for_column(in_form, "state") == ["state IN ('a', 'b')"]
    assert _check_bodies_for_column(or_form, "state") == ["\"state\" = 'a' OR state = 'b'"]
    assert _check_bodies_for_column(prefix, "state") == []
    assert _check_bodies_for_column(prefix, "substate") == ["substate IN ('x')"]


def _assert_state_check(daemon: ContractDaemon, table: str, column: str, allowed: tuple[str, ...]) -> None:
    rows = daemon.query_db("SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,))
    assert rows, f"table {table} is missing"
    sql = rows[0]["sql"]
    bodies = _check_bodies_for_column(sql, column)
    assert bodies, f"{table}.{column} has no CHECK constraint referencing {column}: {sql}"
    found = {literal for body in bodies for literal in re.findall(r"'([^']*)'", body)}
    assert found == set(allowed), (
        f"{table}.{column} CHECK literals {sorted(found)} differ from expected {sorted(allowed)}; "
        f"bodies: {bodies}"
    )
    for value in allowed:
        assert _check_admits(bodies, column, value), f"{table}.{column} CHECK rejects {value!r}: {bodies}"
    assert not _check_admits(bodies, column, "__not_a_state__"), (
        f"{table}.{column} CHECK admits an unknown value: {bodies}"
    )


def _check_admits(bodies: list[str], column: str, value: str) -> bool:
    """Evaluate the CHECK bodies for one column value in a scratch in-memory database."""
    conn = sqlite3.connect(":memory:")
    try:
        for body in bodies:
            row = conn.execute(f'WITH t("{column}") AS (SELECT ?) SELECT ({body}) FROM t', (value,)).fetchone()
            if row[0] is not None and not row[0]:
                return False
        return True
    finally:
        conn.close()


def test_check_admits_rejects_inverted_constraint() -> None:
    assert _check_admits(["state IN ('a', 'b')"], "state", "a")
    assert not _check_admits(["state IN ('a', 'b')"], "state", "c")
    assert not _check_admits(["state NOT IN ('a', 'b')"], "state", "a")
    assert _check_admits(["\"state\" = 'a' OR state = 'b'"], "state", "b")


def test_cards_state_check_is_preserved(daemon: ContractDaemon) -> None:
    """The existing cards.state CHECK keeps listing exactly the card states."""
    _assert_state_check(daemon, "cards", "state", _CARD_STATES)


@pytest.mark.parametrize(("table", "column", "allowed"), _REQUIRED_CHECKS)
def test_schema_v1_state_check_constraints(
    daemon: ContractDaemon, table: str, column: str, allowed: tuple[str, ...]
) -> None:
    """Schema v1 declares a CHECK on each state column listing exactly the DESIGN.md values."""
    _assert_state_check(daemon, table, column, allowed)


@pytest.mark.asyncio
async def test_output_route_never_reads_past_events_committed(daemon: ContractDaemon) -> None:
    """/dashboard/api/jobs/{id}/output stops at the DB events_committed cursor."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {"path": str(daemon.repo), "workflow": "consult", "prompt": "Cursor check"},
        )
        job_id = submitted["job"]["id"]
        await wait_for_job(session, job_id, timeout_s=15)

    committed = daemon.query_db("SELECT events_committed FROM jobs WHERE id = ?", (job_id,))[0][
        "events_committed"
    ]
    assert committed > 0

    stream_file = daemon.home / "streams" / f"{job_id}.jsonl"
    with stream_file.open("a", encoding="utf-8") as handle:
        handle.write('{"seq": 9999, "kind": "assistant.text.delta", "data": {"text": "UNCOMMITTED"}}\n')

    resp = await daemon.async_http_request("GET", f"/dashboard/api/jobs/{job_id}/output")
    assert resp.status == 200
    payload = resp.json()
    assert payload.get("available") is True
    events = payload.get("events", [])
    assert len(events) > 0
    assert payload.get("next", 0) <= committed
    serialized = [json.dumps(e) for e in events]
    assert any("E2E backend completed" in s for s in serialized)
    assert not any("UNCOMMITTED" in s for s in serialized)


def _split_sse_frames(buffer: bytes) -> tuple[list[str], bytes]:
    """Normalize CRLF on the whole buffer, return decoded complete frames and the unconsumed rest."""
    *complete, rest = buffer.replace(b"\r\n", b"\n").split(b"\n\n")
    return [frame.decode("utf-8") for frame in complete], rest


def test_split_sse_frames_handles_split_crlf_and_split_utf8() -> None:
    chunks = [b'data: {"t": "\xc3', b'\xa9"}\r', b"\n\r", b"\n", b"data: next\r\n\r\n"]
    buffer = b""
    frames: list[str] = []
    for chunk in chunks:
        buffer += chunk
        complete, buffer = _split_sse_frames(buffer)
        frames.extend(complete)
    assert frames == ['data: {"t": "é"}', "data: next"]
    assert buffer == b""


def _read_sse_until_terminal(
    conn: http.client.HTTPConnection,
    resp: http.client.HTTPResponse,
    job_id: str,
    *,
    timeout_s: float = 10.0,
) -> dict[str, object]:
    """Read chunk-decoded SSE bytes, parse complete frames, and return the job's terminal event."""
    deadline = time.monotonic() + timeout_s
    buffer = b""
    while time.monotonic() < deadline:
        if conn.sock is not None:
            conn.sock.settimeout(max(0.05, deadline - time.monotonic()))
        try:
            chunk = resp.read1(4096)
        except TimeoutError:
            break
        if not chunk:
            break
        buffer += chunk
        frames, buffer = _split_sse_frames(buffer)
        for frame in frames:
            data_lines = [
                line[len("data:") :].strip()
                for line in frame.split("\n")
                if line.startswith("data:")
            ]
            if not data_lines:
                continue
            try:
                payload = json.loads("\n".join(data_lines))
            except ValueError:
                continue
            if isinstance(payload, dict) and payload.get("job_id") == job_id and payload.get("kind") == "terminal":
                return payload
    raise TimeoutError(f"Did not receive terminal SSE event for {job_id} within {timeout_s}s")


@pytest.mark.asyncio
async def test_sse_events_endpoint_streams_terminal_event(daemon: ContractDaemon) -> None:
    """GET /dashboard/api/events streams SSE events including terminal for a finished job."""
    conn = http.client.HTTPConnection("127.0.0.1", daemon.port, timeout=10)
    try:
        conn.request("GET", "/dashboard/api/events")
        resp = conn.getresponse()
        assert resp.status == 200
        assert "text/event-stream" in resp.getheader("Content-Type", "")

        async with daemon.mcp_session() as session:
            submitted = await call_tool_json(
                session,
                "submit",
                {"path": str(daemon.repo), "workflow": "consult", "prompt": "SSE check"},
            )
            job_id = submitted["job"]["id"]
            await wait_for_job(session, job_id, timeout_s=15)

        frame = _read_sse_until_terminal(conn, resp, job_id, timeout_s=10.0)
        assert frame["job_id"] == job_id
    finally:
        conn.close()
