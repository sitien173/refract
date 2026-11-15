"""Contract tests for automatic retry, fresh session, fallback, and replay_safe."""

from __future__ import annotations

import pytest

from tests.contract.conftest import ContractDaemon, call_tool_json, wait_for_job


@pytest.mark.asyncio
async def test_automatic_retry_records_attempt_rows(daemon: ContractDaemon) -> None:
    """A transient failure on a replay-safe attempt retries on the same target and records attempts."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "prompt": "E2E_MODE=fail_once_transient E2E_KEY=retry-1",
            },
        )
        job_id = submitted["job"]["id"]
        waited = await wait_for_job(session, job_id, timeout_s=15)
        assert waited["job"]["state"] == "succeeded"

    rows = daemon.query_db(
        "SELECT seq, reason, target, state, replay_safe FROM attempts WHERE job_id = ? ORDER BY seq",
        (job_id,),
    )
    assert [(r["seq"], r["reason"], r["target"], r["state"], r["replay_safe"]) for r in rows] == [
        (1, "initial", "claude-primary", "failed", 1),
        (2, "retry", "claude-primary", "succeeded", 1),
    ]


@pytest.mark.asyncio
async def test_context_overflow_triggers_one_fresh_session_attempt(daemon: ContractDaemon) -> None:
    """A context_overflow on a replay-safe attempt triggers one fresh_session attempt."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "prompt": "E2E_MODE=fail_once_overflow E2E_KEY=overflow-1",
            },
        )
        job_id = submitted["job"]["id"]
        waited = await wait_for_job(session, job_id, timeout_s=15)
        assert waited["job"]["state"] == "succeeded"

    rows = daemon.query_db(
        "SELECT seq, reason, state FROM attempts WHERE job_id = ? ORDER BY seq",
        (job_id,),
    )
    assert [(r["seq"], r["reason"], r["state"]) for r in rows] == [
        (1, "initial", "failed"),
        (2, "fresh_session", "succeeded"),
    ]


@pytest.mark.asyncio
async def test_transient_failure_falls_back_to_next_target(daemon: ContractDaemon) -> None:
    """When same-target retries are exhausted on a replay-safe attempt, fallback tries the next target."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "profile": "fallback",
                "prompt": "E2E_MODE=fail_once_transient E2E_KEY=fallback-1",
            },
        )
        job_id = submitted["job"]["id"]
        waited = await wait_for_job(session, job_id, timeout_s=15)
        assert waited["job"]["state"] == "succeeded"

    rows = daemon.query_db(
        "SELECT seq, reason, target, state FROM attempts WHERE job_id = ? ORDER BY seq",
        (job_id,),
    )
    assert [(r["seq"], r["reason"], r["target"], r["state"]) for r in rows] == [
        (1, "initial", "claude-secondary", "failed"),
        (2, "fallback", "claude-primary", "succeeded"),
    ]


@pytest.mark.asyncio
async def test_no_automatic_rerun_after_tool_started(daemon: ContractDaemon) -> None:
    """An attempt that emitted tool.started has replay_safe=0 and is never automatically re-run."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "prompt": "E2E_MODE=tool_then_fail_transient",
            },
        )
        job_id = submitted["job"]["id"]
        waited = await wait_for_job(session, job_id, timeout_s=15)
        assert waited["job"]["state"] == "failed"

    rows = daemon.query_db(
        "SELECT seq, reason, replay_safe FROM attempts WHERE job_id = ? ORDER BY seq",
        (job_id,),
    )
    assert [(r["seq"], r["reason"], r["replay_safe"]) for r in rows] == [(1, "initial", 0)]


@pytest.mark.asyncio
async def test_no_automatic_rerun_after_question(daemon: ContractDaemon) -> None:
    """An attempt that asked a question has replay_safe=0 and is never automatically re-run."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "prompt": "E2E_MODE=ask_then_fail_transient E2E_ASK: Proceed?",
            },
        )
        job_id = submitted["job"]["id"]

        # Await the worker question through wait(), then verify it is persisted and answer it.
        await wait_for_job(session, job_id, timeout_s=10)
        qrows = daemon.query_db("SELECT state FROM questions WHERE job_id = ?", (job_id,))
        assert [r["state"] for r in qrows] == ["open"]
        await call_tool_json(session, "answer", {"job_id": job_id, "answer": "yes"})

        waited = await wait_for_job(session, job_id, timeout_s=15)
        assert waited["job"]["state"] == "failed"

    rows = daemon.query_db(
        "SELECT seq, reason, replay_safe FROM attempts WHERE job_id = ? ORDER BY seq",
        (job_id,),
    )
    assert [(r["seq"], r["reason"], r["replay_safe"]) for r in rows] == [(1, "initial", 0)]


@pytest.mark.asyncio
async def test_no_automatic_rerun_on_non_streaming_target(daemon: ContractDaemon) -> None:
    """A non-streaming target has replay_safe=0 and is never automatically re-run."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "profile": "nonstream",
                "prompt": "E2E_MODE=fail_once_transient E2E_KEY=nonstream-1",
            },
        )
        job_id = submitted["job"]["id"]
        waited = await wait_for_job(session, job_id, timeout_s=15)
        assert waited["job"]["state"] == "failed"

    rows = daemon.query_db(
        "SELECT seq, reason, target, replay_safe FROM attempts WHERE job_id = ? ORDER BY seq",
        (job_id,),
    )
    assert [(r["seq"], r["reason"], r["target"], r["replay_safe"]) for r in rows] == [
        (1, "initial", "agy-nonstream", 0)
    ]
