"""Characterization fixtures and streaming normalization tests for backends."""

from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Any
from unittest.mock import MagicMock

import pytest

from refract.backends import classify_tool_activity
from refract.backends import BackendParams
from refract.backends.agy import execute, execute as agy_sync
from refract.backends.claude import execute as claude_sync
from refract.backends.codex import execute as codex_sync
from refract.backends.pi import execute as pi_sync


# --- Fixture Payloads ---

CLAUDE_STREAM_JSON_FIXTURE = [
    # System / prompt echo events (must be ignored)
    json.dumps({"type": "system", "content": "system prompt secret_token_123"}),
    # Assistant text delta wrapped in stream_event envelope
    json.dumps({
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "Analyzing the code..."},
            "index": 0,
        },
    }),
    # Thinking block (must be ignored, including planted secret)
    json.dumps({
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "delta": {"type": "thinking_delta", "thinking": "secret_reasoning_456"},
            "index": 1,
        },
    }),
    # Tool use start event (safe lifecycle only; arguments must NOT leak)
    json.dumps({
        "type": "stream_event",
        "event": {
            "type": "content_block_start",
            "content_block": {
                "type": "tool_use",
                "id": "toolu_01",
                "name": "Read",
                "input": {"path": "/etc/shadow", "secret_arg": "pass123"},
            },
        },
    }),
    # Tool result / finish event (result data must NOT leak)
    json.dumps({
        "type": "stream_event",
        "event": {
            "type": "content_block_stop",
            "index": 2,
        },
    }),
    # Another assistant text delta
    json.dumps({
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": " Found 0 bugs."},
            "index": 3,
        },
    }),
    # Final result event (authoritative final result & session)
    json.dumps({
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Final Claude Answer",
        "session_id": "claude-sess-999",
    }),
]

CODEX_JSONL_FIXTURE = [
    # Thread started
    json.dumps({"type": "thread.started", "thread_id": "codex-thread-1234-5678"}),
    # Item started: agent message
    json.dumps({
        "type": "item.started",
        "item": {"type": "agent_message", "id": "item_msg_1"},
    }),
    # Item completed: agent message with text
    json.dumps({
        "type": "item.completed",
        "item": {"type": "agent_message", "id": "item_msg_1", "text": "Inspecting repository structure."},
    }),
    # Tool call started with sensitive command / arguments (must NOT leak)
    json.dumps({
        "type": "item.started",
        "item": {
            "type": "tool_call",
            "id": "tool_call_1",
            "name": "bash",
            "input": "cat /etc/passwd secret_key_789",
        },
    }),
    # Tool call completed (output must NOT leak)
    json.dumps({
        "type": "item.completed",
        "item": {
            "type": "tool_call",
            "id": "tool_call_1",
            "name": "bash",
            "output": "root:secret_hash_value",
            "status": "completed",
        },
    }),
    # Reasoning item (must be ignored)
    json.dumps({
        "type": "item.completed",
        "item": {"type": "reasoning", "text": "secret_chain_of_thought"},
    }),
]

PI_JSON_FIXTURE = [
    # Session event
    json.dumps({"type": "session", "id": "pi-sess-abc-123"}),
    # Thinking delta (must be ignored, type is not text_delta)
    json.dumps({
        "type": "message_update",
        "assistantMessageEvent": {
            "type": "thinking_delta",
            "delta": "secret_thinking_pwd",
        },
    }),
    # Text delta wrapped in message_update.assistantMessageEvent
    json.dumps({
        "type": "message_update",
        "assistantMessageEvent": {
            "type": "text_delta",
            "delta": "Checking project files.",
        },
    }),
    # Tool execution start with real camelCase toolCallId and toolName (secret args must NOT leak)
    json.dumps({
        "type": "tool_execution_start",
        "toolCallId": "pi_tool_1",
        "toolName": "grep",
        "args": {"pattern": "secret_pwd_999"},
    }),
    # Tool execution end with real camelCase toolCallId and isError (secret output must NOT leak)
    json.dumps({
        "type": "tool_execution_end",
        "toolCallId": "pi_tool_1",
        "isError": False,
        "result": "matched secret_pwd_999 in config",
    }),
    # Final message_end event
    json.dumps({
        "type": "message_end",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Final Pi Answer"}],
        },
    }),
]

AGY_STREAM_JSON_FIXTURE = [
    # Session / conversation created
    "Created conversation 12345678-1234-1234-1234-123456789abc",
    # Diagnostic non-JSON output (must be ignored once structured JSON is detected)
    "[diagnostic] secret_diagnostic_marker and server trace",
    # Text delta
    json.dumps({
        "type": "assistant.text.delta",
        "text": "Running antigravity analysis.",
    }),
    # Tool event with secret args/results (must NOT leak)
    json.dumps({
        "type": "tool.started",
        "tool_name": "execute_code",
        "arguments": {"script": "secret_token_val"},
    }),
    json.dumps({
        "type": "tool.completed",
        "tool_name": "execute_code",
        "status": "success",
        "output": "secret_stdout_result",
    }),
    # Object payload event (must NOT be str() converted into agent_messages)
    json.dumps({
        "type": "result",
        "result": {"arbitrary_secret_obj": "secret_object_val"},
    }),
    # Final explicit string-valued assistant message
    json.dumps({
        "type": "assistant.message",
        "text": "Antigravity finished successfully.",
    }),
]


# --- Tests ---

def test_claude_streaming_normalization(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    events: list[dict[str, Any]] = []

    def emitter(event: dict[str, Any]) -> None:
        events.append(event)

    monkeypatch.setattr(
        "refract.backends.claude.run_shell_command",
        lambda *args, **kwargs: (line for line in CLAUDE_STREAM_JSON_FIXTURE),
    )

    params = BackendParams(
        PROMPT="inspect",
        cd=workspace,
        emitter=emitter,
    )
    result = claude_sync(params)

    assert result.outcome == "OK"
    assert result.agent_messages == "Final Claude Answer"
    assert result.SESSION_ID == "claude-sess-999"

    # Verify emitted events
    assert len(events) >= 2
    kinds = [e["kind"] for e in events]
    assert "assistant.text.delta" in kinds
    assert "tool.started" in kinds
    assert "tool.completed" in kinds

    started_evt = next(e for e in events if e["kind"] == "tool.started")
    assert started_evt["data"]["tool"] == "Read"
    assert started_evt["data"]["activity"] == "tool_call"
    assert started_evt["data"]["input"] == {"path": "/etc/shadow", "secret_arg": "pass123"}

    completed_evt = next(e for e in events if e["kind"] == "tool.completed")
    assert completed_evt["data"] == {"status": "completed"}
    assert "activity" not in completed_evt["data"]
    assert "output" not in completed_evt["data"]

    serialized = json.dumps(events)
    # Planted non-tool secrets must not be in serialized events
    assert "secret_token_123" not in serialized
    assert "secret_reasoning_456" not in serialized
    # Approved tool input is present in serialized events
    assert "secret_arg" in serialized
    assert "pass123" in serialized
    # Tool arguments must not leak into agent_messages
    assert "pass123" not in result.agent_messages
    assert "secret_arg" not in result.agent_messages


def test_claude_streaming_bash_activity_command(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    stream_fixture = [
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_bash",
                    "name": "bash",
                    "input": {"command": "ls -la"},
                },
            },
        }),
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_stop",
                "index": 0,
            },
        }),
        json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Done",
            "session_id": "claude-bash-sess",
        }),
    ]
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.claude.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    result = claude_sync(BackendParams(PROMPT="test", cd=workspace, emitter=events.append))
    assert result.outcome == "OK"
    started_evt = next(e for e in events if e["kind"] == "tool.started")
    assert started_evt["data"]["tool"] == "bash"
    assert started_evt["data"]["activity"] == "command"
    assert started_evt["data"]["input"] == {"command": "ls -la"}
    completed_evt = next(e for e in events if e["kind"] == "tool.completed")
    assert "activity" not in completed_evt["data"]


def test_claude_streaming_nested_and_missing_payloads(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    nested_input = {
        "nested": {"key": [1, 2.5, "three", False, True, None, {"deep": True}]},
        "empty_list": [],
        "empty_dict": {},
        "empty_str": "",
        "zero": 0,
        "false_val": False,
    }

    stream_fixture = [
        # Tool 1: complex nested input
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "content_block": {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "NestedTool",
                    "input": nested_input,
                },
            },
        }),
        json.dumps({
            "type": "stream_event",
            "event": {"type": "content_block_stop", "index": 0},
        }),
        # Tool 2: missing input field
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "content_block": {
                    "type": "tool_use",
                    "id": "t2",
                    "name": "NoInputTool",
                },
            },
        }),
        json.dumps({
            "type": "stream_event",
            "event": {"type": "content_block_stop", "index": 1},
        }),
        # Tool 3: null input
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "content_block": {
                    "type": "tool_use",
                    "id": "t3",
                    "name": "NullInputTool",
                    "input": None,
                },
            },
        }),
        json.dumps({
            "type": "stream_event",
            "event": {"type": "content_block_stop", "index": 2},
        }),
        json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Done",
            "session_id": "claude-sess",
        }),
    ]

    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.claude.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    params = BackendParams(PROMPT="inspect", cd=workspace, emitter=events.append)
    result = claude_sync(params)
    assert result.outcome == "OK"

    tool_starts = [e for e in events if e["kind"] == "tool.started"]
    assert len(tool_starts) == 3

    # Nested structure preserved exactly
    assert tool_starts[0]["data"]["input"] == nested_input
    # Missing input remains absent
    assert "input" not in tool_starts[1]["data"]
    # Provider-supplied null remains present
    assert "input" in tool_starts[2]["data"]
    assert tool_starts[2]["data"]["input"] is None


def test_claude_streaming_content_block_stop_output_ignored(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    stream_fixture = [
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "content_block": {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "bash",
                    "input": {"cmd": "echo hi"},
                },
            },
        }),
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_stop",
                "index": 0,
                "output": "unrelated_stop_output",
                "result": "unrelated_stop_result",
                "content_block": {
                    "output": "unrelated_cb_output",
                    "result": "unrelated_cb_result",
                },
            },
            "output": "unrelated_top_output",
            "result": "unrelated_top_result",
        }),
        json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Done",
            "session_id": "claude-sess",
        }),
    ]

    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.claude.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    params = BackendParams(PROMPT="inspect", cd=workspace, emitter=events.append)
    result = claude_sync(params)
    assert result.outcome == "OK"

    completed_events = [e for e in events if e["kind"] == "tool.completed"]
    assert len(completed_events) == 1
    assert completed_events[0]["data"] == {"status": "completed"}
    assert "output" not in completed_events[0]["data"]
    assert "result" not in completed_events[0]["data"]

    serialized = json.dumps(events)
    assert "unrelated_stop_output" not in serialized
    assert "unrelated_stop_result" not in serialized
    assert "unrelated_cb_output" not in serialized
    assert "unrelated_cb_result" not in serialized
    assert "unrelated_top_output" not in serialized
    assert "unrelated_top_result" not in serialized


