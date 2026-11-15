"""Contract tests for declared error codes across MCP and HTTP."""

from __future__ import annotations

import typing

import pytest

from refract import models
from tests.contract.conftest import ContractDaemon, call_tool_json


def _declared_error_codes() -> set[str]:
    error_codes = getattr(models, "ERROR_CODES", None)
    assert error_codes is not None, "models.ERROR_CODES must be declared as a Literal"
    return set(typing.get_args(error_codes))


@pytest.mark.asyncio
async def test_mcp_emits_only_declared_error_codes(daemon: ContractDaemon) -> None:
    """Malformed or failing MCP calls emit only error codes declared in refract.models."""
    declared = _declared_error_codes()
    async with daemon.mcp_session() as session:
        unknown_wait = await call_tool_json(
            session, "wait", {"job_ids": ["nonexistent"], "timeout_s": 1}
        )
        assert unknown_wait["code"] in declared

        bad_wait = await call_tool_json(session, "wait", {"job_ids": [], "timeout_s": 1})
        assert bad_wait["code"] == "invalid_request"
        assert bad_wait["code"] in declared

        bad_submit = await call_tool_json(
            session,
            "submit",
            {"path": str(daemon.repo), "workflow": "consult", "prompt": "x", "from_job": "y"},
        )
        assert bad_submit["code"] == "invalid_request"
        assert bad_submit["code"] in declared


@pytest.mark.asyncio
async def test_http_emits_only_declared_error_codes_and_no_bad_request(
    daemon: ContractDaemon,
) -> None:
    """HTTP error responses use declared codes and never emit bad_request."""
    declared = _declared_error_codes()
    bad_ask = await daemon.async_http_request(
        "POST",
        "/ask",
        body="{not json",
        headers={"Content-Type": "application/json"},
    )
    assert bad_ask.status == 400
    ask_payload = bad_ask.json()
    assert ask_payload["code"] != "bad_request"
    assert ask_payload["code"] == "invalid_request"
    assert ask_payload["code"] in declared

    missing_job = await daemon.async_http_request("GET", "/dashboard/api/jobs/does-not-exist")
    assert missing_job.status == 404
    assert missing_job.json()["code"] in declared
