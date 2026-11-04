import json
from pathlib import Path

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from refract.drivers import DriverResult
from refract.models import FAILURE_KINDS
from refract.server import _raw_argument_error, create_mcp
from tests.orchestration_helpers import FakeDrivers, repository
from tests.test_server import _connected_client


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


TOOL_SCHEMAS = {
    "submit": ({"path", "workflow", "prompt", "profile", "session", "fresh"}, {"path", "workflow", "prompt"}),
    "wait": ({"job_id", "timeout_s"}, {"job_id"}),
    "answer": ({"job_id", "answer"}, {"job_id", "answer"}),
    "cancel": ({"job_id"}, {"job_id"}),
    "retry": ({"job_id", "target"}, {"job_id"}),
    "list": ({"path"}, {"path"}),
}
JOB_KEYS = {"id", "project", "workflow", "profile", "target", "session", "state", "retry_of", "created_at", "updated_at"}
RESULT_KEYS = {"text", "truncated", "result_path", "pending_question", "failure_kind", "next_target", "model", "duration_ms", "tokens"}
TOKEN_KEYS = {"context_used", "context_window", "input", "output", "cache_read", "cache_write"}
ERROR_KEYS = {"code", "message", "next_action", "retry_after_s"}
REMOVED_KEYS = {
    "project_id", "context_key", "fresh_session", "next_offset", "result_offset", "retryable",
    "source", "quality", "observed_at", "metadata", "next_target_token",
}


def _keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value))
    return set()


async def _call(client, name: str, arguments: dict) -> dict:
    response = await client.call_tool(name, arguments)
    payload = json.loads(response.content[0].text)
    assert not (_keys(payload) & REMOVED_KEYS), name
    if response.is_error:
        assert set(payload) <= ERROR_KEYS and {"code", "message", "next_action"} <= set(payload)
        return {"error": payload}
    return payload


class TextDrivers(FakeDrivers):
    def __init__(self, text: str = "done", outcome: str = "SUCCESS") -> None:
        super().__init__()
        self.text = text
        self.outcome = outcome

    async def execute(self, **kwargs) -> DriverResult:
        if self.outcome != "SUCCESS":
            return DriverResult(self.outcome, "", "", "backend said no", "backend_failure")
        return DriverResult("SUCCESS", "session-1", self.text, "", "", model="model-1")


@pytest.mark.asyncio
async def test_mcp_surface_is_exactly_six_tools_with_exact_input_schemas():
    server = create_mcp()
    tools = {tool.name: tool for tool in await server.list_tools()}
    assert set(tools) == set(TOOL_SCHEMAS)
    for name, (properties, required) in TOOL_SCHEMAS.items():
        schema = tools[name].input_schema
        assert set(schema["properties"]) == properties, name
        assert set(schema.get("required", [])) == required, name
        assert _raw_argument_error(schema, {**{key: "x" for key in required}, "unknown": 1}), name
    assert tools["submit"].input_schema["properties"]["fresh"]["default"] is False
    assert tools["wait"].input_schema["properties"]["timeout_s"]["default"] == 3600
    assert tools["answer"].input_schema["properties"]["answer"]["maxLength"] == 8192


def test_failure_kinds_match_design():
    assert set(FAILURE_KINDS) == {
        "cancelled", "circuit_open", "replay_blocked", "context_overflow", "request_fatal", "target_fatal", "transient",
    }