def test_codex_streaming_normalization(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    events: list[dict[str, Any]] = []

    def emitter(event: dict[str, Any]) -> None:
        events.append(event)

    monkeypatch.setattr(
        "refract.backends.codex.run_shell_command",
        lambda *args, **kwargs: (line for line in CODEX_JSONL_FIXTURE),
    )

    params = BackendParams(
        PROMPT="inspect",
        cd=workspace,
        emitter=emitter,
    )
    result = codex_sync(params)

    assert result.outcome == "OK"
    assert result.SESSION_ID == "codex-thread-1234-5678"

    assert len(events) >= 1
    started_evt = next(e for e in events if e["kind"] == "tool.started")
    assert started_evt["data"]["tool"] == "bash"
    assert started_evt["data"]["activity"] == "command"
    assert started_evt["data"]["input"] == "cat /etc/passwd secret_key_789"

    completed_evt = next(e for e in events if e["kind"] == "tool.completed")
    assert completed_evt["data"]["status"] == "completed"
    assert "activity" not in completed_evt["data"]
    assert completed_evt["data"]["output"] == "root:secret_hash_value"

    serialized = json.dumps(events)
    # Exclude reasoning
    assert "secret_chain_of_thought" not in serialized
    # Include tool payload
    assert "secret_key_789" in serialized
    assert "secret_hash_value" in serialized
    # Final agent message does not leak tool payload
    assert "secret_key_789" not in result.agent_messages
    assert "secret_hash_value" not in result.agent_messages


def test_codex_streaming_non_bash_tool_activity_tool_call(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    stream_fixture = [
        json.dumps({"type": "thread.started", "thread_id": "codex-other-123"}),
        json.dumps({
            "type": "item.started",
            "item": {
                "type": "tool_call",
                "id": "tool_call_read",
                "name": "read_file",
                "input": {"path": "/tmp/test.txt"},
            },
        }),
        json.dumps({
            "type": "item.completed",
            "item": {
                "type": "tool_call",
                "id": "tool_call_read",
                "name": "read_file",
                "output": "contents",
            },
        }),
    ]
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.codex.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    result = codex_sync(BackendParams(PROMPT="test", cd=workspace, emitter=events.append))
    assert result.outcome == "OK"
    started_evt = next(e for e in events if e["kind"] == "tool.started")
    assert started_evt["data"]["tool"] == "read_file"
    assert started_evt["data"]["activity"] == "tool_call"
    completed_evt = next(e for e in events if e["kind"] == "tool.completed")
    assert "activity" not in completed_evt["data"]


def test_codex_streaming_nested_and_missing_payloads(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    nested_payload = {
        "cmd": "process",
        "params": [1, False, None, {"k": "v"}],
        "zero": 0,
        "empty_str": "",
    }
    nested_output = {"exit_code": 0, "records": [{"id": 101, "ok": True}]}

    stream_fixture = [
        json.dumps({"type": "thread.started", "thread_id": "codex-nested-123"}),
        # Tool 1: complex nested input and output
        json.dumps({
            "type": "item.started",
            "item": {"type": "tool_call", "id": "tc1", "name": "process_tool", "input": nested_payload},
        }),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "tool_call", "id": "tc1", "name": "process_tool", "output": nested_output, "status": "completed"},
        }),
        # Tool 2: missing input and output
        json.dumps({
            "type": "item.started",
            "item": {"type": "tool_call", "id": "tc2", "name": "bare_tool"},
        }),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "tool_call", "id": "tc2", "name": "bare_tool", "status": "completed"},
        }),
        # Tool 3: null input and null output
        json.dumps({
            "type": "item.started",
            "item": {"type": "tool_call", "id": "tc3", "name": "null_tool", "input": None},
        }),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "tool_call", "id": "tc3", "name": "null_tool", "output": None, "status": "completed"},
        }),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "id": "m1", "text": "Finished."},
        }),
    ]

    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.codex.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    params = BackendParams(PROMPT="inspect", cd=workspace, emitter=events.append)
    result = codex_sync(params)
    assert result.outcome == "OK"

    tool_starts = [e for e in events if e["kind"] == "tool.started"]
    tool_comps = [e for e in events if e["kind"] == "tool.completed"]

    assert len(tool_starts) == 3
    assert len(tool_comps) == 3

    # Preserved nested structure
    assert tool_starts[0]["data"]["input"] == nested_payload
    assert tool_comps[0]["data"]["output"] == nested_output
    assert tool_starts[0]["entity_id"] == tool_comps[0]["entity_id"]

    # Missing fields remain absent
    assert "input" not in tool_starts[1]["data"]
    assert "output" not in tool_comps[1]["data"]

    # Provider null remains present
    assert "input" in tool_starts[2]["data"]
    assert tool_starts[2]["data"]["input"] is None
    assert "output" in tool_comps[2]["data"]
    assert tool_comps[2]["data"]["output"] is None


def test_pi_streaming_normalization(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    events: list[dict[str, Any]] = []

    def emitter(event: dict[str, Any]) -> None:
        events.append(event)

    monkeypatch.setattr(
        "refract.backends.pi.run_shell_command",
        lambda *args, **kwargs: (line for line in PI_JSON_FIXTURE),
    )

    params = BackendParams(
        PROMPT="inspect",
        cd=workspace,
        emitter=emitter,
    )
    result = pi_sync(params)

    assert result.outcome == "OK"
    assert result.SESSION_ID == "pi-sess-abc-123"
    assert result.agent_messages == "Final Pi Answer"

    assert len(events) == 3
    kinds = [e["kind"] for e in events]
    assert kinds == ["assistant.text.delta", "tool.started", "tool.completed"]
    assert events[0]["data"]["text"] == "Checking project files."
    assert events[1]["data"]["tool"] == "grep"
    assert events[1]["data"]["activity"] == "tool_call"
    assert events[1]["entity_id"] == "tool-1"
    assert events[1]["data"]["input"] == {"pattern": "secret_pwd_999"}
    assert events[2]["data"]["status"] == "completed"
    assert "activity" not in events[2]["data"]
    assert events[2]["data"]["output"] == "matched secret_pwd_999 in config"
    assert events[2]["entity_id"] == "tool-1"

    serialized = json.dumps(events)
    assert "secret_pwd_999" in serialized
    # Thinking deltas must be excluded
    assert "secret_thinking_pwd" not in serialized
    assert "secret_pwd_999" not in result.agent_messages


def test_pi_streaming_nested_and_missing_payloads(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    nested_args = {"nested": [1, False, None, {"sub": "data"}], "zero": 0}
    nested_result = {"matches": [{"file": "a.py", "line": 42}], "count": 1}

    stream_fixture = [
        json.dumps({"type": "session", "id": "pi-nested-sess"}),
        # Tool 1: camelCase IDs, nested args and result, error status
        json.dumps({
            "type": "tool_execution_start",
            "toolCallId": "call_1",
            "toolName": "nested_pi_tool",
            "args": nested_args,
        }),
        json.dumps({
            "type": "tool_execution_end",
            "toolCallId": "call_1",
            "isError": True,
            "result": nested_result,
        }),
        # Tool 2: snake_case tool_call_id, missing args and result
        json.dumps({
            "type": "tool_call",
            "tool_call_id": "call_2",
            "name": "bare_pi_tool",
        }),
        json.dumps({
            "type": "tool_result",
            "tool_call_id": "call_2",
            "status": "completed",
        }),
        # Tool 3: null args and null result
        json.dumps({
            "type": "tool_execution_start",
            "toolCallId": "call_3",
            "toolName": "null_pi_tool",
            "args": None,
        }),
        json.dumps({
            "type": "tool_execution_end",
            "toolCallId": "call_3",
            "isError": False,
            "result": None,
        }),
        json.dumps({
            "type": "message_end",
            "message": {"role": "assistant", "content": "Done"},
        }),
    ]

    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.pi.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    params = BackendParams(PROMPT="inspect", cd=workspace, emitter=events.append)
    result = pi_sync(params)
    assert result.outcome == "OK"

    tool_starts = [e for e in events if e["kind"] == "tool.started"]
    tool_comps = [e for e in events if e["kind"] == "tool.completed"]

    assert len(tool_starts) == 3
    assert len(tool_comps) == 3

    # Nested structures and error status normalization
    assert tool_starts[0]["data"]["input"] == nested_args
    assert tool_comps[0]["data"]["output"] == nested_result
    assert tool_comps[0]["data"]["status"] == "error"
    assert tool_starts[0]["entity_id"] == tool_comps[0]["entity_id"]

    # Missing fields remain absent
    assert "input" not in tool_starts[1]["data"]
    assert "output" not in tool_comps[1]["data"]
    assert tool_starts[1]["entity_id"] == tool_comps[1]["entity_id"]

    # Null fields remain present
    assert "input" in tool_starts[2]["data"]
    assert tool_starts[2]["data"]["input"] is None
    assert "output" in tool_comps[2]["data"]
    assert tool_comps[2]["data"]["output"] is None


def test_agy_streaming_normalization(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    events: list[dict[str, Any]] = []

    def emitter(event: dict[str, Any]) -> None:
        events.append(event)

    monkeypatch.setattr(
        "refract.backends.agy.run_shell_command",
        lambda *args, **kwargs: (line for line in AGY_STREAM_JSON_FIXTURE),
    )

    params = BackendParams(
        PROMPT="inspect",
        cd=workspace,
        emitter=emitter,
    )
    result = execute(params)

    assert result.outcome == "OK"
    assert result.SESSION_ID == "12345678-1234-1234-1234-123456789abc"

    assert len(events) >= 1
    started_evt = next(e for e in events if e["kind"] == "tool.started")
    assert started_evt["data"]["tool"] == "execute_code"
    assert started_evt["data"]["activity"] == "tool_call"
    assert started_evt["data"]["input"] == {"script": "secret_token_val"}

    completed_evt = next(e for e in events if e["kind"] == "tool.completed")
    assert completed_evt["data"]["status"] == "success"
    assert "activity" not in completed_evt["data"]
    assert completed_evt["data"]["output"] == "secret_stdout_result"

    serialized = json.dumps(events)
    assert "secret_token_val" in serialized
    assert "secret_stdout_result" in serialized
    # Fixture secrets must NOT leak into returned agent_messages
    assert "secret_token_val" not in result.agent_messages
    assert "secret_stdout_result" not in result.agent_messages
    # Diagnostic non-JSON output must be ignored when structured mode is detected
    assert "secret_diagnostic_marker" not in result.agent_messages
    # Arbitrary object fields must never be str() converted into agent_messages
    assert "secret_object_val" not in result.agent_messages
    assert "arbitrary_secret_obj" not in result.agent_messages
    assert result.agent_messages == "Running antigravity analysis.\n\nAntigravity finished successfully."


def test_agy_current_stream_json_protocol(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    conversation_id = "12345678-1234-1234-1234-123456789abc"
    stream_fixture = [
        json.dumps({
            "event": "init",
            "conversation_id": conversation_id,
            "init": {"model": "Gemini 3.8 Flash (High)"},
        }),
        json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": conversation_id,
                "step_index": 1,
                "state": "ACTIVE",
                "step_type": "tool",
                "tool_name": "view_file",
                "tool_info": {
                    "name": "view_file",
                    "parameters": {"AbsolutePath": "/tmp/example.txt"},
                },
            },
        }),
        json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": conversation_id,
                "step_index": 1,
                "state": "DONE",
                "step_type": "tool",
                "tool_name": "view_file",
                "tool_info": {
                    "name": "view_file",
                    "parameters": {"AbsolutePath": "/tmp/example.txt"},
                    "output": "1 line, 3 bytes",
                },
            },
        }),
        json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": conversation_id,
                "step_index": 2,
                "state": "ACTIVE",
                "step_type": "agent_response",
                "text_delta": "OK",
            },
        }),
        json.dumps({
            "event": "result",
            "result": {
                "conversation_id": conversation_id,
                "status": "SUCCESS",
                "response": "OK\n",
                "usage": {"private_diagnostic": "ignored"},
            },
        }),
    ]
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.agy.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    result = execute(
        BackendParams(PROMPT="inspect", cd=workspace, emitter=events.append)
    )

    assert result.outcome == "OK"
    assert result.SESSION_ID == conversation_id
    assert result.agent_messages == "OK"
    assert events == [
        {
            "kind": "tool.started",
            "entity_id": "tool-1",
            "data": {
                "tool": "view_file",
                "activity": "tool_call",
                "input": {"AbsolutePath": "/tmp/example.txt"},
            },
        },
        {
            "kind": "tool.completed",
            "entity_id": "tool-1",
            "data": {"status": "completed", "output": "1 line, 3 bytes"},
        },
        {
            "kind": "assistant.text.delta",
            "entity_id": "msg-1",
            "data": {"text": "OK"},
        },
    ]
    assert "activity" not in events[1]["data"]
    assert "private_diagnostic" not in result.agent_messages


