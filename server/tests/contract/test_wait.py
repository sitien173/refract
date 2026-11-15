"""Contract tests for wait semantics, truncation, multi-ID wait, and restart mid-wait."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.contract.conftest import ContractDaemon, call_tool_json, wait_for_file, wait_for_job


@pytest.mark.asyncio
async def test_wait_long_result_truncates_with_result_path(daemon: ContractDaemon) -> None:
    """A >=100 KB result is truncated in wait with truncated=true and a readable result_path."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {"path": str(daemon.repo), "workflow": "consult", "prompt": "E2E_MODE=long"},
        )
        job_id = submitted["job"]["id"]
        waited = await call_tool_json(session, "wait", {"job_ids": [job_id], "timeout_s": 15})
        assert waited.get("code") != "response_too_large"
        assert waited["job"]["state"] == "succeeded"
        assert waited["truncated"] is True
        result_path = Path(waited["result_path"])
        assert result_path.exists()
        assert len(result_path.read_text(encoding="utf-8")) >= 100 * 1024


@pytest.mark.asyncio
async def test_wait_multi_job_ids_returns_first_ready(daemon: ContractDaemon) -> None:
    """wait(job_ids) returns as soon as any listed job reaches a terminal state."""
    ready_file = daemon.ready_file("block.ready")
    async with daemon.mcp_session() as session:
        slow = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "session": "slow-session",
                "prompt": "E2E_MODE=block E2E_READY_NAME=block.ready",
            },
        )
        slow_id = slow["job"]["id"]
        wait_for_file(ready_file)

        fast = await call_tool_json(
            session,
            "submit",
            {"path": str(daemon.repo), "workflow": "consult", "session": "fast-session", "prompt": "Fast job"},
        )
        fast_id = fast["job"]["id"]

        waited = await call_tool_json(
            session,
            "wait",
            {"job_ids": [slow_id, fast_id], "timeout_s": 15},
        )
        assert waited["job"]["id"] == fast_id
        assert waited["job"]["state"] == "succeeded"

        await call_tool_json(session, "cancel", {"job_id": slow_id})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "job_ids",
    [
        [],
        [f"job-{i}" for i in range(17)],
        ["dup-1", "dup-1"],
    ],
    ids=["empty", "over_16", "duplicate"],
)
async def test_wait_invalid_job_ids_returns_invalid_request(
    daemon: ContractDaemon, job_ids: list[str]
) -> None:
    """wait rejects empty, >16, or duplicate job_ids with invalid_request."""
    async with daemon.mcp_session() as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
        assert "job_ids" in tools["wait"].input_schema.get("properties", {})
        resp = await call_tool_json(session, "wait", {"job_ids": job_ids, "timeout_s": 1})
        assert resp["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_wait_unknown_job_returns_unknown_job_immediately(daemon: ContractDaemon) -> None:
    """wait with an unknown job ID returns unknown_job without blocking."""
    async with daemon.mcp_session() as session:
        resp = await call_tool_json(session, "wait", {"job_ids": ["missing-job-id"], "timeout_s": 10})
        assert resp["code"] == "unknown_job"


@pytest.mark.asyncio
async def test_wait_after_restart_mid_job_sees_interrupted(daemon: ContractDaemon) -> None:
    """A job running across a daemon restart becomes interrupted and wait observes it."""
    ready_file = daemon.ready_file("restart.ready")
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "prompt": "E2E_MODE=block E2E_READY_NAME=restart.ready",
            },
        )
        job_id = submitted["job"]["id"]
        wait_for_file(ready_file)

    daemon.restart(kill=True)

    async with daemon.mcp_session() as session:
        waited = await wait_for_job(session, job_id, timeout_s=5)
        assert waited["job"]["state"] == "interrupted"
