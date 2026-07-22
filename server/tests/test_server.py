from __future__ import annotations

import pytest

from openmcp.models import JobView
from openmcp.server import mcp


@pytest.mark.asyncio
async def test_mcp_exposes_direct_job_contract() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert "job_integrate" not in tools
    assert set(tools["job_submit"].inputSchema["properties"]) == {"project_id", "workflow", "prompt", "commit_message", "context_key", "profile"}
    assert set(tools["job_wait"].inputSchema["properties"]) == {"job_id", "timeout_s"}
    assert set(tools["job_retry"].inputSchema["properties"]) == {"job_id"}
    assert {"stages", "parent_job_id", "branch", "integration_base", "artifacts"}.isdisjoint(JobView.model_fields)