def test_agy_streaming_nested_and_missing_payloads(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    nested_args = {"nested": [1, False, None, {"inner": 123}], "empty": {}}
    nested_res = {"stdout": "ok", "items": [{"val": 1}]}

    stream_fixture = [
        "Created conversation 12345678-1234-1234-1234-123456789abc",
        # Tool 1: arguments and result
        json.dumps({
            "type": "tool.started",
            "tool_name": "agy_tool_1",
            "arguments": nested_args,
        }),
        json.dumps({
            "type": "tool.completed",
            "tool_name": "agy_tool_1",
            "status": "completed",
            "result": nested_res,
        }),
        # Tool 2: arguments and output alternatives
        json.dumps({
            "type": "tool_started",
            "tool": "agy_tool_2",
            "arguments": "arg_string",
        }),
        json.dumps({
            "type": "tool_completed",
            "status": "completed",
            "output": "output_string",
        }),
        # Tool 3: unproven input and args fields are ignored
        json.dumps({
            "type": "tool.started",
            "tool_name": "unproven_tool",
            "input": "ignored_input_val",
            "args": "ignored_args_val",
        }),
        json.dumps({
            "type": "tool.completed",
            "status": "completed",
        }),
        # Tool 4: missing arguments and output
        json.dumps({
            "type": "tool.started",
            "tool_name": "bare_tool",
        }),
        json.dumps({
            "type": "tool.completed",
            "status": "completed",
        }),
        # Tool 5: provider null arguments and output
        json.dumps({
            "type": "tool.started",
            "tool_name": "null_tool",
            "arguments": None,
        }),
        json.dumps({
            "type": "tool.completed",
            "status": "completed",
            "output": None,
        }),
        json.dumps({
            "type": "result",
            "result": "Done",
        }),
    ]

    events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.agy.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    params = BackendParams(PROMPT="inspect", cd=workspace, emitter=events.append)
    result = execute(params)
    assert result.outcome == "OK"

    tool_starts = [e for e in events if e["kind"] == "tool.started"]
    tool_comps = [e for e in events if e["kind"] == "tool.completed"]

    assert len(tool_starts) == 5
    assert len(tool_comps) == 5

    # Nested preservation
    assert tool_starts[0]["data"]["input"] == nested_args
    assert tool_comps[0]["data"]["output"] == nested_res

    # Alternative event type and output field support
    assert tool_starts[1]["data"]["input"] == "arg_string"
    assert tool_comps[1]["data"]["output"] == "output_string"

    # Unproven input/args aliases ignored
    assert "input" not in tool_starts[2]["data"]
    assert "ignored_input_val" not in json.dumps(events)
    assert "ignored_args_val" not in json.dumps(events)

    # Missing fields remain absent
    assert "input" not in tool_starts[3]["data"]
    assert "output" not in tool_comps[3]["data"]

    # Provider null remains present
    assert "input" in tool_starts[4]["data"]
    assert tool_starts[4]["data"]["input"] is None
    assert "output" in tool_comps[4]["data"]
    assert tool_comps[4]["data"]["output"] is None



def test_exact_command_classification_and_unsafe_substring_rejection(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    candidate_tools = ["bash", "Bash", "bash_exec", "sub_bash", "exec", "execute_code", "runner"]

    # Test Claude stream with all candidate tools
    claude_stream = []
    for idx, tool in enumerate(candidate_tools):
        claude_stream.extend([
            json.dumps({
                "type": "stream_event",
                "event": {
                    "type": "content_block_start",
                    "content_block": {
                        "type": "tool_use",
                        "id": f"tu_{idx}",
                        "name": tool,
                        "input": {"command": "bash -c whoami", "cmd": "bash"},
                    },
                },
            }),
            json.dumps({
                "type": "stream_event",
                "event": {"type": "content_block_stop", "index": idx},
            }),
        ])
    claude_stream.append(
        json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "OK",
            "session_id": "c-sess",
        })
    )

    claude_events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.claude.run_shell_command",
        lambda *args, **kwargs: (line for line in claude_stream),
    )
    res_claude = claude_sync(BackendParams(PROMPT="test", cd=workspace, emitter=claude_events.append))
    assert res_claude.outcome == "OK"
    starts = [e for e in claude_events if e["kind"] == "tool.started"]
    assert len(starts) == len(candidate_tools)
    for start in starts:
        tool_name = start["data"]["tool"]
        if tool_name == "bash":
            assert start["data"]["activity"] == "command"
        else:
            assert start["data"]["activity"] == "tool_call"

    # Test Codex stream with candidate tools
    codex_stream = [json.dumps({"type": "thread.started", "thread_id": "codex-test-th"})]
    for idx, tool in enumerate(candidate_tools):
        codex_stream.extend([
            json.dumps({
                "type": "item.started",
                "item": {
                    "type": "tool_call",
                    "id": f"tc_{idx}",
                    "name": tool,
                    "input": {"command": "bash -c whoami"},
                },
            }),
            json.dumps({
                "type": "item.completed",
                "item": {"type": "tool_call", "id": f"tc_{idx}", "output": "ok"},
            }),
        ])
    codex_events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.codex.run_shell_command",
        lambda *args, **kwargs: (line for line in codex_stream),
    )
    res_codex = codex_sync(BackendParams(PROMPT="test", cd=workspace, emitter=codex_events.append))
    assert res_codex.outcome == "OK"
    c_starts = [e for e in codex_events if e["kind"] == "tool.started"]
    assert len(c_starts) == len(candidate_tools)
    for start in c_starts:
        tool_name = start["data"]["tool"]
        if tool_name == "bash":
            assert start["data"]["activity"] == "command"
        else:
            assert start["data"]["activity"] == "tool_call"

    # Test Pi stream: all tools must remain tool_call
    pi_stream = []
    for idx, tool in enumerate(candidate_tools):
        pi_stream.extend([
            json.dumps({
                "type": "tool_execution_start",
                "toolCallId": f"pi_{idx}",
                "toolName": tool,
                "args": {"command": "bash -c ls"},
            }),
            json.dumps({
                "type": "tool_execution_end",
                "toolCallId": f"pi_{idx}",
                "result": "done",
            }),
        ])
    pi_stream.append(
        json.dumps({
            "type": "message_end",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "Pi done"}]},
        })
    )
    pi_events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.pi.run_shell_command",
        lambda *args, **kwargs: (line for line in pi_stream),
    )
    res_pi = pi_sync(BackendParams(PROMPT="test", cd=workspace, emitter=pi_events.append))
    assert res_pi.outcome == "OK"
    pi_starts = [e for e in pi_events if e["kind"] == "tool.started"]
    assert len(pi_starts) == len(candidate_tools)
    for start in pi_starts:
        assert start["data"]["activity"] == "tool_call"

    # Test Agy stream: all tools must remain tool_call
    agy_stream = ["Created conversation 12345678-1234-1234-1234-123456789abc"]
    for idx, tool in enumerate(candidate_tools):
        agy_stream.extend([
            json.dumps({
                "event": "step_update",
                "step_update": {
                    "step_index": idx + 1,
                    "state": "ACTIVE",
                    "step_type": "tool",
                    "tool_name": tool,
                    "tool_info": {"name": tool, "parameters": {"cmd": "bash"}},
                },
            }),
            json.dumps({
                "event": "step_update",
                "step_update": {
                    "step_index": idx + 1,
                    "state": "DONE",
                    "step_type": "tool",
                    "tool_name": tool,
                    "tool_info": {"name": tool, "output": "ok"},
                },
            }),
        ])
    agy_stream.append(
        json.dumps({
            "event": "result",
            "result": {"status": "SUCCESS", "response": "Agy done"},
        })
    )
    agy_events: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "refract.backends.agy.run_shell_command",
        lambda *args, **kwargs: (line for line in agy_stream),
    )
    res_agy = execute(BackendParams(PROMPT="test", cd=workspace, emitter=agy_events.append))
    assert res_agy.outcome == "OK"
    agy_starts = [e for e in agy_events if e["kind"] == "tool.started"]
    assert len(agy_starts) == len(candidate_tools)
    for start in agy_starts:
        assert start["data"]["activity"] == "tool_call"


def test_negative_reasoning_and_diagnostics_excluded(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    cot_secret = "HIDDEN_COT_SECRET_NEVER_EMIT_999"
    diag_secret = "INTERNAL_DIAGNOSTIC_SECRET_888"

    # Claude stream with thinking_delta, system prompt, and diagnostics
    claude_lines = [
        f"[diagnostic] {diag_secret}",
        json.dumps({"type": "system", "content": f"System prompt with {diag_secret}"}),
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "thinking_delta", "thinking": cot_secret},
                "index": 0,
            },
        }),
        json.dumps({
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "Clean response"},
                "index": 1,
            },
        }),
        json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Clean response",
            "session_id": "c-sess",
        }),
    ]
    claude_evts: list[dict[str, Any]] = []
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in claude_lines))
    c_res = claude_sync(BackendParams(PROMPT="test", cd=workspace, emitter=claude_evts.append))
    assert c_res.outcome == "OK"
    assert cot_secret not in json.dumps(claude_evts)
    assert diag_secret not in json.dumps(claude_evts)
    assert not any(e["kind"] == "assistant.reasoning_summary.delta" for e in claude_evts)

    # Codex stream with reasoning item and stderr trace
    codex_lines = [
        f"stderr trace: {diag_secret}",
        json.dumps({"type": "thread.started", "thread_id": "th-1"}),
        json.dumps({
            "type": "item.started",
            "item": {"type": "reasoning", "id": "r1", "text": cot_secret},
        }),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "reasoning", "id": "r1", "text": cot_secret},
        }),
        json.dumps({
            "type": "item.started",
            "item": {"type": "thought", "id": "t1", "text": cot_secret},
        }),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "thought", "id": "t1", "text": cot_secret},
        }),
        json.dumps({
            "type": "item.started",
            "item": {"type": "agent_message", "id": "m1"},
        }),
        json.dumps({
            "type": "item.completed",
            "item": {"type": "agent_message", "id": "m1", "text": "Clean response"},
        }),
    ]
    codex_evts: list[dict[str, Any]] = []
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_lines))
    cdx_res = codex_sync(BackendParams(PROMPT="test", cd=workspace, emitter=codex_evts.append))
    assert cdx_res.outcome == "OK"
    assert cot_secret not in json.dumps(codex_evts)
    assert diag_secret not in json.dumps(codex_evts)
    assert not any(e["kind"] == "assistant.reasoning_summary.delta" for e in codex_evts)

    # Pi stream with thinking deltas and thoughts
    pi_lines = [
        f"pi stderr: {diag_secret}",
        json.dumps({"type": "message_update", "assistantMessageEvent": {"type": "thinking_delta", "delta": cot_secret}}),
        json.dumps({"type": "message_update", "assistantMessageEvent": {"type": "thought", "delta": cot_secret}}),
        json.dumps({"type": "text_delta", "text": "Clean response"}),
        json.dumps({"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": "Clean response"}]}}),
    ]
    pi_evts: list[dict[str, Any]] = []
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in pi_lines))
    p_res = pi_sync(BackendParams(PROMPT="test", cd=workspace, emitter=pi_evts.append))
    assert p_res.outcome == "OK"
    assert cot_secret not in json.dumps(pi_evts)
    assert diag_secret not in json.dumps(pi_evts)
    assert not any(e["kind"] == "assistant.reasoning_summary.delta" for e in pi_evts)

    # Agy stream with thought step_update and usage diagnostics
    agy_lines = [
        "Created conversation 12345678-1234-1234-1234-123456789abc",
        f"[trace] {diag_secret}",
        json.dumps({
            "event": "step_update",
            "step_update": {
                "step_index": 1,
                "state": "ACTIVE",
                "step_type": "thought",
                "text_delta": cot_secret,
            },
        }),
        json.dumps({
            "event": "step_update",
            "step_update": {
                "step_index": 2,
                "state": "ACTIVE",
                "step_type": "reasoning",
                "text_delta": cot_secret,
            },
        }),
        json.dumps({
            "event": "step_update",
            "step_update": {
                "step_index": 3,
                "state": "ACTIVE",
                "step_type": "agent_response",
                "text_delta": "Clean response",
            },
        }),
        json.dumps({
            "event": "result",
            "result": {
                "status": "SUCCESS",
                "response": "Clean response",
                "usage": {"private_diagnostic": diag_secret},
            },
        }),
    ]
    agy_evts: list[dict[str, Any]] = []
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in agy_lines))
    a_res = execute(BackendParams(PROMPT="test", cd=workspace, emitter=agy_evts.append))
    assert a_res.outcome == "OK"
    assert cot_secret not in json.dumps(agy_evts)
    assert diag_secret not in json.dumps(agy_evts)
    assert not any(e["kind"] == "assistant.reasoning_summary.delta" for e in agy_evts)


def test_classify_tool_activity_unit():
    # Exact case-sensitive mappings
    assert classify_tool_activity("claude", "bash") == "command"
    assert classify_tool_activity("codex", "bash") == "command"

    # Case sensitivity rejection
    assert classify_tool_activity("claude", "Bash") == "tool_call"
    assert classify_tool_activity("claude", "BASH") == "tool_call"
    assert classify_tool_activity("codex", "Bash") == "tool_call"

    # Substring rejection
    assert classify_tool_activity("claude", "bash_exec") == "tool_call"
    assert classify_tool_activity("claude", "my_bash") == "tool_call"
    assert classify_tool_activity("codex", "run_bash") == "tool_call"

    # Other tools default to tool_call
    assert classify_tool_activity("claude", "read") == "tool_call"
    assert classify_tool_activity("claude", "exec") == "tool_call"
    assert classify_tool_activity("codex", "execute_code") == "tool_call"
    assert classify_tool_activity("codex", "edit") == "tool_call"

    # Pi and Agy have no verified commands
    assert classify_tool_activity("pi", "bash") == "tool_call"
    assert classify_tool_activity("pi", "grep") == "tool_call"
    assert classify_tool_activity("agy", "bash") == "tool_call"
    assert classify_tool_activity("agy", "exec") == "tool_call"
    assert classify_tool_activity("agy", "execute_code") == "tool_call"
    assert classify_tool_activity("agy", "view_file") == "tool_call"

    # Unknown provider
    assert classify_tool_activity("unknown", "bash") == "tool_call"
    assert classify_tool_activity("", "") == "tool_call"


