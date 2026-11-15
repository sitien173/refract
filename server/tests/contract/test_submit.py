"""Contract tests for submit, from_job, and get."""

from __future__ import annotations

import pytest

from tests.contract.conftest import ContractDaemon, call_tool_json, wait_for_file, wait_for_job


@pytest.mark.asyncio
async def test_submit_and_wait_succeeds(daemon: ContractDaemon) -> None:
    """Submitting a job and waiting on it reaches succeeded with output."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "prompt": "Hello contract harness",
            },
        )
        job_id = submitted["job"]["id"]
        assert submitted["job"]["state"] in {"queued", "running"}

        waited = await wait_for_job(session, job_id, timeout_s=15)
        assert waited["job"]["id"] == job_id
        assert waited["job"]["state"] == "succeeded"


@pytest.mark.asyncio
async def test_submit_from_job_copies_fields_and_picks_next_target(daemon: ContractDaemon) -> None:
    """submit(from_job) copies workflow, profile, session, prompt and picks the next target."""
    async with daemon.mcp_session() as session:
        first = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "profile": "contract",
                "session": "copy-session",
                "prompt": "Initial prompt",
            },
        )
        first_id = first["job"]["id"]
        await call_tool_json(session, "wait", {"job_ids": [first_id], "timeout_s": 15})

        second = await call_tool_json(
            session,
            "submit",
            {"path": str(daemon.repo), "from_job": first_id},
        )
        second_id = second["job"]["id"]
        waited = await call_tool_json(session, "wait", {"job_ids": [second_id], "timeout_s": 15})
        assert waited["job"]["workflow"] == "consult"
        assert waited["job"]["profile"] == "contract"
        assert waited["job"]["session"] == "copy-session"
        assert waited["job"]["target_id"] == "claude-secondary"


@pytest.mark.asyncio
async def test_submit_from_job_and_prompt_mutually_exclusive(daemon: ContractDaemon) -> None:
    """submit with both from_job and prompt returns invalid_request."""
    async with daemon.mcp_session() as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
        assert "from_job" in tools["submit"].input_schema.get("properties", {})
        resp = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "prompt": "Both set",
                "from_job": "some-job",
            },
        )
        assert resp["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_submit_from_job_non_terminal_returns_invalid_state(daemon: ContractDaemon) -> None:
    """submit(from_job) on a running job returns invalid_state."""
    ready_file = daemon.ready_file("from_job.ready")
    async with daemon.mcp_session() as session:
        first = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "prompt": "E2E_MODE=block E2E_READY_NAME=from_job.ready",
            },
        )
        first_id = first["job"]["id"]
        wait_for_file(ready_file)

        resp = await call_tool_json(
            session,
            "submit",
            {"path": str(daemon.repo), "from_job": first_id},
        )
        assert resp["code"] == "invalid_state"
        await call_tool_json(session, "cancel", {"job_id": first_id})


@pytest.mark.asyncio
async def test_submit_from_job_no_next_target_returns_targets_unavailable(daemon: ContractDaemon) -> None:
    """submit(from_job) on a single-target profile without explicit target returns targets_unavailable."""
    async with daemon.mcp_session() as session:
        first = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "profile": "codex",
                "prompt": "E2E_MODE=codex",
            },
        )
        first_id = first["job"]["id"]
        await call_tool_json(session, "wait", {"job_ids": [first_id], "timeout_s": 15})

        resp = await call_tool_json(
            session,
            "submit",
            {"path": str(daemon.repo), "from_job": first_id},
        )
        assert resp["code"] == "targets_unavailable"


@pytest.mark.asyncio
async def test_get_returns_job_attempts_and_result(daemon: ContractDaemon) -> None:
    """get(job_id) is read-only and returns job, attempts, and result."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {"path": str(daemon.repo), "workflow": "consult", "prompt": "Check get"},
        )
        job_id = submitted["job"]["id"]
        await call_tool_json(session, "wait", {"job_ids": [job_id], "timeout_s": 15})

        got = await call_tool_json(session, "get", {"job_id": job_id})
        assert got["job"]["id"] == job_id
        assert got["job"]["state"] == "succeeded"
        assert len(got["attempts"]) == 1
        assert "E2E backend completed" in got["result"]
