import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from refract.server import _raw_argument_error, create_mcp


@pytest.mark.asyncio
async def test_argument_guard_uses_registered_input_schema():
    server = create_mcp()

    @server.tool()
    async def new_tool(new_argument: str, enabled: bool = False) -> str:
        return new_argument

    tool = next(tool for tool in await server.list_tools() if tool.name == "new_tool")
    assert not _raw_argument_error(tool.input_schema, {"new_argument": "value", "enabled": True})
    assert _raw_argument_error(tool.input_schema, {"new_argument": "value", "unknown": 1})
    assert _raw_argument_error(tool.input_schema, {"new_argument": 1})
    assert _raw_argument_error(tool.input_schema, {"new_argument": "value", "enabled": 1})


@pytest.mark.asyncio
async def test_pinned_sdk_tool_error_prefix():
    server = MCPServer("prefix-contract")

    @server.tool()
    async def rejected() -> str:
        raise ToolError("contract failure")

    with pytest.raises(ToolError) as error:
        await server.call_tool("rejected", {})
    assert str(error.value) == "Error executing tool rejected: contract failure"