def test_fixture_usage_parsing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from refract.drivers import _normalize

    fixtures_dir = Path(__file__).parent / "fixtures" / "usage"
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # 1. Claude
    claude_lines = (fixtures_dir / "claude.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in claude_lines))
    c_res = claude_sync(BackendParams(PROMPT="test", cd=workspace))
    assert c_res.outcome == "OK"
    assert c_res.model == "claude-opus-5-5"
    assert not hasattr(c_res, "usage")
    c_drv = _normalize(c_res)
    assert c_drv.model == "claude-opus-5-5"
    assert not hasattr(c_drv, "usage")

    # Claude with usage removed
    c_lines_no_usage = [
        json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "OK", "session_id": "sess"})
    ]
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in c_lines_no_usage))
    c_res_empty = claude_sync(BackendParams(PROMPT="test", cd=workspace))
    assert c_res_empty.outcome == "OK"
    assert c_res_empty.model is None
    assert not hasattr(c_res_empty, "usage")

    # 2. Codex
    codex_lines = (fixtures_dir / "codex.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_lines))
    cdx_res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert cdx_res.outcome == "OK"
    assert cdx_res.model is None
    assert not hasattr(cdx_res, "usage")
    cdx_drv = _normalize(cdx_res)
    assert cdx_drv.model is None
    assert not hasattr(cdx_drv, "usage")

    # Codex with usage removed
    cdx_lines_no_usage = [
        json.dumps({"type": "thread.started", "thread_id": "00000000-0000-0000-0000-000000000000"}),
        json.dumps({"type": "turn.completed"}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in cdx_lines_no_usage))
    cdx_res_empty = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert cdx_res_empty.outcome == "OK"
    assert cdx_res_empty.model is None
    assert not hasattr(cdx_res_empty, "usage")

    # 3. Pi
    pi_lines = (fixtures_dir / "pi.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in pi_lines))
    p_res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert p_res.outcome == "OK"
    assert p_res.model == "gpt-6.1-sol"
    assert not hasattr(p_res, "usage")
    p_drv = _normalize(p_res)
    assert p_drv.model == "gpt-6.1-sol"
    assert not hasattr(p_drv, "usage")

    # Pi with usage removed
    p_lines_no_usage = [
        json.dumps({"type": "session", "id": "00000000-0000-0000-0000-000000000000"}),
        json.dumps({"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": "OK"}]}}),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in p_lines_no_usage))
    p_res_empty = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert p_res_empty.outcome == "OK"
    assert p_res_empty.model is None
    assert not hasattr(p_res_empty, "usage")

    # 4. Agy
    agy_lines = (fixtures_dir / "agy.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in agy_lines))
    a_res = agy_sync(BackendParams(PROMPT="test", cd=workspace))
    assert a_res.outcome == "OK"
    assert a_res.model is None
    assert not hasattr(a_res, "usage")
    a_drv = _normalize(a_res)
    assert a_drv.model is None
    assert not hasattr(a_drv, "usage")

    # Agy with usage removed
    a_lines_no_usage = [
        json.dumps({"event": "result", "result": {"conversation_id": "00000000-0000-0000-0000-000000000000", "status": "SUCCESS", "response": "OK\n"}}),
    ]
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in a_lines_no_usage))
    a_res_empty = agy_sync(BackendParams(PROMPT="test", cd=workspace))
    assert a_res_empty.outcome == "OK"
    assert a_res_empty.model is None
    assert not hasattr(a_res_empty, "usage")


def test_malformed_usage_never_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # Corrupted / invalid usage types in Claude
    c_lines = [
        json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "OK",
            "session_id": "sess",
            "usage": {"input_tokens": "not_an_int", "output_tokens": []},
            "modelUsage": "not_a_dict",
        })
    ]
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in c_lines))
    c_res = claude_sync(BackendParams(PROMPT="test", cd=workspace))
    assert c_res.outcome == "OK"
    assert c_res.model is None
    assert not hasattr(c_res, "usage")


def test_backend_result_telemetry_field():
    from refract.backends import BackendResult
    res = BackendResult(outcome="OK", SESSION_ID="s1", agent_messages="ok", error="", error_class="")
    assert res.telemetry is None


def test_result_model_identity_replaces_usage():
    from refract.backends import BackendResult, classify_backend_output
    from refract.drivers import DriverResult, _normalize

    res = BackendResult(
        outcome="OK",
        SESSION_ID="s1",
        agent_messages="ok",
        error="",
        error_class="",
        model="claude-opus-5-5",
    )
    assert res.model == "claude-opus-5-5"
    assert not hasattr(res, "usage")

    drv = _normalize(res)
    assert drv.model == "claude-opus-5-5"
    assert not hasattr(drv, "usage")

    classified = classify_backend_output(
        backend_name="claude",
        agent_messages="ok",
        session_id="s1",
        error_text="",
        model="claude-opus-5-5",
    )
    assert classified.model == "claude-opus-5-5"
    assert not hasattr(classified, "usage")


