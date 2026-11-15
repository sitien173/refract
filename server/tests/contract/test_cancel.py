"""Contract tests for cancel_status and terminal compare-and-set."""

from __future__ import annotations

import pytest

from tests.contract.conftest import ContractDaemon, call_tool_json, wait_for_file


@pytest.mark.asyncio
async def test_cancel_queued_returns_terminated(daemon: ContractDaemon) -> None:
    """Cancelling a queued job transitions it immediately and returns cancel_status=terminated."""
    ready_file = daemon.ready_file("queue_head.ready")
    async with daemon.mcp_session() as session:
        head = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "session": "serial-session",
                "prompt": "E2E_MODE=block E2E_READY_NAME=queue_head.ready",
            },
        )
        head_id = head["job"]["id"]
        wait_for_file(ready_file)

        queued = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "session": "serial-session",
                "prompt": "Should stay queued",
            },
        )
        queued_id = queued["job"]["id"]

        cancelled = await call_tool_json(session, "cancel", {"job_id": queued_id})
        assert cancelled["cancel_status"] == "terminated"
        assert cancelled["job"]["state"] == "cancelled"

        await call_tool_json(session, "cancel", {"job_id": head_id})


@pytest.mark.asyncio
async def test_cancel_running_returns_requested(daemon: ContractDaemon) -> None:
    """Cancelling a running job requests termination and returns cancel_status=requested."""
    ready_file = daemon.ready_file("cancel_run.ready")
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "prompt": "E2E_MODE=block E2E_READY_NAME=cancel_run.ready",
            },
        )
        job_id = submitted["job"]["id"]
        wait_for_file(ready_file)

        cancelled = await call_tool_json(session, "cancel", {"job_id": job_id})
        assert cancelled["cancel_status"] == "requested"


@pytest.mark.asyncio
async def test_cancel_terminal_returns_already_terminal_and_never_overwrites(
    daemon: ContractDaemon,
) -> None:
    """Cancelling a succeeded job returns already_terminal and leaves state as succeeded."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {"path": str(daemon.repo), "workflow": "consult", "prompt": "Finish fast"},
        )
        job_id = submitted["job"]["id"]
        await call_tool_json(session, "wait", {"job_ids": [job_id], "timeout_s": 15})

        cancelled = await call_tool_json(session, "cancel", {"job_id": job_id})
        assert cancelled["cancel_status"] == "already_terminal"
        assert cancelled["job"]["state"] == "succeeded"
