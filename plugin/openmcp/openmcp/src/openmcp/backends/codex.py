"""Transport-agnostic codex backend (plain-text stdout mode)."""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

from . import BackendResult
from openmcp.logging_setup import get_logger

log = get_logger("codex")

_DISABLED_PLUGIN = "superpowers-ccg@superpowers-ccg-marketplace"


def _disabled_plugin_override(plugin_name: str) -> str:
    plugin_name = plugin_name.strip()
    escaped_name = plugin_name.replace("\\", "\\\\").replace('"', '\\"')
    return f'plugins."{escaped_name}".enabled=false' if escaped_name else ""


@dataclass(slots=True)
class CodexParams:
    PROMPT: str
    cd: Path
    SESSION_ID: str = ""
    model: str = ""
    profile: str = ""
    reasoning_effort: str = ""


def _windows_escape(prompt: str) -> str:
    result = prompt.replace("\\", "\\\\")
    result = result.replace('"', '\\"')
    result = result.replace("\n", "\\n")
    result = result.replace("\r", "\\r")
    result = result.replace("\t", "\\t")
    result = result.replace("\b", "\\b")
    result = result.replace("\f", "\\f")
    result = result.replace("'", "\\'")
    return result


def run_shell_command(cmd: list[str], cwd: str | None = None) -> Generator[str, None, None]:
    """Execute a command and stream its stdout lines until EOF."""
    popen_cmd = cmd.copy()
    codex_path = shutil.which("codex") or cmd[0]
    popen_cmd[0] = codex_path

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

    def read_output() -> None:
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                output_queue.put(line.rstrip("\r\n"))
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
        process.wait(timeout=10)
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
    "invalid profile",
    "unknown profile",
    "profile not found",
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
    " 5xx",
    " 500",
    " 502",
    " 503",
    " 504",
    "timeout",
    "timed out",
)