def test_behavioral_model_extraction_all_routes_and_propagation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from refract.backends import BackendParams
    from refract.backends.agy import execute as agy_sync
    from refract.backends.claude import execute as claude_sync
    from refract.backends.codex import execute as codex_sync
    from refract.backends.pi import execute as pi_sync
    from refract.config import TargetConfig
    from refract.drivers import DriverResult, _normalize
    from refract.execution import TargetExecutor

    workspace = tmp_path / "ws_behavioral"
    workspace.mkdir()

    # Route 1: Agy with stream model event and absent telemetry
    agy_lines = [
        json.dumps({"event": "model", "model": "agy-test-model"}),
        json.dumps({"event": "result", "result": {"status": "SUCCESS", "response": "ok"}}),
    ]
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in agy_lines))
    res_agy = agy_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res_agy.model == "agy-test-model"

    # Route 2a: Claude with modelUsage in final result
    claude_lines_final = [
        json.dumps({
            "type": "result",
            "subtype": "success",
            "result": "done",
            "modelUsage": {"claude-3-5-sonnet-20241022": {}},
        })
    ]
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in claude_lines_final))
    res_claude_final = claude_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res_claude_final.model == "claude-3-5-sonnet-20241022"

    # Route 2b: Claude with streaming assistant active_model and absent telemetry
    claude_lines_stream = [
        json.dumps({
            "type": "assistant",
            "message": {"role": "assistant", "model": "claude-3-haiku-20240307"},
        }),
        json.dumps({
            "type": "result",
            "subtype": "success",
            "result": "done",
        }),
    ]
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in claude_lines_stream))
    res_claude_stream = claude_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res_claude_stream.model == "claude-3-haiku-20240307"

    # Route 3a: Codex with session_configured in rollout and absent telemetry
    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    thread_id = "11111111-2222-3333-4444-555555555555"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    rollout_file = sessions_dir / f"rollout_{thread_id}.jsonl"
    rollout_file.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id, "cwd": str(workspace)}}) + "\n"
        + json.dumps({"type": "event_msg", "payload": {"type": "session_configured", "model": "gpt-4o-custom"}}) + "\n"
    )
    codex_lines = [
        json.dumps({"type": "thread.started", "thread_id": thread_id}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_lines))
    res_cdx = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res_cdx.model == "gpt-4o-custom"

    # Route 3b: Codex with model_reroute in rollout
    rollout_file.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id, "cwd": str(workspace)}}) + "\n"
        + json.dumps({"type": "event_msg", "payload": {"type": "session_configured", "model": "gpt-4o-custom"}}) + "\n"
        + json.dumps({"type": "event_msg", "payload": {"type": "model_reroute", "to_model": "o3-mini-custom"}}) + "\n"
    )
    res_cdx_reroute = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res_cdx_reroute.model == "o3-mini-custom"

    # Route 4a: Pi with message_end metadata
    pi_lines_msg = [
        json.dumps({"type": "session", "id": "pi-s1"}),
        json.dumps({
            "type": "message_end",
            "message": {"role": "assistant", "model": "pi-streaming-extracted", "content": "hello"},
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in pi_lines_msg))
    res_pi_msg = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res_pi_msg.model == "pi-streaming-extracted"

    # Route 4b: Pi with agent_end messages and absent telemetry
    pi_lines_agent = [
        json.dumps({"type": "session", "id": "pi-s2"}),
        json.dumps({
            "type": "agent_end",
            "messages": [{"role": "assistant", "model": "pi-agent-end-extracted", "content": "done"}],
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in pi_lines_agent))
    res_pi_agent = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res_pi_agent.model == "pi-agent-end-extracted"

    # Route 5: DriverResult._normalize propagation
    drv = _normalize(res_pi_agent)
    assert drv.model == "pi-agent-end-extracted"

    # Route 6: TargetExecutor._result_metadata propagation and fallback
    target_fallback = TargetConfig(id="tgt-1", backend="pi", model="fallback-configured-model")
    meta_present = TargetExecutor._result_metadata(drv, target_fallback, duration_ms=50)
    assert meta_present["execution"]["model"] == "pi-agent-end-extracted"

    drv_none = DriverResult(
        outcome="SUCCESS",
        session_id="pi-s-none",
        text="done",
        error="",
        error_code="",
        model=None,
    )
    meta_fallback = TargetExecutor._result_metadata(drv_none, target_fallback, duration_ms=50)
    assert meta_fallback["execution"]["model"] == "fallback-configured-model"
    assert meta_fallback["telemetry"]["context_window_size"]["quality"] == "unavailable"

    target_empty = TargetConfig(id="tgt-2", backend="pi", model="")
    meta_empty = TargetExecutor._result_metadata(drv_none, target_empty, duration_ms=50)
    assert meta_empty["execution"]["model"] is None


def test_all_four_adapters_final_only_non_streaming_and_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # 1. Claude: final-only non-streaming result with cache accounting
    claude_lines = [
        json.dumps({
            "type": "result",
            "subtype": "success",
            "result": "Claude non-streaming done",
            "session_id": "claude-sess-term",
            "modelUsage": {"claude-3-haiku": {"contextWindow": 200000}},
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "cache_read_input_tokens": 50,
                "cache_creation_input_tokens": 10,
            },
        })
    ]
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in claude_lines))
    c_res = claude_sync(BackendParams(PROMPT="test", cd=workspace))
    assert c_res.outcome == "OK"
    assert c_res.model == "claude-3-haiku"
    assert not hasattr(c_res, "usage")
    assert c_res.telemetry is not None
    assert c_res.telemetry["total_input_tokens"]["value"] == 160
    assert c_res.telemetry["total_output_tokens"]["value"] == 20
    assert c_res.telemetry["cache_read_tokens"]["value"] == 50
    assert c_res.telemetry["cache_write_tokens"]["value"] == 10
    assert c_res.telemetry["context_window_size"]["value"] == 200000

    # 2. Pi: final-only non-streaming agent_end with cache accounting
    pi_lines = [
        json.dumps({
            "type": "session",
            "id": "pi-sess-term",
        }),
        json.dumps({
            "type": "agent_end",
            "messages": [{
                "role": "assistant",
                "content": "Pi non-streaming done",
                "model": "pi-model-term",
            }],
            "usage": {
                "input": 200,
                "output": 40,
                "cacheRead": 60,
                "cacheWrite": 15,
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in pi_lines))
    p_res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert p_res.outcome == "OK"
    assert p_res.model == "pi-model-term"
    assert not hasattr(p_res, "usage")
    assert p_res.telemetry is not None
    assert p_res.telemetry["total_input_tokens"]["value"] == 275
    assert p_res.telemetry["total_output_tokens"]["value"] == 40
    assert p_res.telemetry["cache_read_tokens"]["value"] == 60
    assert p_res.telemetry["cache_write_tokens"]["value"] == 15

    # 3. Codex: non-streaming summary with cache accounting
    codex_lines = [
        json.dumps({"type": "thread.started", "thread_id": "00000000-0000-0000-0000-000000000000"}),
        json.dumps({
            "type": "summary",
            "usage": {
                "input_tokens": 300,
                "output_tokens": 50,
                "cached_input_tokens": 70,
                "cache_write_input_tokens": 25,
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_lines))
    cdx_res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert cdx_res.outcome == "OK"
    assert not hasattr(cdx_res, "usage")
    assert cdx_res.telemetry is not None
    assert cdx_res.telemetry["total_input_tokens"]["value"] == 300
    assert cdx_res.telemetry["total_output_tokens"]["value"] == 50
    assert cdx_res.telemetry["cache_read_tokens"]["value"] == 70
    assert cdx_res.telemetry["cache_write_tokens"]["value"] == 25

    # 4. Agy: final-only result event with cache accounting
    agy_lines = [
        json.dumps({
            "event": "result",
            "result": {
                "conversation_id": "00000000-0000-0000-0000-000000000000",
                "status": "SUCCESS",
                "response": "Agy non-streaming done",
                "usage": {
                    "input_tokens": 400,
                    "output_tokens": 60,
                    "cache_read_tokens": 80,
                    "cache_write_tokens": 30,
                    "model_context_window": 128000,
                },
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in agy_lines))
    a_res = agy_sync(BackendParams(PROMPT="test", cd=workspace))
    assert a_res.outcome == "OK"
    assert not hasattr(a_res, "usage")
    assert a_res.telemetry is not None
    assert a_res.telemetry["total_input_tokens"]["value"] == 400
    assert a_res.telemetry["total_output_tokens"]["value"] == 60
    assert a_res.telemetry["cache_read_tokens"]["value"] == 80
    assert a_res.telemetry["cache_write_tokens"]["value"] == 30
    assert a_res.telemetry["context_window_size"]["value"] == 128000


def test_backend_cancellation_and_failure_precedence_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    cancel_evt = threading.Event()
    cancel_evt.set()

    # Cancellation across backends
    c_res = claude_sync(BackendParams(PROMPT="test", cd=workspace, cancel_event=cancel_evt))
    assert c_res.outcome == "FATAL"
    assert c_res.error_class == "cancelled"
    assert not hasattr(c_res, "usage")

    p_res = pi_sync(BackendParams(PROMPT="test", cd=workspace, cancel_event=cancel_evt))
    assert p_res.outcome == "FATAL"
    assert p_res.error_class == "cancelled"
    assert not hasattr(p_res, "usage")




def test_claude_capacity_not_selected_arbitrarily(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # Case 1: Active model is matched, not first unrelated key in modelUsage
    lines_multi_model = [
        json.dumps({"type": "assistant", "message": {"id": "m1", "model": "claude-opus-5-5", "role": "assistant", "usage": {"input_tokens": 100, "output_tokens": 10}}}),
        json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "OK",
            "usage": {"input_tokens": 100, "output_tokens": 10},
            "modelUsage": {
                "unrelated-fast-model": {"contextWindow": 32000},
                "claude-opus-5-5": {"contextWindow": 200000},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in lines_multi_model))
    res1 = claude_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res1.outcome == "OK"
    assert res1.telemetry is not None
    assert res1.telemetry["context_window_size"]["value"] == 200000

    # Case 2: Active model not found in modelUsage leaves capacity unavailable null
    lines_missing_model = [
        json.dumps({"type": "assistant", "message": {"id": "m1", "model": "claude-opus-5-5", "role": "assistant", "usage": {"input_tokens": 100, "output_tokens": 10}}}),
        json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "OK",
            "usage": {"input_tokens": 100, "output_tokens": 10},
            "modelUsage": {
                "unrelated-fast-model": {"contextWindow": 32000},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in lines_missing_model))
    res2 = claude_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res2.outcome == "OK"
    assert res2.telemetry is not None
    assert res2.telemetry["context_window_size"]["value"] is None
    assert res2.telemetry["context_remaining_percent"]["value"] is None


def test_pi_lifecycle_duplicates_do_not_double_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # Repeated message_end, turn_end, and message_update for the same response
    lines = [
        json.dumps({"type": "session", "id": "s1"}),
        json.dumps({"type": "message_update", "usage": {"input": 0, "output": 0}}),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "responseId": "resp-1",
                "content": [{"type": "text", "text": "Turn 1"}],
                "usage": {"input": 500, "output": 25, "cacheRead": 100, "cacheWrite": 0, "totalTokens": 625},
            },
        }),
        # Repeated turn_end with exact same responseId and usage
        json.dumps({
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "responseId": "resp-1",
                "content": [{"type": "text", "text": "Turn 1"}],
                "usage": {"input": 500, "output": 25, "cacheRead": 100, "cacheWrite": 0, "totalTokens": 625},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in lines))
    res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    # 500 + 100 = 600 input, NOT 1200
    assert res.telemetry["total_input_tokens"]["value"] == 600
    assert res.telemetry["total_output_tokens"]["value"] == 25
    assert res.telemetry["cache_read_tokens"]["value"] == 100


def test_multi_response_pi_telemetry_exceeds_final_message_alone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixtures_dir = Path(__file__).parent / "fixtures" / "usage"
    workspace = tmp_path / "ws"
    workspace.mkdir()

    pi_lines = (fixtures_dir / "pi.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in pi_lines))

    emitted_events: list[dict[str, Any]] = []
    p_res = pi_sync(BackendParams(PROMPT="test", cd=workspace, emitter=emitted_events.append))
    assert p_res.outcome == "OK"

    # Multi-response Pi consumption exceeds the final message alone (12622)
    assert p_res.telemetry is not None
    assert p_res.telemetry["total_input_tokens"]["value"] == 24638
    assert p_res.telemetry["total_output_tokens"]["value"] == 47
    assert p_res.telemetry["cache_read_tokens"]["value"] == 11904

    # Verify at least one observation is emitted before completion
    tel_events = [e for e in emitted_events if e.get("kind") == "telemetry.updated"]
    assert len(tel_events) >= 1

    # Legacy usage removed; model identity preserved
    assert p_res.model == "gpt-6.1-sol"
    assert not hasattr(p_res, "usage")


def test_claude_cache_reads_and_writes_enter_normalized_input_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixtures_dir = Path(__file__).parent / "fixtures" / "usage"
    workspace = tmp_path / "ws"
    workspace.mkdir()

    claude_lines = (fixtures_dir / "claude.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in claude_lines))

    emitted_events: list[dict[str, Any]] = []
    c_res = claude_sync(BackendParams(PROMPT="test", cd=workspace, emitter=emitted_events.append))
    assert c_res.outcome == "OK"

    # Claude cache reads and writes enter normalized input once
    assert c_res.telemetry is not None
    assert c_res.telemetry["total_input_tokens"]["value"] == 66291
    assert c_res.telemetry["cache_read_tokens"]["value"] == 59855
    assert c_res.telemetry["cache_write_tokens"]["value"] == 150
    assert c_res.telemetry["total_output_tokens"]["value"] == 14
    assert c_res.telemetry["context_window_size"]["value"] == 200000

    tel_events = [e for e in emitted_events if e.get("kind") == "telemetry.updated"]
    assert len(tel_events) >= 1


def test_codex_cached_input_not_added_twice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixtures_dir = Path(__file__).parent / "fixtures" / "usage"
    workspace = tmp_path / "ws"
    workspace.mkdir()

    codex_lines = (fixtures_dir / "codex.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_lines))

    emitted_events: list[dict[str, Any]] = []
    cdx_res = codex_sync(BackendParams(PROMPT="test", cd=workspace, emitter=emitted_events.append))
    assert cdx_res.outcome == "OK"

    # Codex cached input is already included in input, not added twice
    assert cdx_res.telemetry is not None
    assert cdx_res.telemetry["total_input_tokens"]["value"] == 22000
    assert cdx_res.telemetry["total_output_tokens"]["value"] == 50
    assert cdx_res.telemetry["cache_read_tokens"]["value"] == 10000
    assert cdx_res.telemetry["cache_write_tokens"]["value"] == 800

    tel_events = [e for e in emitted_events if e.get("kind") == "telemetry.updated"]
    assert len(tel_events) >= 1


def test_agy_final_totals_do_not_duplicate_prior_step_consumption(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixtures_dir = Path(__file__).parent / "fixtures" / "usage"
    workspace = tmp_path / "ws"
    workspace.mkdir()

    agy_lines = (fixtures_dir / "agy.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in agy_lines))

    emitted_events: list[dict[str, Any]] = []
    a_res = agy_sync(BackendParams(PROMPT="test", cd=workspace, emitter=emitted_events.append))
    assert a_res.outcome == "OK"

    # Final totals do not duplicate prior step consumption
    assert a_res.telemetry is not None
    assert a_res.telemetry["total_input_tokens"]["value"] == 14072
    assert a_res.telemetry["total_output_tokens"]["value"] == 168
    assert a_res.telemetry["cache_read_tokens"]["value"] == 1000

    tel_events = [e for e in emitted_events if e.get("kind") == "telemetry.updated"]
    assert len(tel_events) >= 1


def test_no_emitter_execution_returns_normalized_telemetry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    fixtures_dir = Path(__file__).parent / "fixtures" / "usage"
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # Claude Code without emitter
    claude_lines = (fixtures_dir / "claude.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in claude_lines))
    c_res = claude_sync(BackendParams(PROMPT="test", cd=workspace, emitter=None))
    assert c_res.outcome == "OK"
    assert c_res.telemetry is not None
    assert c_res.telemetry["total_input_tokens"]["value"] == 66291
    assert c_res.telemetry["total_output_tokens"]["value"] == 14

    # Pi without emitter
    pi_lines = (fixtures_dir / "pi.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in pi_lines))
    p_res = pi_sync(BackendParams(PROMPT="test", cd=workspace, emitter=None))
    assert p_res.outcome == "OK"
    assert p_res.telemetry is not None
    assert p_res.telemetry["total_input_tokens"]["value"] == 24638
    assert p_res.telemetry["total_output_tokens"]["value"] == 47

    # Codex without emitter
    codex_lines = (fixtures_dir / "codex.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_lines))
    cdx_res = codex_sync(BackendParams(PROMPT="test", cd=workspace, emitter=None))
    assert cdx_res.outcome == "OK"
    assert cdx_res.telemetry is not None
    assert cdx_res.telemetry["total_input_tokens"]["value"] == 22000
    assert cdx_res.telemetry["total_output_tokens"]["value"] == 50

    # Agy without emitter
    agy_lines = (fixtures_dir / "agy.jsonl").read_text().splitlines()
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in agy_lines))
    a_res = agy_sync(BackendParams(PROMPT="test", cd=workspace, emitter=None))
    assert a_res.outcome == "OK"
    assert a_res.telemetry is not None
    assert a_res.telemetry["total_input_tokens"]["value"] == 14072
    assert a_res.telemetry["total_output_tokens"]["value"] == 168


def test_parsing_failures_leave_text_and_outcome_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # 1. Claude with broken/malformed usage payload and non-json line
    c_lines = [
        "not a json line at all",
        json.dumps({"type": "assistant", "message": {"id": "m1", "role": "assistant", "content": [{"type": "text", "text": "claude reply"}], "usage": "invalid"}}),
        json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "claude reply", "usage": {"input_tokens": -99, "output_tokens": "bad"}}),
    ]
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in c_lines))
    c_res = claude_sync(BackendParams(PROMPT="test", cd=workspace))
    assert c_res.outcome == "OK"
    assert c_res.agent_messages == "claude reply"

    # 2. Codex with invalid turn usage
    cdx_lines = [
        json.dumps({"type": "thread.started", "thread_id": "codex-test-tid"}),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "id": "msg1", "text": "codex reply"}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": "wrong", "output_tokens": -5}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in cdx_lines))
    cdx_res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert cdx_res.outcome == "OK"
    assert cdx_res.agent_messages == "codex reply"

    # 3. Pi with malformed usage
    p_lines = [
        json.dumps({"type": "session", "id": "pi-sess"}),
        json.dumps({"type": "message_end", "message": {"role": "assistant", "responseId": "r1", "content": [{"type": "text", "text": "pi reply"}], "usage": {"input": "nan"}}}),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in p_lines))
    p_res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert p_res.outcome == "OK"
    assert p_res.agent_messages == "pi reply"

    # 4. Agy with malformed usage
    a_lines = [
        json.dumps({"event": "step_update", "step_update": {"conversation_id": "00000000-0000-0000-0000-000000000000", "step_index": 1, "state": "DONE", "text_delta": "agy reply", "usage": {"input_tokens": []}}}),
        json.dumps({"event": "result", "result": {"conversation_id": "00000000-0000-0000-0000-000000000000", "status": "SUCCESS", "response": "agy reply", "usage": {"input_tokens": None}}}),
    ]
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in a_lines))
    a_res = agy_sync(BackendParams(PROMPT="test", cd=workspace))
    assert a_res.outcome == "OK"
    assert a_res.agent_messages == "agy reply"


def test_pi_lifecycle_deduplication_without_provider_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    p_lines = [
        json.dumps({"type": "session", "id": "pi-sess-noid"}),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "turn 1 message"}],
                "usage": {"input": 150, "output": 25},
            },
        }),
        json.dumps({
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "turn 1 message"}],
                "usage": {"input": 150, "output": 25},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in p_lines))
    p_res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert p_res.outcome == "OK"
    assert p_res.telemetry is not None
    assert p_res.telemetry["total_input_tokens"]["value"] == 150
    assert p_res.telemetry["total_output_tokens"]["value"] == 25


def test_missing_input_tokens_leaves_input_unavailable_and_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # Claude: output tokens only
    c_lines = [
        json.dumps({
            "type": "assistant",
            "message": {
                "id": "m1",
                "role": "assistant",
                "content": [{"type": "text", "text": "claude reply"}],
                "usage": {"output_tokens": 42},
            },
        }),
        json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "claude reply", "session_id": "c-sess-1"}),
    ]
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in c_lines))
    c_res = claude_sync(BackendParams(PROMPT="test", cd=workspace))
    assert c_res.outcome == "OK"
    assert c_res.telemetry is not None
    assert c_res.telemetry["total_input_tokens"]["value"] is None
    assert c_res.telemetry["total_input_tokens"]["quality"] == "unavailable"
    assert c_res.telemetry["total_output_tokens"]["value"] == 42
    assert c_res.telemetry["completeness"] == "partial"

    # Pi: output tokens only
    p_lines = [
        json.dumps({"type": "session", "id": "pi-sess"}),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "responseId": "r1",
                "content": [{"type": "text", "text": "pi reply"}],
                "usage": {"output": 35},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in p_lines))
    p_res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert p_res.outcome == "OK"
    assert p_res.telemetry is not None
    assert p_res.telemetry["total_input_tokens"]["value"] is None
    assert p_res.telemetry["total_input_tokens"]["quality"] == "unavailable"
    assert p_res.telemetry["total_output_tokens"]["value"] == 35
    assert p_res.telemetry["completeness"] == "partial"

    # Codex: output tokens only
    cdx_lines = [
        json.dumps({"type": "thread.started", "thread_id": "codex-tid"}),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "id": "msg1", "text": "codex reply"}}),
        json.dumps({
            "type": "turn.completed",
            "usage": {"output_tokens": 60},
        }),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in cdx_lines))
    cdx_res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert cdx_res.outcome == "OK"
    assert cdx_res.telemetry is not None
    assert cdx_res.telemetry["total_input_tokens"]["value"] is None
    assert cdx_res.telemetry["total_input_tokens"]["quality"] == "unavailable"
    assert cdx_res.telemetry["total_output_tokens"]["value"] == 60
    assert cdx_res.telemetry["completeness"] == "partial"


