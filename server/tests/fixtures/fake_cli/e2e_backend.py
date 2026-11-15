from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Markers the coding_agent_cli drivers probe in --help. agy prints none, so the fake agy is a non-streaming target.
HELP_BY_BACKEND = {
    "claude": "--output-format stream-json --include-partial-messages",
    "pi": "--mode --session --thinking",
    "codex": "--json --output-last-message",
    "agy": "",
}

if "--help" in sys.argv:
    print(HELP_BY_BACKEND.get(os.environ.get("FAKE_CLI_NAME", ""), ""))
    raise SystemExit(0)

if "--print" in sys.argv:
    prompt = sys.argv[sys.argv.index("--print") + 1]
else:
    prompt = sys.stdin.read()


def emit(event: dict[str, object]) -> None:
    print(json.dumps(event), flush=True)


def _extract_mode(text: str) -> str:
    match = re.search(r"E2E_MODE=([a-zA-Z0-9_]+)", text)
    return match.group(1) if match else ""


def _next_attempt_count(text: str) -> int:
    state_dir = os.environ.get("E2E_STATE_DIR")
    if not state_dir:
        return 1
    key_match = re.search(r"E2E_KEY=([a-zA-Z0-9_.-]+)", text)
    key = key_match.group(1) if key_match else hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    counter_path = Path(state_dir) / f"{key}.count"
    counter_path.parent.mkdir(parents=True, exist_ok=True)
    current = int(counter_path.read_text(encoding="utf-8")) if counter_path.exists() else 0
    current += 1
    counter_path.write_text(str(current), encoding="utf-8")
    return current


def _write_ready_file(text: str) -> None:
    env_file = os.environ.get("E2E_READY_FILE")
    if env_file:
        path = Path(env_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ready\n", encoding="utf-8")
        return

    ready_dir = os.environ.get("E2E_READY_DIR")
    name_match = re.search(r"E2E_READY_NAME=([a-zA-Z0-9_.-]+)", text)
    if ready_dir and name_match:
        path = Path(ready_dir) / name_match.group(1)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ready\n", encoding="utf-8")
        return

    quoted_match = re.search(r'E2E_READY_FILE="([^"]+)"', text)
    match = quoted_match or re.search(r"E2E_READY_FILE=(\S+)", text)
    if match:
        path = Path(match.group(1))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("ready\n", encoding="utf-8")


def _write_log_file(lines: list[str]) -> None:
    if "--log-file" in sys.argv:
        log_path = Path(sys.argv[sys.argv.index("--log-file") + 1])
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_ask(text: str) -> str:
    match = re.search(r"E2E_ASK:\s*(.+)", text)
    question = match.group(1).strip() if match else "Should the e2e test continue?"
    return subprocess.run(
        ["refract", "ask", question],
        check=True,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    ).stdout.strip()


def _fail(diagnostic: str) -> None:
    sys.stderr.write(diagnostic + "\n")
    sys.stderr.flush()
    _write_log_file([diagnostic])
    raise SystemExit(1)


_write_ready_file(prompt)
mode = _extract_mode(prompt)

if mode == "block":
    emit({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Waiting for cancellation"}})
    while True:
        time.sleep(0.2)

if mode == "context_overflow":
    _fail("context_length_exceeded")

if mode == "transient":
    _fail("rate_limit")

if mode == "fail_once_overflow":
    if _next_attempt_count(prompt) == 1:
        _fail("context_length_exceeded")
    output = "Recovered after overflow"
elif mode == "fail_once_transient":
    if _next_attempt_count(prompt) == 1:
        _fail("rate_limit")
    output = "Recovered after transient"
elif mode == "tool_started":
    emit(
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "tu_1", "name": "read_file", "input": {"path": "README.md"}},
        }
    )
    output = "Tool started completed"
elif mode == "tool_then_fail_transient":
    emit(
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "tu_1", "name": "read_file", "input": {"path": "README.md"}},
        }
    )
    _fail("rate_limit")
elif mode == "ask":
    output = _run_ask(prompt)
elif mode == "ask_then_fail_transient":
    _run_ask(prompt)
    _fail("rate_limit")
elif mode == "long":
    output = "X" * 112640
elif mode == "codex_fail_once_transient":
    attempt = _next_attempt_count(prompt)
    if attempt == 1:
        events = [
            {"type": "thread.started", "thread_id": "00000000-0000-0000-0000-000000000001"},
            {"type": "turn.started"},
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 1111,
                    "cached_input_tokens": 33,
                    "cache_write_input_tokens": 44,
                    "output_tokens": 22,
                    "reasoning_output_tokens": 5,
                },
            },
        ]
        for event in events:
            emit(event)
        _fail("rate_limit")
    events = [
        {"type": "thread.started", "thread_id": "00000000-0000-0000-0000-000000000002"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_2", "type": "agent_message", "text": "Attempt 2 reply"}},
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 5555,
                "cached_input_tokens": 77,
                "cache_write_input_tokens": 88,
                "output_tokens": 66,
                "reasoning_output_tokens": 9,
            },
        },
    ]
    for event in events:
        emit(event)
    if "-o" in sys.argv:
        out_path = Path(sys.argv[sys.argv.index("-o") + 1])
        out_path.write_text("Codex attempt 2 completed", encoding="utf-8")
    raise SystemExit(0)
elif mode == "codex" or "-o" in sys.argv:
    events = [
        {"type": "thread.started", "thread_id": "00000000-0000-0000-0000-000000000001"},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message", "text": "Turn 1 reply"}},
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 10000,
                "cached_input_tokens": 2000,
                "cache_write_input_tokens": 500,
                "output_tokens": 20,
                "reasoning_output_tokens": 10,
            },
        },
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "item_2", "type": "agent_message", "text": "Turn 2 reply"}},
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 12000,
                "cached_input_tokens": 8000,
                "cache_write_input_tokens": 300,
                "output_tokens": 30,
                "reasoning_output_tokens": 15,
            },
        },
    ]
    for event in events:
        emit(event)
    if "-o" in sys.argv:
        out_path = Path(sys.argv[sys.argv.index("-o") + 1])
        out_path.write_text("Codex completed", encoding="utf-8")
    raise SystemExit(0)
else:
    output = "E2E backend completed"

if "--log-file" in sys.argv:
    _write_log_file([output])
    raise SystemExit(0)

emit({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": output}})
emit({"type": "result", "subtype": "success", "result": output, "session_id": "e2e-session"})