@pytest.mark.asyncio
async def test_list_submit_wait_from_subdirectory_returns_exact_v3_fields(tmp_path, monkeypatch):
    root = repository(tmp_path)
    subdirectory = root / "pkg"
    subdirectory.mkdir()
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        runtime.drivers = TextDrivers()
        listed = await _call(client, "list", {"path": str(subdirectory)})
        assert set(listed) == {"active", "recent", "workflows", "profiles", "guidance"}
        assert listed["active"] == [] and listed["recent"] == []
        submitted = await _call(client, "submit", {"path": str(subdirectory), "workflow": "consult", "prompt": "hello"})
        assert set(submitted) == {"job"}
        job = submitted["job"]
        assert set(job) == JOB_KEYS
        assert job["project"] == root.resolve().as_posix()
        assert job["retry_of"] in {"", None}
        waited = await _call(client, "wait", {"job_id": job["id"], "timeout_s": 10})
        assert set(waited) == {"job", "result"}
        assert set(waited["job"]) == JOB_KEYS and waited["job"]["state"] == "succeeded"
        assert waited["job"]["target"] == "primary"
        result = waited["result"]
        assert set(result) == RESULT_KEYS and set(result["tokens"]) == TOKEN_KEYS
        assert result["text"] == "done" and result["truncated"] is False
        assert result["failure_kind"] is None and result["pending_question"] is None
        assert result["model"] == "model-1"
        assert Path(result["result_path"]).read_text(encoding="utf-8") == "done"
        relisted = await _call(client, "list", {"path": str(root)})
        assert [item["id"] for item in relisted["recent"]] == [job["id"]]
        assert set(relisted["recent"][0]) == JOB_KEYS


@pytest.mark.asyncio
async def test_submit_outside_git_is_invalid_path(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    async with _connected_client(tmp_path, monkeypatch) as (client, _runtime):
        submitted = await _call(client, "submit", {"path": str(plain), "workflow": "consult", "prompt": "hello"})
        assert submitted["error"]["code"] == "invalid_path"
        listed = await _call(client, "list", {"path": str(plain)})
        assert listed["error"]["code"] == "invalid_path"


@pytest.mark.asyncio
async def test_long_result_is_truncated_with_full_text_at_result_path(tmp_path, monkeypatch):
    root = repository(tmp_path)
    full = "x" * 100_000
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        runtime.drivers = TextDrivers(full)
        job = (await _call(client, "submit", {"path": str(root), "workflow": "consult", "prompt": "long"}))["job"]
        result = (await _call(client, "wait", {"job_id": job["id"], "timeout_s": 10}))["result"]
        assert result["truncated"] is True
        assert 0 < len(result["text"]) < len(full) and full.startswith(result["text"])
        assert Path(result["result_path"]).read_text(encoding="utf-8") == full


@pytest.mark.asyncio
async def test_failed_job_reports_transient_kind_and_retry_returns_new_job(tmp_path, monkeypatch):
    root = repository(tmp_path)
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        runtime.drivers = TextDrivers(outcome="RETRYABLE")
        source = (await _call(client, "submit", {"path": str(root), "workflow": "consult", "prompt": "fail"}))["job"]
        failed = await _call(client, "wait", {"job_id": source["id"], "timeout_s": 10})
        assert failed["job"]["state"] == "failed"
        assert failed["result"]["failure_kind"] == "transient"
        assert failed["result"]["next_target"] is None
        runtime.drivers = TextDrivers()
        retried = await _call(client, "retry", {"job_id": source["id"], "target": "primary"})
        assert set(retried) == {"job"} and set(retried["job"]) == JOB_KEYS
        assert retried["job"]["id"] != source["id"] and retried["job"]["retry_of"] == source["id"]
        done = await _call(client, "wait", {"job_id": retried["job"]["id"], "timeout_s": 10})
        assert done["job"]["state"] == "succeeded"
        unknown = await _call(client, "retry", {"job_id": source["id"], "target": "missing"})
        assert unknown["error"]["code"] == "invalid_request" and "primary" in unknown["error"]["message"]


@pytest.mark.asyncio
async def test_cancel_and_answer_return_job_or_compact_error(tmp_path, monkeypatch):
    root = repository(tmp_path)
    async with _connected_client(tmp_path, monkeypatch) as (client, runtime):
        runtime.drivers = TextDrivers()
        job = (await _call(client, "submit", {"path": str(root), "workflow": "consult", "prompt": "hi"}))["job"]
        await _call(client, "wait", {"job_id": job["id"], "timeout_s": 10})
        cancelled = await _call(client, "cancel", {"job_id": job["id"]})
        assert set(cancelled) == {"job"} and set(cancelled["job"]) == JOB_KEYS
        answered = await _call(client, "answer", {"job_id": job["id"], "answer": "yes"})
        assert answered["error"]["code"] == "invalid_state"
        missing = await _call(client, "wait", {"job_id": "missing", "timeout_s": 0})
        assert missing["error"]["code"] == "unknown_job"
