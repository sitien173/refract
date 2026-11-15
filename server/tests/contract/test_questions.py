"""Contract tests for persisted questions, concurrent answers, and restart expiry."""

from __future__ import annotations

import asyncio

import pytest

from tests.contract.conftest import ContractDaemon, call_tool_json, wait_for_job


@pytest.mark.asyncio
async def test_question_persisted_and_concurrent_answer_has_one_winner(
    daemon: ContractDaemon,
) -> None:
    """Concurrent answer calls let one win via compare-and-set and reject the other with invalid_state."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "prompt": "E2E_MODE=ask E2E_ASK: Choose option",
            },
        )
        job_id = submitted["job"]["id"]
        await wait_for_job(session, job_id, timeout_s=10)
        qrows = daemon.query_db("SELECT state FROM questions WHERE job_id = ?", (job_id,))
        assert [r["state"] for r in qrows] == ["open"]

        res1, res2 = await asyncio.gather(
            call_tool_json(session, "answer", {"job_id": job_id, "answer": "option-1"}),
            call_tool_json(session, "answer", {"job_id": job_id, "answer": "option-2"}),
        )
        codes = [r.get("code") for r in (res1, res2)]
        assert codes.count(None) == 1
        assert codes.count("invalid_state") == 1

        waited = await wait_for_job(session, job_id, timeout_s=15)
        assert waited["job"]["state"] == "succeeded"

    rows = daemon.query_db("SELECT state, answer FROM questions WHERE job_id = ?", (job_id,))
    assert len(rows) == 1
    assert rows[0]["state"] == "answered"
    assert rows[0]["answer"] in {"option-1", "option-2"}


@pytest.mark.asyncio
async def test_open_question_expires_on_restart(daemon: ContractDaemon) -> None:
    """An open question transitions to expired and its job to interrupted on daemon restart."""
    async with daemon.mcp_session() as session:
        submitted = await call_tool_json(
            session,
            "submit",
            {
                "path": str(daemon.repo),
                "workflow": "consult",
                "prompt": "E2E_MODE=ask E2E_ASK: Will I expire?",
            },
        )
        job_id = submitted["job"]["id"]
        await wait_for_job(session, job_id, timeout_s=10)
        qrows = daemon.query_db("SELECT state FROM questions WHERE job_id = ?", (job_id,))
        assert [r["state"] for r in qrows] == ["open"]

    daemon.restart(kill=True)

    qrows = daemon.query_db("SELECT state FROM questions WHERE job_id = ?", (job_id,))
    assert [r["state"] for r in qrows] == ["expired"]
    jrows = daemon.query_db("SELECT state FROM jobs WHERE id = ?", (job_id,))
    assert [r["state"] for r in jrows] == ["interrupted"]
