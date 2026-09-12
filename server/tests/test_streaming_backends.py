"""Characterization fixtures and streaming normalization tests for backends."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from openmcp.backends.agy import AgyParams, _execute_once, _execute_sync as agy_sync
from openmcp.backends.claude import ClaudeParams, _execute_sync as claude_sync
from openmcp.backends.codex import CodexParams, _execute_sync as codex_sync
from openmcp.backends.pi import PiParams, _execute_sync as pi_sync


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
        "openmcp.backends.claude.run_shell_command",
        lambda *args, **kwargs: (line for line in CLAUDE_STREAM_JSON_FIXTURE),
    )

    params = ClaudeParams(
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
    assert started_evt["data"]["input"] == {"path": "/etc/shadow", "secret_arg": "pass123"}

    completed_evt = next(e for e in events if e["kind"] == "tool.completed")
    assert completed_evt["data"] == {"status": "completed"}
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
        "openmcp.backends.claude.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    params = ClaudeParams(PROMPT="inspect", cd=workspace, emitter=events.append)
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
        "openmcp.backends.claude.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    params = ClaudeParams(PROMPT="inspect", cd=workspace, emitter=events.append)
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
        "openmcp.backends.codex.run_shell_command",
        lambda *args, **kwargs: (line for line in CODEX_JSONL_FIXTURE),
    )

    params = CodexParams(
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
    assert started_evt["data"]["input"] == "cat /etc/passwd secret_key_789"

    completed_evt = next(e for e in events if e["kind"] == "tool.completed")
    assert completed_evt["data"]["status"] == "completed"
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
        "openmcp.backends.codex.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    params = CodexParams(PROMPT="inspect", cd=workspace, emitter=events.append)
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
        "openmcp.backends.pi.run_shell_command",
        lambda *args, **kwargs: (line for line in PI_JSON_FIXTURE),
    )

    params = PiParams(
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
    assert events[1]["entity_id"] == "tool-1"
    assert events[1]["data"]["input"] == {"pattern": "secret_pwd_999"}
    assert events[2]["data"]["status"] == "completed"
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
        "openmcp.backends.pi.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )

    params = PiParams(PROMPT="inspect", cd=workspace, emitter=events.append)
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
        "openmcp.backends.agy.run_shell_command",
        lambda *args, **kwargs: (line for line in AGY_STREAM_JSON_FIXTURE),
    )
    monkeypatch.setattr(
        "openmcp.backends.agy._agy_has_pending_tasks",
        lambda *args, **kwargs: False,
    )

    params = AgyParams(
        PROMPT="inspect",
        cd=workspace,
        emitter=emitter,
    )
    result = _execute_once(params)

    assert result.outcome == "OK"
    assert result.SESSION_ID == "12345678-1234-1234-1234-123456789abc"

    assert len(events) >= 1
    started_evt = next(e for e in events if e["kind"] == "tool.started")
    assert started_evt["data"]["tool"] == "execute_code"
    assert started_evt["data"]["input"] == {"script": "secret_token_val"}

    completed_evt = next(e for e in events if e["kind"] == "tool.completed")
    assert completed_evt["data"]["status"] == "success"
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
        "openmcp.backends.agy.run_shell_command",
        lambda *args, **kwargs: (line for line in stream_fixture),
    )
    monkeypatch.setattr(
        "openmcp.backends.agy._agy_has_pending_tasks",
        lambda *args, **kwargs: False,
    )

    params = AgyParams(PROMPT="inspect", cd=workspace, emitter=events.append)
    result = _execute_once(params)
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



def test_agy_continuations_unique_synthetic_entities(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/" + cmd)

    events: list[dict[str, Any]] = []

    def emitter(event: dict[str, Any]) -> None:
        events.append(event)

    call_count = 0

    def fake_run_shell(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return iter([
            "Created conversation 12345678-1234-1234-1234-123456789abc",
            json.dumps({
                "type": "assistant.text.delta",
                "text": f"Continuation {call_count}",
            }),
            f"Done {call_count}",
        ])

    monkeypatch.setattr("openmcp.backends.agy.run_shell_command", fake_run_shell)
    pending_checks = [True, False]
    monkeypatch.setattr(
        "openmcp.backends.agy._agy_has_pending_tasks",
        lambda *args, **kwargs: pending_checks.pop(0) if pending_checks else False,
    )

    params = AgyParams(
        PROMPT="inspect",
        cd=workspace,
        emitter=emitter,
    )
    result = agy_sync(params)

    assert result.outcome == "OK"
    deltas = [e for e in events if e.get("kind") == "assistant.text.delta"]
    assert len(deltas) == 2
    # Continuation events must have unique synthetic assistant entities
    assert deltas[0]["entity_id"] != deltas[1]["entity_id"]
    assert deltas[0]["entity_id"] == "msg-1"
    assert deltas[1]["entity_id"] == "msg-2"