def test_malformed_codex_usage_does_not_alter_backend_outcome_or_subsequent_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    cdx_lines = [
        json.dumps({"type": "thread.started", "thread_id": "codex-test-tid"}),
        json.dumps({"type": "turn.completed", "usage": {"reasoning_output_tokens": 10}}),
        json.dumps({"type": "item.started", "item": {"type": "agent_message", "id": "msg1"}}),
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "id": "msg1", "text": "clean completion after malformed usage"}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in cdx_lines))
    emitted: list[dict[str, Any]] = []
    res = codex_sync(BackendParams(PROMPT="test", cd=workspace, emitter=emitted.append))
    assert res.outcome == "OK"
    assert res.agent_messages == "clean completion after malformed usage"
    assert any(e.get("kind") == "assistant.text.delta" for e in emitted)


def test_backends_emit_derived_context_quality(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # Claude derived context quality
    c_lines = [
        json.dumps({
            "type": "assistant",
            "message": {
                "id": "m1",
                "role": "assistant",
                "content": [{"type": "text", "text": "claude reply"}],
                "usage": {"input_tokens": 100, "output_tokens": 20},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in c_lines))
    c_events: list[dict[str, Any]] = []
    claude_sync(BackendParams(PROMPT="test", cd=workspace, emitter=c_events.append))
    c_tel = [e["data"] for e in c_events if e.get("kind") == "telemetry.updated" and "context_used_tokens" in e["data"]]
    assert len(c_tel) == 1
    assert c_tel[0]["quality"] == "derived"

    # Pi derived context quality (when totalTokens is absent)
    p_lines = [
        json.dumps({"type": "session", "id": "pi-sess"}),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "responseId": "r1",
                "content": [{"type": "text", "text": "pi reply"}],
                "usage": {"input": 120, "output": 30},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in p_lines))
    p_events: list[dict[str, Any]] = []
    pi_sync(BackendParams(PROMPT="test", cd=workspace, emitter=p_events.append))
    p_tel = [e["data"] for e in p_events if e.get("kind") == "telemetry.updated" and "context_used_tokens" in e["data"]]
    assert len(p_tel) == 1
    assert p_tel[0]["quality"] == "derived"

    # Codex derived context quality
    cdx_lines = [
        json.dumps({"type": "thread.started", "thread_id": "codex-tid"}),
        json.dumps({
            "type": "turn.completed",
            "usage": {"input_tokens": 200, "output_tokens": 50, "reasoning_output_tokens": 10},
        }),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in cdx_lines))
    cdx_events: list[dict[str, Any]] = []
    codex_sync(BackendParams(PROMPT="test", cd=workspace, emitter=cdx_events.append))
    cdx_tel = [e["data"] for e in cdx_events if e.get("kind") == "telemetry.updated" and "context_used_tokens" in e["data"]]
    assert len(cdx_tel) == 1
    assert cdx_tel[0]["quality"] == "derived"

    # Agy derived context quality
    a_lines = [
        json.dumps({"event": "step_update", "step_update": {"conversation_id": "00000000-0000-0000-0000-000000000000", "step_index": 1, "state": "DONE", "usage": {"input_tokens": 300, "output_tokens": 40}}}),
    ]
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in a_lines))
    a_events: list[dict[str, Any]] = []
    agy_sync(BackendParams(PROMPT="test", cd=workspace, emitter=a_events.append))
    a_tel = [e["data"] for e in a_events if e.get("kind") == "telemetry.updated" and "context_used_tokens" in e["data"]]
    assert len(a_tel) == 1
    assert a_tel[0]["quality"] == "derived"


def test_pi_no_id_lifecycle_scoped_to_actual_turns_and_dedups_repeated_message_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # Turn 1: turn_start -> message_end -> repeated message_end -> turn_end (all no-ID)
    # Turn 2: turn_start -> turn_end-only fallback response (no-ID)
    # Turn 3: turn_start -> turn_end-only fallback response (no-ID)
    p_lines = [
        json.dumps({"type": "session", "id": "pi-sess-no-id-turns"}),
        # Turn 1
        json.dumps({"type": "turn_start"}),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Turn 1 answer"}],
                "usage": {"input": 100, "output": 20},
            },
        }),
        # Repeated message_end within Turn 1 (must be deduplicated)
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Turn 1 answer"}],
                "usage": {"input": 100, "output": 20},
            },
        }),
        # turn_end for Turn 1 (must not double-count)
        json.dumps({
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Turn 1 answer"}],
                "usage": {"input": 100, "output": 20},
            },
        }),
        # Turn 2: turn_end-only fallback response after turn_start
        json.dumps({"type": "turn_start"}),
        json.dumps({
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Turn 2 answer"}],
                "usage": {"input": 200, "output": 30},
            },
        }),
        # Turn 3: second turn_end-only fallback response after turn_start
        json.dumps({"type": "turn_start"}),
        json.dumps({
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Turn 3 answer"}],
                "usage": {"input": 150, "output": 15},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in p_lines))
    p_res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert p_res.outcome == "OK"
    assert p_res.telemetry is not None
    # Input must be 100 + 200 + 150 = 450, output 20 + 30 + 15 = 65
    assert p_res.telemetry["total_input_tokens"]["value"] == 450
    assert p_res.telemetry["total_output_tokens"]["value"] == 65


def test_claude_and_pi_malformed_cache_preserves_unknown_normalized_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # 1. Claude response path: invalid negative, bool, non-finite, and string cache components
    invalid_cache_values = [-5, True, float("nan"), float("inf"), "invalid_component"]
    for bad_val in invalid_cache_values:
        c_lines = [
            json.dumps({
                "type": "assistant",
                "message": {
                    "id": f"msg-{bad_val}",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "reply"}],
                    "usage": {"input_tokens": 100, "cache_read_input_tokens": bad_val, "output_tokens": 20},
                },
            }),
            json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "reply", "session_id": "c-1"}),
        ]
        monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in c_lines))
        c_res = claude_sync(BackendParams(PROMPT="test", cd=workspace))
        assert c_res.outcome == "OK"
        assert c_res.telemetry is not None
        assert c_res.telemetry["total_input_tokens"]["value"] is None
        assert c_res.telemetry["total_input_tokens"]["quality"] == "unavailable"
        assert c_res.telemetry["total_output_tokens"]["value"] == 20
        assert c_res.telemetry["completeness"] == "partial"

    # 2. Claude cumulative path: invalid cacheWrite in result event
    c_cum_lines = [
        json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "reply",
            "session_id": "c-2",
            "usage": {"input_tokens": 120, "cache_creation_input_tokens": -1, "output_tokens": 30},
        }),
    ]
    monkeypatch.setattr("refract.backends.claude.run_shell_command", lambda *a, **k: (l for l in c_cum_lines))
    c_cum_res = claude_sync(BackendParams(PROMPT="test", cd=workspace))
    assert c_cum_res.outcome == "OK"
    assert c_cum_res.telemetry is not None
    assert c_cum_res.telemetry["total_input_tokens"]["value"] is None
    assert c_cum_res.telemetry["total_input_tokens"]["quality"] == "unavailable"
    assert c_cum_res.telemetry["completeness"] == "partial"

    # 3. Pi response path: invalid cacheRead in message_end
    for bad_val in [-10, False, float("nan")]:
        p_lines = [
            json.dumps({"type": "session", "id": "pi-bad"}),
            json.dumps({
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "responseId": "r-bad",
                    "content": [{"type": "text", "text": "reply"}],
                    "usage": {"input": 150, "cacheRead": bad_val, "output": 25},
                },
            }),
        ]
        monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in p_lines))
        p_res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
        assert p_res.outcome == "OK"
        assert p_res.telemetry is not None
        assert p_res.telemetry["total_input_tokens"]["value"] is None
        assert p_res.telemetry["total_input_tokens"]["quality"] == "unavailable"
        assert p_res.telemetry["total_output_tokens"]["value"] == 25
        assert p_res.telemetry["completeness"] == "partial"

    # 4. Pi cumulative path: invalid cacheWrite in summary
    p_cum_lines = [
        json.dumps({"type": "session", "id": "pi-cum-bad"}),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "responseId": "r-cum",
                "content": [{"type": "text", "text": "cum reply"}],
            },
        }),
        json.dumps({
            "type": "summary",
            "usage": {"input": 150, "cacheWrite": -1, "output": 25},
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in p_cum_lines))
    p_cum_res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert p_cum_res.outcome == "OK"
    assert p_cum_res.telemetry is not None
    assert p_cum_res.telemetry["total_input_tokens"]["value"] is None
    assert p_cum_res.telemetry["total_input_tokens"]["quality"] == "unavailable"
    assert p_cum_res.telemetry["completeness"] == "partial"

    # 5. Legitimate omitted and zero fields produce complete input
    p_ok_lines = [
        json.dumps({"type": "session", "id": "pi-ok"}),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "responseId": "r-ok",
                "content": [{"type": "text", "text": "reply"}],
                "usage": {"input": 150, "cacheRead": 0, "output": 25},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in p_ok_lines))
    p_ok_res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert p_ok_res.outcome == "OK"
    assert p_ok_res.telemetry is not None
    assert p_ok_res.telemetry["total_input_tokens"]["value"] == 150
    assert p_ok_res.telemetry["completeness"] == "complete"


def test_pi_total_tokens_never_labeled_reported_context_and_derivation_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # Normal payload with totalTokens present
    lines = [
        json.dumps({"type": "session", "id": "pi-sess"}),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "responseId": "r1",
                "content": [{"type": "text", "text": "pi reply"}],
                "usage": {"input": 500, "output": 25, "cacheRead": 100, "cacheWrite": 0, "totalTokens": 625},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in lines))
    res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    # totalTokens is response usage, not explicit context occupancy:
    # Context must be derived with source="derived" and quality="derived", NEVER reported/provider
    assert res.telemetry["context_used_tokens"]["value"] == 625
    assert res.telemetry["context_used_tokens"]["quality"] == "derived"
    assert res.telemetry["context_used_tokens"]["source"] == "derived"

    # When retained components are not established (missing input tokens), context is unavailable even if totalTokens present
    no_input_lines = [
        json.dumps({"type": "session", "id": "pi-sess"}),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "responseId": "r2",
                "content": [{"type": "text", "text": "pi reply"}],
                "usage": {"output": 25, "totalTokens": 625},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in no_input_lines))
    res_no_in = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res_no_in.outcome == "OK"
    assert res_no_in.telemetry is not None
    assert res_no_in.telemetry["context_used_tokens"]["value"] is None
    assert res_no_in.telemetry["context_used_tokens"]["quality"] == "unavailable"


def test_pi_repeated_no_id_turn_end_does_not_open_implicit_turn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    # 1. Exact reproduction: turn_start -> message_end -> turn_end -> turn_end
    # for one assistant response with input 100, output 20, no responseId.
    # Must report 100, not 200.
    repro_lines = [
        json.dumps({"type": "session", "id": "pi-sess-repro"}),
        json.dumps({"type": "turn_start"}),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Turn 1 message"}],
                "usage": {"input": 100, "output": 20},
            },
        }),
        json.dumps({
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Turn 1 message"}],
                "usage": {"input": 100, "output": 20},
            },
        }),
        json.dumps({
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Turn 1 message"}],
                "usage": {"input": 100, "output": 20},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in repro_lines))
    repro_res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert repro_res.outcome == "OK"
    assert repro_res.telemetry is not None
    assert repro_res.telemetry["total_input_tokens"]["value"] == 100
    assert repro_res.telemetry["total_output_tokens"]["value"] == 20

    # 2. Distinct subsequent turn after actual new-turn boundary (turn_start) with repeated turn_end
    multi_turn_lines = repro_lines + [
        json.dumps({"type": "turn_start"}),
        json.dumps({
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Turn 2 message"}],
                "usage": {"input": 150, "output": 15},
            },
        }),
        json.dumps({
            "type": "turn_end",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Turn 2 message"}],
                "usage": {"input": 150, "output": 15},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in multi_turn_lines))
    multi_res = pi_sync(BackendParams(PROMPT="test", cd=workspace))
    assert multi_res.outcome == "OK"
    assert multi_res.telemetry is not None
    assert multi_res.telemetry["total_input_tokens"]["value"] == 250
    assert multi_res.telemetry["total_output_tokens"]["value"] == 35


