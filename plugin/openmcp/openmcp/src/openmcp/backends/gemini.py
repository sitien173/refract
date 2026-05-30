"""Transport-agnostic Gemini backend extracted from geminimcp."""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from . import BackendResult
from openmcp.logging_setup import get_logger

log = get_logger("gemini")


@dataclass(slots=True)
class GeminiParams:
    PROMPT: str
    cd: Path
    SESSION_ID: str = ""
    model: str = ""


def run_shell_command(cmd: list[str], cwd: str | None = None) -> Generator[str, None, None]:
    """Execute Gemini CLI and stream stdout lines until the turn completes."""
    popen_cmd = cmd.copy()
    gemini_path = shutil.which("gemini") or cmd[0]
    popen_cmd[0] = gemini_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
    )

    output_queue: queue.Queue[str | None] = queue.Queue()
    graceful_shutdown_delay = 0.3

    def is_turn_completed(line: str) -> bool:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            return False
        return data.get("type") in {"turn.completed", "result"}

    def read_output() -> None:
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                stripped = line.rstrip("\r\n")
                output_queue.put(stripped)
                if is_turn_completed(stripped):
                    time.sleep(graceful_shutdown_delay)
                    process.terminate()
                    break
            process.stdout.close()
        output_queue.put(None)

    thread = threading.Thread(target=read_output, daemon=True)
    thread.start()

    while True:
        try:
            line = output_queue.get(timeout=0.5)
            if line is None:
                break
            yield line
        except queue.Empty:
            if process.poll() is not None and not thread.is_alive():
                break

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise
    finally:
        thread.join(timeout=5)

    while not output_queue.empty():
        try:
            line = output_queue.get_nowait()
            if line is not None:
                yield line
        except queue.Empty:
            break


_FATAL_TOKENS = (
    "invalid model",
    "unknown model",
    "authentication",
    "unauthorized",
    "forbidden",
    "api key",
    "not logged in",
    "login required",
)

_RETRYABLE_TOKENS = (
    "rate limit",
    " 429",
    " 500",
    " 502",
    " 503",
    " 504",
    "timeout",
    "timed out",
)


def _message_content(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _classify(*, agent_messages: str, session_id: str, error_text: str) -> BackendResult:
    combined = f"{error_text}\n{agent_messages}".lower()
    # Strip node_tls_reject_unauthorized to avoid false-positive auth failure classification
    combined = combined.replace("node_tls_reject_unauthorized", "")

    if any(token in combined for token in _FATAL_TOKENS):
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=session_id,
            agent_messages=agent_messages,
            error=error_text or "fatal backend/auth failure",
            error_class="fatal_backend",
        )

    if any(token in combined for token in _RETRYABLE_TOKENS):
        return BackendResult(
            outcome="RETRYABLE",
            SESSION_ID=session_id,
            agent_messages=agent_messages,
            error=error_text or "retryable backend failure",
            error_class="retryable_backend",
        )

    if not agent_messages.strip():
        extra = f" {error_text}" if error_text else ""
        return BackendResult(
            outcome="RETRYABLE",
            SESSION_ID=session_id,
            agent_messages=agent_messages,
            error=f"Failed to get output from the gemini session.{extra}".strip(),
            error_class="no_agent_messages",
        )

    if not session_id:
        return BackendResult(
            outcome="RETRYABLE",
            SESSION_ID="",
            agent_messages=agent_messages,
            error=error_text or "missing SESSION_ID",
            error_class="missing_session_id",
        )

    return BackendResult(
        outcome="OK",
        SESSION_ID=session_id,
        agent_messages=agent_messages,
        error=error_text,
        error_class="",
    )


async def execute(params: GeminiParams) -> BackendResult:
    """Execute a Gemini CLI session and return normalized backend result."""
    cd = Path(params.cd)
    if not cd.exists():
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error=f"The workspace root directory `{cd.absolute().as_posix()}` does not exist. Please check the path and try again.",
            error_class="bad_cd",
        )

    gemini_binary = shutil.which("gemini")
    if gemini_binary is None:
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error="The `gemini` CLI was not found on PATH. Please install Gemini CLI and ensure `gemini` is available.",
            error_class="missing_cli",
        )

    cmd = [
        "gemini",
        "--prompt",
        params.PROMPT,
        "--output-format",
        "stream-json",
        "--approval-mode=yolo",
        "--allowed-mcp-server-names=[*]",
        "--skip-trust",
    ]
    if params.model:
        cmd.extend(["--model", params.model])
    if params.SESSION_ID:
        cmd.extend(["--resume", params.SESSION_ID])

    log.info(
        "gemini.execute start cwd=%s model=%s session_id=%s prompt_len=%d",
        cd.absolute().as_posix(),
        params.model,
        params.SESSION_ID or "<new>",
        len(params.PROMPT),
    )
    log.debug("gemini cmd: %s", cmd)

    agent_messages = ""
    error_text = ""
    session_id = ""

    try:
        for line in run_shell_command(cmd, cwd=cd.absolute().as_posix()):
            stripped = line.strip()
            try:
                line_dict = json.loads(stripped)
            except json.JSONDecodeError:
                if stripped:
                    log.debug("gemini: skipping non-JSON stdout line: %s", stripped)
                continue

            item_type = line_dict.get("type", "")
            item_role = line_dict.get("role", "")
            if item_type == "init" and line_dict.get("session_id"):
                session_id = str(line_dict.get("session_id"))
            if item_type == "message" and item_role == "assistant":
                content = _message_content(line_dict.get("content", ""))
                agent_messages += content
            if item_type == "result":
                break
    except subprocess.TimeoutExpired as exc:
        log.exception("gemini subprocess timeout")
        error_text += f"\n\n[timeout] {exc}"
    except Exception as exc:  # noqa: BLE001
        log.exception("gemini: unexpected error during stream")
        error_text += f"\n\n[unexpected] {exc}"

    if not session_id:
        session_id = params.SESSION_ID
    if session_id:
        log.info("gemini: resolved session id: %s", session_id)
    agent_messages = agent_messages.rstrip()

    result = _classify(
        agent_messages=agent_messages,
        session_id=session_id,
        error_text=error_text.strip(),
    )
    log.info(
        "gemini.execute done outcome=%s session_id=%s error_class=%s msg_len=%d",
        result.outcome,
        result.SESSION_ID or "",
        result.error_class,
        len(result.agent_messages),
    )
    if result.error:
        log.warning("gemini.execute error_text: %s", result.error[:500])
    return result


__all__ = ["GeminiParams", "execute"]