_RECONNECT_RE = re.compile(r"^\s*Reconnecting\.\.\.\s+\d+/\d+", re.MULTILINE)
_SESSION_ID_STDOUT_RE = re.compile(
    r"^\s*session id:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

def _extract_session_id_from_stdout(text: str) -> str:
    if not text:
        return ""
    match = _SESSION_ID_STDOUT_RE.search(text)
    return match.group(1) if match else ""


def _same_path(left: str, right: Path) -> bool:
    try:
        return Path(left).resolve() == right.resolve()
    except OSError:
        return Path(left).as_posix().lower() == right.as_posix().lower()


def _extract_session_id_from_latest_session(cwd: Path, prompt: str, started_at: float) -> str:
    sessions_dir = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions"
    if not sessions_dir.exists():
        return ""

    prompt_hint = prompt.strip().splitlines()[0][:80] if prompt.strip() else ""

    try:
        session_files = sorted(
            sessions_dir.rglob("*.jsonl"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return ""

    cwd_match_without_prompt = ""
    for session_path in session_files[:50]:
        try:
            stat = session_path.stat()
        except OSError:
            continue
        if stat.st_mtime < started_at - 30:
            break

        try:
            with session_path.open(encoding="utf-8", errors="ignore") as handle:
                first_line = handle.readline()
                head = handle.read(65536)
        except OSError:
            continue

        meta = {}
        for line in (first_line, *head.splitlines()[:10]):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                continue
            if parsed.get("type") == "session_meta":
                meta = parsed
                break
        if not meta:
            continue

        payload = meta.get("payload", {})
        if not isinstance(payload, dict):
            continue
        session_id = payload.get("id", "")
        session_cwd = payload.get("cwd", "")
        if (
            not session_id
            or not _SESSION_ID_RE.fullmatch(session_id)
            or not session_cwd
            or not _same_path(session_cwd, cwd)
        ):
            continue
        if prompt_hint and prompt_hint not in head:
            if not cwd_match_without_prompt:
                cwd_match_without_prompt = session_id
            continue
        return session_id

    return cwd_match_without_prompt


def _resolve_session_id(
    *,
    parsed_session_id: str,
    last_message: str,
    stdout_text: str,
    cwd: Path,
    prompt: str,
    started_at: float,
    fallback_session_id: str,
) -> tuple[str, str]:
    candidates: tuple[tuple[str, str], ...] = (
        ("stdout-jsonl:thread.started", parsed_session_id.strip()),
        ("last-message:session-id-line", _extract_session_id_from_stdout(last_message)),
        ("stdout:session-id-line", _extract_session_id_from_stdout(stdout_text)),
        ("codex-jsonl", _extract_session_id_from_latest_session(cwd, prompt, started_at)),
        ("params:SESSION_ID", fallback_session_id.strip()),
    )
    for source, value in candidates:
        if value:
            return value, source
    return "", ""


def _classify(*, agent_messages: str, session_id: str, error_text: str) -> BackendResult:
    combined = f"{error_text}\n{agent_messages}".lower()

    if any(token in combined for token in _FATAL_TOKENS):
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=session_id,
            agent_messages=agent_messages,
            error=error_text or "fatal backend/auth failure",
            error_class="fatal_backend",
        )

    if _RECONNECT_RE.search(agent_messages) or any(token in combined for token in _RETRYABLE_TOKENS):
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
            error=f"Failed to get output from the codex session.{extra}".strip(),
            error_class="no_agent_messages",
        )

    if not session_id:
        return BackendResult(
            outcome="OK",
            SESSION_ID="",
            agent_messages=agent_messages,
            error="warning: no SESSION_ID",
            error_class="warning",
        )

    return BackendResult(
        outcome="OK",
        SESSION_ID=session_id,
        agent_messages=agent_messages,
        error=error_text,
        error_class="",
    )


async def execute(params: CodexParams) -> BackendResult:
    """Execute a Codex CLI session and return normalized backend result."""
    cd = Path(params.cd)
    if not cd.exists():
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error=f"The workspace root directory `{cd.absolute().as_posix()}` does not exist. Please check the path and try again.",
            error_class="bad_cd",
        )

    codex_binary = shutil.which("codex")
    if codex_binary is None:
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error="The `codex` CLI was not found on PATH. Please install Codex CLI and ensure `codex` is available.",
            error_class="missing_cli",
        )

    with tempfile.NamedTemporaryFile(
        prefix="openmcp-codex-", suffix=".txt", delete=False
    ) as tmp:
        last_message_path = Path(tmp.name)

    cmd = [
        "codex",
        "exec",
        "--cd",
        str(cd),
        "--yolo",
        "--skip-git-repo-check",
        "--json",
        "-o",
        str(last_message_path),
    ]

    if params.model:
        cmd.extend(["--model", params.model])

    if params.profile:
        cmd.extend(["--profile", params.profile])

    if params.reasoning_effort:
        cmd.extend(["-c", f"model_reasoning_effort={params.reasoning_effort}"])

    cmd.extend(["-c", _disabled_plugin_override(_DISABLED_PLUGIN)])

    if params.SESSION_ID:
        cmd.extend(["resume", str(params.SESSION_ID)])

    prompt = _windows_escape(params.PROMPT) if os.name == "nt" else params.PROMPT
    cmd += ["--", prompt]

    log.info(
        "codex.execute start cwd=%s model=%s profile=%s reasoning_effort=%s session_id=%s prompt_len=%d",
        cd.absolute().as_posix(),
        params.model,
        params.profile,
        params.reasoning_effort or "<off>",
        params.SESSION_ID or "<new>",
        len(params.PROMPT),
    )
    log.debug("codex cmd: %s", cmd)

    stdout_lines: list[str] = []
    err_message = ""
    started_at = time.time()

    try:
        for line in run_shell_command(cmd, cwd=cd.absolute().as_posix()):
            stdout_lines.append(line)
    except subprocess.TimeoutExpired as exc:
        log.exception("codex subprocess timeout")
        err_message += f"\n\n[timeout] {exc}"
    except Exception as exc:  # noqa: BLE001
        log.exception("codex: unexpected error during stream")
        err_message += f"\n\n[unexpected] {exc}"

    stdout_text = "\n".join(stdout_lines)
    parsed_session_id = ""
    parsed_agent_messages = ""
    for line in stdout_lines:
        stripped = line.strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            if stripped:
                log.debug("codex: skipping non-JSON stdout line: %s", stripped)
            continue

        item_type = parsed.get("type", "")
        if item_type == "thread.started" and parsed.get("thread_id"):
            parsed_session_id = str(parsed.get("thread_id"))
            continue
        if item_type != "item.completed":
            continue
        item = parsed.get("item", {})
        if not isinstance(item, dict):
            continue
        if item.get("type") == "agent_message" and item.get("text"):
            parsed_agent_messages += str(item.get("text"))

    try:
        last_message = last_message_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("codex: could not read --output-last-message file %s: %s", last_message_path, exc)
        last_message = ""
    finally:
        try:
            last_message_path.unlink()
        except OSError:
            pass

    last_message_text = last_message.strip()
    parsed_agent_messages = parsed_agent_messages.strip()
    if last_message_text:
        agent_messages = last_message_text
    elif parsed_agent_messages:
        agent_messages = parsed_agent_messages
    else:
        agent_messages = stdout_text
    log.debug(
        "codex: last_message_len=%d parsed_msg_len=%d stdout_len=%d using=%s",
        len(last_message), len(parsed_agent_messages), len(stdout_text),
        "last_message_file" if last_message_text else ("stdout_jsonl_fallback" if parsed_agent_messages else "stdout_fallback"),
    )

    session_id, session_id_source = _resolve_session_id(
        parsed_session_id=parsed_session_id,
        last_message=last_message,
        stdout_text=stdout_text,
        cwd=cd,
        prompt=params.PROMPT,
        started_at=started_at,
        fallback_session_id=params.SESSION_ID,
    )

    if session_id_source:
        log.info("codex: resolved session id via %s", session_id_source)
    else:
        log.warning(
            "codex: no session id found from stdout/session-file/params "
            "(last_msg_len=%d stdout_len=%d).",
            len(last_message), len(stdout_text),
        )

    classify_text = agent_messages if agent_messages else stdout_text
    result = _classify(
        agent_messages=classify_text,
        session_id=session_id,
        error_text=err_message.strip() or (stdout_text if not last_message.strip() else ""),
    )
    result.agent_messages = agent_messages
    log.info(
        "codex.execute done outcome=%s session_id=%s error_class=%s msg_len=%d",
        result.outcome,
        result.SESSION_ID or "",
        result.error_class,
        len(result.agent_messages),
    )
    if result.error:
        log.warning("codex.execute error_text: %s", result.error[:500])
    return result


__all__ = ["CodexParams", "execute"]
