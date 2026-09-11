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

    serialized = json.dumps(events)
    # Planted secrets must not be in serialized events
    assert "secret_token_123" not in serialized
    assert "secret_reasoning_456" not in serialized
    assert "secret_arg" not in serialized
    assert "pass123" not in serialized


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
    serialized = json.dumps(events)
    # Exclude secrets & tool arguments/outputs
    assert "secret_key_789" not in serialized
    assert "secret_hash_value" not in serialized
    assert "secret_chain_of_thought" not in serialized


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
    assert events[2]["data"]["status"] == "completed"
    assert events[2]["entity_id"] == "tool-1"

    serialized = json.dumps(events)
    assert "secret_pwd_999" not in serialized
    # Thinking deltas must be excluded
    assert "secret_thinking_pwd" not in serialized


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
    serialized = json.dumps(events)
    assert "secret_token_val" not in serialized
    assert "secret_stdout_result" not in serialized
    # Fixture secrets must NOT leak into returned agent_messages
    assert "secret_token_val" not in result.agent_messages
    assert "secret_stdout_result" not in result.agent_messages
    # Diagnostic non-JSON output must be ignored when structured mode is detected
    assert "secret_diagnostic_marker" not in result.agent_messages
    # Arbitrary object fields must never be str() converted into agent_messages
    assert "secret_object_val" not in result.agent_messages
    assert "arbitrary_secret_obj" not in result.agent_messages
    assert result.agent_messages == "Running antigravity analysis.\n\nAntigravity finished successfully."



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
