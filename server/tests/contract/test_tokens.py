"""Contract tests for codex token accounting and per-attempt tokens."""

from __future__ import annotations

import pytest

from tests.contract.conftest import ContractDaemon, call_tool_json, wait_for_job


@pytest.mark.asyncio
async def test_codex_context_used_falls_back_to_input_plus_output(daemon: ContractDaemon) -> None:
    """Codex reports no context window, so context_used is input plus output and the window stays null."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "profile": "codex",
                "prompt": "E2E_MODE=codex",
            },
        )
        job_id = submitted["job"]["id"]
        waited = await wait_for_job(session, job_id, timeout_s=15)
        assert waited["job"]["state"] == "succeeded"

    rows = daemon.query_db(
        "SELECT tok_context_used, tok_context_window, tok_input, tok_output FROM attempts WHERE job_id = ?",
        (job_id,),
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["tok_input"] is not None
    assert row["tok_context_used"] == row["tok_input"] + row["tok_output"]
    assert row["tok_context_window"] is None

    detail = await daemon.async_http_request("GET", f"/dashboard/api/jobs/{job_id}")
    assert detail.status == 200
    job_data = detail.json()
    tokens = job_data.get("result", {}).get("tokens") or job_data.get("tokens") or {}
    context_used = tokens.get("context_used")
    assert context_used is not None, f"Missing context_used in job detail: {job_data}"
    assert context_used == row["tok_context_used"]


@pytest.mark.asyncio
async def test_codex_per_attempt_tokens_cover_only_that_attempt(daemon: ContractDaemon) -> None:
    """Each attempt row records only that attempt's tokens, not cumulative totals across attempts."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "profile": "codex-retry",
                "prompt": "E2E_MODE=codex_fail_once_transient E2E_KEY=codex-retry-1",
            },
        )
        job_id = submitted["job"]["id"]
        waited = await wait_for_job(session, job_id, timeout_s=15)
        assert waited["job"]["state"] == "succeeded"

    rows = daemon.query_db(
        "SELECT seq, state, tok_input, tok_output FROM attempts WHERE job_id = ? ORDER BY seq",
        (job_id,),
    )
    assert [(r["seq"], r["state"], r["tok_input"], r["tok_output"]) for r in rows] == [
        (1, "failed", 1111, 22),
        (2, "succeeded", 5555, 66),
    ]
