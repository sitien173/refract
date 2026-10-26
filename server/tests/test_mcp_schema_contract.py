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


@pytest.mark.asyncio
async def test_job_answer_schema_contract():
    server = create_mcp()
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert "job_answer" in tools
    job_answer_tool = tools["job_answer"]
    schema = job_answer_tool.input_schema
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"job_id", "answer"}
    properties = schema["properties"]
    assert properties["job_id"]["type"] == "string"
    assert properties["job_id"]["minLength"] == 1
    assert properties["answer"]["type"] == "string"
    assert properties["answer"]["minLength"] == 1
    assert properties["answer"]["maxLength"] == 8192
    assert not _raw_argument_error(schema, {"job_id": "job-1", "answer": "ok"})
    assert _raw_argument_error(schema, {"job_id": "job-1", "answer": 123})
    assert _raw_argument_error(schema, {"job_id": "job-1", "answer": "ok", "extra": 1})


@pytest.mark.asyncio
async def test_job_wait_schema_contract():
    server = create_mcp()
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert "job_wait" in tools
    job_wait_tool = tools["job_wait"]
    schema = job_wait_tool.input_schema
    assert schema["type"] == "object"
    assert "job_id" in schema["required"]
    properties = schema["properties"]
    assert properties["job_id"]["type"] == "string"
    assert properties["timeout_s"]["type"] == "integer"
    assert properties["result_offset"]["type"] == "integer"
    assert not _raw_argument_error(schema, {"job_id": "job-1", "timeout_s": 0, "result_offset": 0})
    assert _raw_argument_error(schema, {"job_id": "job-1", "timeout_s": "not-an-int"})
    assert _raw_argument_error(schema, {"job_id": "job-1", "extra": 1})