def test_codex_rollout_exact_session_enrichment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-111111111111"
    session_file = sessions_dir / f"rollout_{session_id}.jsonl"
    session_file.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}}) + "\n"
    )

    codex_stdout = [
        json.dumps({"type": "thread.started", "thread_id": session_id}),
        json.dumps({"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "OK"}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 50, "cached_input_tokens": 200}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_stdout))

    emitted: list[dict[str, Any]] = []
    res = codex_sync(BackendParams(PROMPT="test", cd=workspace, emitter=emitted.append))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["context_window_size"]["value"] is None
    assert res.telemetry["context_window_size"]["quality"] == "unavailable"
    assert res.telemetry["context_used_tokens"]["value"] == 1050
    assert res.telemetry["context_used_tokens"]["quality"] == "derived"
    assert res.telemetry["context_used_tokens"]["source"] == "derived"
    assert res.telemetry["context_remaining_percent"]["value"] is None


def test_codex_rollout_refuses_mismatched_session_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-111111111111"
    wrong_id = "00000000-0000-0000-0000-999999999999"
    session_file = sessions_dir / f"rollout_{session_id}.jsonl"
    session_file.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": wrong_id, "cwd": str(workspace)}}) + "\n"
        + json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 9000, "cached_input_tokens": 0, "output_tokens": 999, "reasoning_output_tokens": 0, "total_tokens": 9999}, "last_token_usage": {"input_tokens": 900, "cached_input_tokens": 100, "output_tokens": 99, "reasoning_output_tokens": 9, "total_tokens": 999}, "model_context_window": 200000}}}) + "\n"
    )

    codex_stdout = [
        json.dumps({"type": "thread.started", "thread_id": session_id}),
        json.dumps({"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "OK"}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 50}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_stdout))

    res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["context_window_size"]["value"] is None


def test_codex_rollout_never_selects_unrelated_latest_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-111111111111"
    unrelated_id = "00000000-0000-0000-0000-888888888888"
    unrelated_file = sessions_dir / f"rollout_{unrelated_id}.jsonl"
    unrelated_file.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": unrelated_id, "cwd": str(workspace)}}) + "\n"
        + json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 4000, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 4000}, "last_token_usage": {"input_tokens": 4000, "cached_input_tokens": 0, "output_tokens": 0, "reasoning_output_tokens": 0, "total_tokens": 4000}, "model_context_window": 128000}}}) + "\n"
    )

    codex_stdout = [
        json.dumps({"type": "thread.started", "thread_id": session_id}),
        json.dumps({"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "OK"}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 50}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_stdout))

    res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["context_window_size"]["value"] is None


def test_codex_rollout_handles_partial_and_malformed_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-222222222222"
    session_file = sessions_dir / f"rollout_{session_id}.jsonl"

    session_file.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}}) + "\n"
        + "malformed raw non-json line\n"
        + json.dumps({"type": "event_msg", "payload": "not a dict payload"}) + "\n"
        + '{"type": "event_msg", "payload": {"type": "noise"' # unterminated partial line
    )

    codex_stdout = [
        json.dumps({"type": "thread.started", "thread_id": session_id}),
        json.dumps({"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "OK"}}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 50}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_stdout))

    res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    # Context occupied is derived from turn usage; capacity is unverified null
    assert res.telemetry["context_used_tokens"]["value"] == 1050
    assert res.telemetry["context_used_tokens"]["quality"] == "derived"
    assert res.telemetry["context_window_size"]["value"] is None


def test_codex_rollout_handles_file_growth_and_incremental_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-333333333333"
    session_file = sessions_dir / f"rollout_{session_id}.jsonl"
    session_file.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}}) + "\n"
    )

    def stream_lines(*args, **kwargs):
        yield json.dumps({"type": "thread.started", "thread_id": session_id})
        with session_file.open("a") as f:
            f.write(json.dumps({"type": "event_msg", "payload": {"type": "noise", "data": 1}}) + "\n")
        yield json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 20}})
        with session_file.open("a") as f:
            f.write(json.dumps({"type": "event_msg", "payload": {"type": "noise", "data": 2}}) + "\n")
        yield json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1500, "output_tokens": 30}})

    monkeypatch.setattr("refract.backends.codex.run_shell_command", stream_lines)

    res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["context_used_tokens"]["value"] == 1530
    assert res.telemetry["context_window_size"]["value"] is None


def test_codex_rollout_handles_file_truncation_and_rotation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-444444444444"
    session_file = sessions_dir / f"rollout_{session_id}.jsonl"

    session_file.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}}) + "\n"
        + ("x" * 5000) + "\n"
    )

    def stream_lines(*args, **kwargs):
        yield json.dumps({"type": "thread.started", "thread_id": session_id})
        # Simulate truncation: rewrite file with shorter content
        session_file.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}}) + "\n"
        )
        yield json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 20}})

    monkeypatch.setattr("refract.backends.codex.run_shell_command", stream_lines)

    res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["context_used_tokens"]["value"] == 1020


def test_codex_rollout_compaction_invalidates_stale_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-555555555555"
    session_file = sessions_dir / f"rollout_{session_id}.jsonl"

    session_file.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}}) + "\n"
        + json.dumps({"type": "event_msg", "payload": {"type": "context_compacted"}}) + "\n"
    )

    codex_stdout = [
        json.dumps({"type": "thread.started", "thread_id": session_id}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 20}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_stdout))

    res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    # Compaction invalidates context
    assert res.telemetry["context_used_tokens"]["value"] is None
    assert res.telemetry["context_window_size"]["value"] is None


def test_codex_rollout_concurrent_sessions_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace1 = tmp_path / "ws1"
    workspace2 = tmp_path / "ws2"
    workspace1.mkdir()
    workspace2.mkdir()

    s1 = "00000000-0000-0000-0000-aaaaaaaaaaaa"
    s2 = "00000000-0000-0000-0000-bbbbbbbbbbbb"

    f1 = sessions_dir / f"rollout_{s1}.jsonl"
    f2 = sessions_dir / f"rollout_{s2}.jsonl"

    f1.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": s1, "cwd": str(workspace1)}}) + "\n"
    )
    f2.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": s2, "cwd": str(workspace2)}}) + "\n"
    )

    monkeypatch.setattr(
        "refract.backends.codex.run_shell_command",
        lambda *a, **k: (l for l in [json.dumps({"type": "thread.started", "thread_id": s1}), json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 10}})]),
    )
    res1 = codex_sync(BackendParams(PROMPT="test", cd=workspace1))

    monkeypatch.setattr(
        "refract.backends.codex.run_shell_command",
        lambda *a, **k: (l for l in [json.dumps({"type": "thread.started", "thread_id": s2}), json.dumps({"type": "turn.completed", "usage": {"input_tokens": 200, "output_tokens": 20}})]),
    )
    res2 = codex_sync(BackendParams(PROMPT="test", cd=workspace2))

    assert res1.telemetry["context_used_tokens"]["value"] == 110
    assert res2.telemetry["context_used_tokens"]["value"] == 220
    assert res1.telemetry["context_window_size"]["value"] is None
    assert res2.telemetry["context_window_size"]["value"] is None


def test_codex_rollout_bounded_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-666666666666"
    session_file = sessions_dir / f"rollout_{session_id}.jsonl"

    # Write a header followed by thousands of noise lines, bounded read should not choke or run forever
    lines = [json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}})]
    for i in range(500):
        lines.append(json.dumps({"type": "event_msg", "payload": {"type": "noise", "index": i}}))
    session_file.write_text("\n".join(lines) + "\n")

    codex_stdout = [
        json.dumps({"type": "thread.started", "thread_id": session_id}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 50}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_stdout))

    res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["context_used_tokens"]["value"] == 1050
    assert res.telemetry["context_window_size"]["value"] is None


def test_codex_token_count_nested_usage_enriches_latest_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from refract.backends.codex import _CodexRolloutCollector
    from refract.telemetry import TelemetryAccumulator

    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    session_id = "00000000-0000-0000-0000-111111111111"
    path = sessions_dir / f"rollout_{session_id}.jsonl"
    records = [
        {"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": 5000, "cached_input_tokens": 2000, "output_tokens": 700, "reasoning_output_tokens": 100, "total_tokens": 5700},
            "last_token_usage": {"input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 70, "reasoning_output_tokens": 10, "total_tokens": 1070},
            "model_context_window": 64000,
        }}}
    ]
    path.write_text("\n".join(json.dumps(x) for x in records) + "\n")
    acc = TelemetryAccumulator()
    collector = _CodexRolloutCollector(cwd=workspace, session_id=session_id, accumulator=acc)
    collector.poll()
    result = acc.snapshot().model_dump(mode="json")
    assert result["context_window_size"]["value"] == 64000
    assert result["context_window_size"]["quality"] == "reported"
    assert result["context_used_tokens"]["value"] == 1060
    assert result["context_used_tokens"]["quality"] == "derived"

    # A later valid token_count replaces the context snapshot (not cumulative usage).
    next_record = {"type": "event_msg", "payload": {"type": "token_count", "info": {
        "total_token_usage": {"input_tokens": 6000, "cached_input_tokens": 2400, "output_tokens": 800, "reasoning_output_tokens": 110, "total_tokens": 6800},
        "last_token_usage": {"input_tokens": 300, "cached_input_tokens": 100, "output_tokens": 30, "reasoning_output_tokens": 5, "total_tokens": 330},
        "model_context_window": 32000,
    }}}
    with path.open("a") as rollout:
        rollout.write(json.dumps(next_record) + "\n")
    collector.poll()
    replaced = acc.snapshot().model_dump(mode="json")
    assert replaced["context_used_tokens"]["value"] == 325
    assert replaced["context_window_size"]["value"] == 32000


def test_codex_verified_rollout_context_wins_over_turn_consumption_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    session_id = "00000000-0000-0000-0000-111111111111"
    usage = {"input_tokens": 1000, "cached_input_tokens": 400, "output_tokens": 70, "reasoning_output_tokens": 10, "total_tokens": 1070}
    (sessions_dir / f"rollout_{session_id}.jsonl").write_text(
        json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}}) + "\n"
        + json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": 5000, "cached_input_tokens": 2000, "output_tokens": 700, "reasoning_output_tokens": 100, "total_tokens": 5700},
            "last_token_usage": usage, "model_context_window": 64000,
        }}}) + "\n"
    )
    lines = [
        json.dumps({"type": "thread.started", "thread_id": session_id}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 5000, "output_tokens": 700, "reasoning_output_tokens": 100}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: iter(lines))
    result = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert result.telemetry["context_used_tokens"]["value"] == 1060
    assert result.telemetry["context_window_size"]["value"] == 64000
    assert result.telemetry["total_input_tokens"]["value"] == 5000


def test_codex_rollout_session_switch_invalidates_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from refract.backends.codex import _CodexRolloutCollector
    from refract.telemetry import TelemetryAccumulator

    root = tmp_path / "codex"
    (root / "sessions").mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(root))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    acc = TelemetryAccumulator()
    emitted = []
    collector = _CodexRolloutCollector(cwd=workspace, session_id="00000000-0000-0000-0000-111111111111", accumulator=acc, emitter=emitted.append)
    acc.record_context_snapshot(used_tokens=1060, window_size=64000)
    collector.set_session_id("00000000-0000-0000-0000-222222222222")
    snap = acc.snapshot().model_dump(mode="json")
    assert snap["context_used_tokens"]["value"] is None
    assert snap["context_window_size"]["value"] is None
    assert any(e["data"].get("invalidate_context") for e in emitted)


def test_codex_rollout_rejects_replacement_between_discovery_and_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from refract.backends.codex import _CodexRolloutCollector
    from refract.telemetry import TelemetryAccumulator

    root = tmp_path / "codex"
    sessions = root / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(root))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    sid = "00000000-0000-0000-0000-111111111111"
    path = sessions / f"rollout_{sid}.jsonl"
    path.write_text(json.dumps({"type": "session_meta", "payload": {"id": sid, "cwd": str(workspace)}}) + "\n")
    acc = TelemetryAccumulator()
    collector = _CodexRolloutCollector(cwd=workspace, session_id=sid, accumulator=acc)
    find = collector._find_exact_file
    def replace_after_discovery():
        found = find()
        replacement = path.with_suffix(".replacement")
        replacement.write_text(json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": 900, "output_tokens": 90, "reasoning_output_tokens": 0},
            "model_context_window": 200000,
        }}}) + "\n")
        replacement.replace(path)
        return found
    collector._find_exact_file = replace_after_discovery
    collector.poll()
    assert acc.snapshot().context_window_size.value is None


