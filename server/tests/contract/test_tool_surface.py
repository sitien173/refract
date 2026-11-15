"""Contract tests for the MCP tool surface and annotations."""

from __future__ import annotations

import pytest

from tests.contract.conftest import ContractDaemon, call_tool_json

EXPECTED_TOOLS = frozenset(
    {
        "submit",
        "get",
        "wait",
        "cancel",
        "answer",
        "list",
        "card_create",
        "card_move",
        "card_list",
    }
)


@pytest.mark.asyncio
async def test_mcp_exposes_exact_nine_tools_and_annotations(daemon: ContractDaemon) -> None:
    """MCP exposes exactly the 9 redesigned tools and card_move is non-destructive."""
    async with daemon.mcp_session() as session:
        listing = await session.list_tools()
        tools = {tool.name: tool for tool in listing.tools}
        assert set(tools) == EXPECTED_TOOLS
        assert "retry" not in tools

        card_move = tools["card_move"]
        destructive = card_move.annotations.destructive_hint if card_move.annotations else None
        assert destructive in (False, None)


@pytest.mark.asyncio
async def test_card_create_and_move_preserve_behavior(daemon: ContractDaemon) -> None:
    """card_create and card_move preserve existing card creation and transition behavior."""
    async with daemon.mcp_session() as session:
        created = await call_tool_json(
            session,
            "card_create",
            {"path": str(daemon.repo), "title": "Contract card", "body": "Details"},
        )
        card_id = created["card"]["id"]
        assert created["card"]["state"] == "todo"

        moved = await call_tool_json(
            session,
            "card_move",
            {"card_id": card_id, "state": "in_progress", "note": "Starting"},
        )
        assert moved["moved"] is True
        assert moved["card"]["state"] == "in_progress"