def test_codex_rollout_budget_exhaustion_invalidates_prefix_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from refract.backends.codex import _CodexRolloutCollector
    from refract.telemetry import TelemetryAccumulator

    root = tmp_path / "codex"
    sessions = root / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(root))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    sid = "00000000-0000-0000-0000-111111111111"
    path = sessions / f"rollout_{sid}.jsonl"
    header = json.dumps({"type": "session_meta", "payload": {"id": sid, "cwd": str(workspace)}})
    usage = {"input_tokens": 100, "cached_input_tokens": 0, "output_tokens": 10, "reasoning_output_tokens": 0, "total_tokens": 110}
    event = json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
        "total_token_usage": usage, "last_token_usage": usage, "model_context_window": 64000,
    }}})
    path.write_text(header + "\n" + event + "\n" + (" " * 5000) + "\n")
    acc = TelemetryAccumulator()
    collector = _CodexRolloutCollector(cwd=workspace, session_id=sid, accumulator=acc)
    collector.max_bytes_per_poll = 4096
    collector.max_total_bytes = 4096
    collector.poll()
    assert acc.snapshot().context_used_tokens.value is None
    assert acc.snapshot().context_window_size.value is None


def test_codex_same_inode_truncation_requires_session_header_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from refract.backends.codex import _CodexRolloutCollector
    from refract.telemetry import TelemetryAccumulator

    root = tmp_path / "codex"
    sessions = root / "sessions"
    sessions.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(root))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    sid = "00000000-0000-0000-0000-111111111111"
    path = sessions / f"rollout_{sid}.jsonl"
    header = json.dumps({"type": "session_meta", "payload": {"id": sid, "cwd": str(workspace)}})
    valid_usage = {"input_tokens": 100, "output_tokens": 10, "reasoning_output_tokens": 0}
    valid = json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
        "last_token_usage": valid_usage, "model_context_window": 64000,
    }}})
    path.write_text(header + "\n" + valid + "\n")
    original_inode = path.stat().st_ino
    acc = TelemetryAccumulator()
    collector = _CodexRolloutCollector(cwd=workspace, session_id=sid, accumulator=acc)
    collector.poll()
    assert acc.snapshot().context_used_tokens.value == 110

    hostile_usage = {"input_tokens": 900, "output_tokens": 90, "reasoning_output_tokens": 0}
    token_only = json.dumps({"type": "event_msg", "payload": {"type": "token_count", "info": {
        "last_token_usage": hostile_usage, "model_context_window": 200000,
    }}})
    with path.open("w") as rollout:
        rollout.write(token_only + "\n")
    assert path.stat().st_ino == original_inode
    collector.poll()
    current = acc.snapshot()
    assert current.context_used_tokens.value is None
    assert current.context_window_size.value is None


def test_codex_rollout_refuses_mismatched_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-777777777777"
    mismatched_id = "00000000-0000-0000-0000-999999999999"
    session_file = sessions_dir / f"rollout_{session_id}.jsonl"

    # File has mismatched session id in payload
    session_file.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": mismatched_id, "cwd": str(workspace)}}) + "\n"
    )

    codex_stdout = [
        json.dumps({"type": "thread.started", "thread_id": session_id}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 50}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_stdout))

    res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["context_window_size"]["value"] is None


def test_codex_rollout_missing_file_degrades_gracefully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-888888888888"

    codex_stdout = [
        json.dumps({"type": "thread.started", "thread_id": session_id}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1000, "output_tokens": 50}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_stdout))

    res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["context_window_size"]["value"] is None
    # Context used tokens still derived from turn usage
    assert res.telemetry["context_used_tokens"]["value"] == 1050


def test_codex_rollout_lifecycle_cancellation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    cancel_evt = threading.Event()
    cancel_evt.set()

    # Cancelled before execution starts
    res = codex_sync(BackendParams(PROMPT="test", cd=workspace, cancel_event=cancel_evt))
    assert res.outcome in ("FATAL", "CANCELLED", "ABORTED") or res.error_class in ("cancelled", "timeout")


def test_codex_resumed_session_without_baseline_marks_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-cccccccccccc"

    # Resumed session: turn completed emits invocation-local tokens (500, 150),
    # then thread.completed emits cumulative tokens across session (2000, 400).
    # Because pre-execution baseline is not available, invocation-local turn totals
    # are preserved and completeness is marked partial.
    codex_stdout = [
        json.dumps({"type": "thread.started", "thread_id": session_id}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 500, "output_tokens": 150}}),
        json.dumps({"type": "thread.completed", "usage": {"input_tokens": 2000, "output_tokens": 400}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_stdout))

    res = codex_sync(BackendParams(PROMPT="test", cd=workspace, SESSION_ID=session_id))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["total_input_tokens"]["value"] == 500
    assert res.telemetry["total_output_tokens"]["value"] == 150
    assert res.telemetry["completeness"] == "partial"


def test_codex_fresh_session_cumulative_reconciles_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-dddddddddddd"

    # Fresh session (no SESSION_ID): invocation is whole session. thread.completed reconciles complete.
    codex_stdout = [
        json.dumps({"type": "thread.started", "thread_id": session_id}),
        json.dumps({"type": "turn.completed", "usage": {"input_tokens": 600, "output_tokens": 100}}),
        json.dumps({"type": "thread.completed", "usage": {"input_tokens": 600, "output_tokens": 100}}),
    ]
    monkeypatch.setattr("refract.backends.codex.run_shell_command", lambda *a, **k: (l for l in codex_stdout))

    res = codex_sync(BackendParams(PROMPT="test", cd=workspace))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["completeness"] == "complete"
    assert res.telemetry["total_input_tokens"]["value"] == 600
    assert res.telemetry["total_output_tokens"]["value"] == 100


def test_pi_capacity_remains_null_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pi_stdout = [
        json.dumps({"type": "session", "id": "pi-sess-111"}),
        json.dumps({"type": "turn_start"}),
        json.dumps({
            "type": "message_end",
            "message": {
                "role": "assistant",
                "id": "msg_1",
                "content": "Hello",
                "usage": {"input": 400, "output": 50, "cacheRead": 100},
            },
        }),
        json.dumps({"type": "turn_end"}),
    ]
    monkeypatch.setattr("refract.backends.pi.run_shell_command", lambda *a, **k: (l for l in pi_stdout))

    res = pi_sync(BackendParams(PROMPT="test", cd=tmp_path))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    # Context occupied is derived from turn usage
    assert res.telemetry["context_used_tokens"]["value"] == 550
    # Capacity must remain null without external catalog / RPC daemon
    assert res.telemetry["context_window_size"]["value"] is None
    assert res.telemetry["context_remaining_percent"]["value"] is None


def test_agy_capacity_remains_null_without_explicit_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    agy_stdout = [
        json.dumps({
            "event": "step_update",
            "step_update": {
                "state": "DONE",
                "step_type": "agent_response",
                "step_index": 1,
                "text_delta": "Working",
                "usage": {"input_tokens": 800, "output_tokens": 120},
            },
        }),
        json.dumps({
            "event": "result",
            "result": {
                "conversation_id": "00000000-0000-0000-0000-aaaaaaaaaaaa",
                "response": "Done",
                "usage": {"input_tokens": 800, "output_tokens": 120},
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in agy_stdout))

    res = agy_sync(BackendParams(PROMPT="test", cd=tmp_path))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["context_used_tokens"]["value"] == 920
    # Capacity must remain null when no explicit metadata is present
    assert res.telemetry["context_window_size"]["value"] is None
    assert res.telemetry["context_remaining_percent"]["value"] is None


def test_agy_explicit_context_metadata_handled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    agy_stdout = [
        json.dumps({
            "event": "step_update",
            "step_update": {
                "state": "DONE",
                "step_type": "agent_response",
                "step_index": 1,
                "text_delta": "Working",
                "usage": {
                    "input_tokens": 800,
                    "output_tokens": 120,
                    "model_context_window": 200000,
                },
            },
        }),
        json.dumps({
            "event": "result",
            "result": {
                "conversation_id": "00000000-0000-0000-0000-aaaaaaaaaaaa",
                "response": "Done",
                "usage": {
                    "input_tokens": 800,
                    "output_tokens": 120,
                    "model_context_window": 200000,
                },
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in agy_stdout))

    res = agy_sync(BackendParams(PROMPT="test", cd=tmp_path))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    assert res.telemetry["context_used_tokens"]["value"] == 920
    # Explicit capacity should be recorded and remaining percent derived
    assert res.telemetry["context_window_size"]["value"] == 200000
    assert res.telemetry["context_remaining_percent"]["value"] == 99.54


def test_codex_discovery_bounded_entries_and_depth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-aaaaaaaa1111"
    # Create 60 dummy files/dirs so an entry-bounded scan cannot scan forever
    for i in range(60):
        dummy = sessions_dir / f"dummy_dir_{i:03d}"
        dummy.mkdir()
        (dummy / "noise.jsonl").write_text("noise\n")

    # Target file placed deep or far in listing
    target_dir = sessions_dir / "dummy_dir_059"
    target_file = target_dir / f"rollout_{session_id}.jsonl"
    target_file.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}}) + "\n"
    )

    from refract.backends.codex import _CodexRolloutCollector
    from refract.telemetry import TelemetryAccumulator

    acc = TelemetryAccumulator()
    collector = _CodexRolloutCollector(cwd=workspace, session_id=session_id, accumulator=acc)
    # Must enforce entry limits
    assert collector.MAX_DISCOVERY_ENTRIES <= 50
    assert collector.MAX_DISCOVERY_RETRIES <= 3


def test_codex_discovery_missing_file_retry_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-bbbbbbbb2222"
    from refract.backends.codex import _CodexRolloutCollector
    from refract.telemetry import TelemetryAccumulator

    acc = TelemetryAccumulator()
    collector = _CodexRolloutCollector(cwd=workspace, session_id=session_id, accumulator=acc)

    # Poll multiple times when file does not exist
    for _ in range(10):
        collector.poll()

    assert collector.missing_discovery_retries <= collector.MAX_DISCOVERY_RETRIES
    # Once cap is reached, no file is set and further polls do not retry
    assert collector.session_file is None
    assert collector.missing_discovery_retries == collector.MAX_DISCOVERY_RETRIES


def test_codex_discovery_refuses_symlinks_and_hostile_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-cccccccc3333"

    # Create hostile symlink pointing outside sessions_dir
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret_target = outside_dir / f"rollout_{session_id}.jsonl"
    secret_target.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}}) + "\n"
    )
    symlink_file = sessions_dir / f"symlink_{session_id}.jsonl"
    symlink_file.symlink_to(secret_target)

    from refract.backends.codex import _CodexRolloutCollector
    from refract.telemetry import TelemetryAccumulator

    acc = TelemetryAccumulator()
    collector = _CodexRolloutCollector(cwd=workspace, session_id=session_id, accumulator=acc)
    collector.poll()
    # Must refuse symlink escape
    assert collector.session_file is None


def test_codex_rollout_rotation_equal_size_revalidates_and_emits_invalidation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    codex_home = tmp_path / "codex_home"
    sessions_dir = codex_home / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    workspace = tmp_path / "ws"
    workspace.mkdir()

    session_id = "00000000-0000-0000-0000-dddddddd4444"
    session_file = sessions_dir / f"rollout_{session_id}.jsonl"

    content1 = json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}}) + "\n"
    session_file.write_text(content1)

    emitted: list[dict[str, Any]] = []
    from refract.backends.codex import _CodexRolloutCollector
    from refract.telemetry import TelemetryAccumulator

    acc = TelemetryAccumulator()
    collector = _CodexRolloutCollector(cwd=workspace, session_id=session_id, accumulator=acc, emitter=emitted.append)
    collector.poll()
    assert collector.session_file is not None
    orig_ino = collector.file_ino
    assert orig_ino is not None

    # Replace file with new inode of exactly equal size
    session_file.unlink()
    content2 = json.dumps({"type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}}) + "\n"
    session_file.write_text(content2)

    collector.poll()
    # Rotation must revalidate inode, detect replacement, and emit invalidation
    assert any(
        e.get("kind") == "telemetry.updated"
        and e.get("data", {}).get("quality") == "unavailable"
        for e in emitted
    )


def test_agy_context_provenance_separated_from_capacity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    agy_stdout = [
        json.dumps({
            "event": "step_update",
            "step_update": {
                "state": "DONE",
                "step_type": "agent_response",
                "step_index": 1,
                "text_delta": "Working",
                "usage": {
                    "input_tokens": 800,
                    "output_tokens": 120,
                    "model_context_window": 200000,
                },
            },
        }),
    ]
    monkeypatch.setattr("refract.backends.agy.run_shell_command", lambda *a, **k: (l for l in agy_stdout))

    res = agy_sync(BackendParams(PROMPT="test", cd=tmp_path))
    assert res.outcome == "OK"
    assert res.telemetry is not None
    # Occupied context MUST remain derived provenance
    assert res.telemetry["context_used_tokens"]["quality"] == "derived"
    assert res.telemetry["context_used_tokens"]["source"] == "derived"
    # Capacity is reported
    assert res.telemetry["context_window_size"]["quality"] == "reported"




