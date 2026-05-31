"""Transport-agnostic agy backend extracted from agymcp."""

from __future__ import annotations

import contextlib
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from . import BackendResult
from openmcp.logging_setup import get_logger

log = get_logger("agy")

_SETTINGS_PATH = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
_CONVERSATIONS_PATH = Path.home() / ".gemini" / "antigravity-cli" / "conversations"
_BRAIN_PATH = Path.home() / ".gemini" / "antigravity-cli" / "brain"
_CONTINUE_PROMPT = "Continue your work. Complete any remaining `[ ]` task items."
_AGY_MAX_CONTINUATIONS = 3
_UNCHECKED_RE = re.compile(r"^\s*-\s*`?\[\s\]`?\s", re.MULTILINE)
_settings_lock = threading.Lock()
_DISABLED_PLUGIN_NAME = os.environ.get("OPENMCP_AGY_DISABLE_PLUGIN", "superpowers-ccg").strip()


@dataclass(slots=True)
class AgyParams:
    PROMPT: str
    cd: Path
    SESSION_ID: str = ""
    model: str = ""


_VALID_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")

_AGY_GEMINI_MODEL_NAME_BY_ID = {
    "gemini-3.5-flash": "Gemini 3.5 Flash (Medium)",
    "gemini-3.5-flash-high": "Gemini 3.5 Flash (High)",
    "gemini-3.5-flash-low": "Gemini 3.5 Flash (Low)",
    "gemini-3.1-pro-low": "Gemini 3.1 Pro (Low)",
    "gemini-3.1-pro-high": "Gemini 3.1 Pro (High)",
}
_AGY_SUPPORTED_MODEL_NAMES = frozenset(_AGY_GEMINI_MODEL_NAME_BY_ID.values())


def _is_valid_agy_model_id(model: str) -> bool:
    """Reject display names ('Gemini 3.5 Flash (High)') and accept model ids."""
    return bool(model) and bool(_VALID_MODEL_ID_RE.match(model.strip()))


def _resolve_agy_model_setting(model: str) -> str:
    """Resolve incoming model value to an Antigravity settings display name."""
    normalized = model.strip()
    if not normalized:
        return ""

    mapped_name = _AGY_GEMINI_MODEL_NAME_BY_ID.get(normalized.lower())
    if mapped_name:
        return mapped_name

    if normalized in _AGY_SUPPORTED_MODEL_NAMES:
        return normalized

    if _is_valid_agy_model_id(normalized):
        log.warning(
            "agy: unsupported Gemini model id %r; using agy's configured default instead",
            model,
        )
        return ""

    log.warning(
        "agy: unsupported model name %r; using agy's configured default instead",
        model,
    )
    return ""


@contextlib.contextmanager
def _patch_model(model: str):
    """Temporarily override the model in agy's settings.json, then restore."""
    if not model:
        yield
        return

    resolved_model_name = _resolve_agy_model_setting(model)
    if not resolved_model_name:
        yield
        return

    with _settings_lock:
        original_text = _SETTINGS_PATH.read_text(encoding="utf-8") if _SETTINGS_PATH.exists() else "{}"
        settings = json.loads(original_text)
        original_model = settings.get("model")
        settings["model"] = resolved_model_name
        _SETTINGS_PATH.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            yield
        finally:
            settings["model"] = original_model
            _SETTINGS_PATH.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


_ANSI_ESCAPE = re.compile(
    r"\x1b\[[\?0-9;]*[a-zA-Z]"
    r"|\x1b[()][AB012]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\r"
)
_UUID_PATTERN = r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
_SESSION_ID_PATTERNS = (
    re.compile(rf"--conversation[= ]{_UUID_PATTERN}", re.IGNORECASE),
    re.compile(rf"\bconversation(?:Id|_id)?\b[\"'\s:=]+{_UUID_PATTERN}", re.IGNORECASE),
    re.compile(rf"\bsession(?:Id|_id)?\b[\"'\s:=]+{_UUID_PATTERN}", re.IGNORECASE),
    re.compile(rf"\bthread(?:Id|_id)?\b[\"'\s:=]+{_UUID_PATTERN}", re.IGNORECASE),
)


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _run_plugin_command(command: str, plugin_name: str) -> None:
    subprocess.run(
        ["agy", "plugin", command, plugin_name],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


@contextlib.contextmanager
def _temporary_disabled_plugin(plugin_name: str):
    if not plugin_name:
        yield
        return

    disabled = False
    try:
        _run_plugin_command("disable", plugin_name)
        disabled = True
    except (subprocess.SubprocessError, OSError) as exc:
        log.warning("agy: failed to disable plugin %r before run: %s", plugin_name, exc)

    try:
        yield
    finally:
        if not disabled:
            return
        try:
            _run_plugin_command("enable", plugin_name)
        except (subprocess.SubprocessError, OSError) as exc:
            log.warning("agy: failed to re-enable plugin %r after run: %s", plugin_name, exc)


def run_shell_command(cmd: list[str], cwd: str | None = None) -> Generator[str, None, None]:
    """Execute a command and stream its output line-by-line (non-Windows / fallback)."""
    popen_cmd = cmd.copy()
    agy_path = shutil.which("agy") or cmd[0]
    popen_cmd[0] = agy_path

    process = subprocess.Popen(
        popen_cmd,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding="utf-8",
        cwd=cwd,
    )

    output_queue: queue.Queue[str | None] = queue.Queue()
    GRACEFUL_SHUTDOWN_DELAY = 0.5

    def read_output() -> None:
        if process.stdout:
            for line in iter(process.stdout.readline, ""):
                output_queue.put(line.strip())
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
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        time.sleep(GRACEFUL_SHUTDOWN_DELAY)
    thread.join(timeout=20)

    while not output_queue.empty():
        try:
            line = output_queue.get_nowait()
            if line is not None:
                yield line
        except queue.Empty:
            break


def run_shell_command_pty(cmd: list[str], cwd: str | None = None) -> str:
    """Execute a command inside a Windows ConPTY and return captured output."""
    import winpty  # pywinpty

    agy_path = shutil.which(cmd[0]) or cmd[0]
    argv = [agy_path] + cmd[1:]

    proc = winpty.PtyProcess.spawn(argv, cwd=cwd)
    chunks: list[str] = []
    while proc.isalive():
        try:
            chunk = proc.read(4096)
            chunks.append(chunk)
        except EOFError:
            break
    return _strip_ansi("".join(chunks))


def _extract_session_id(text: str) -> str:
    for pattern in _SESSION_ID_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return ""


def _extract_session_id_from_history(workspace_path: Path, prompt_snippet: str = "") -> str:
    history_file = Path.home() / ".gemini" / "antigravity-cli" / "history.jsonl"
    if not history_file.exists():
        return ""

    resolved_workspace = str(workspace_path.resolve()).lower()
    snippet = prompt_snippet.strip()[:60].lower() if prompt_snippet else ""

    try:
        with history_file.open("r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                raw_workspace = entry.get("workspace", "")
                if not raw_workspace:
                    continue
                entry_workspace = str(Path(raw_workspace).resolve()).lower()
                
                if entry_workspace == resolved_workspace:
                    if snippet:
                        display_text = entry.get("display", "").lower()
                        if snippet in display_text:
                            return entry.get("conversationId", "")
                    else:
                        return entry.get("conversationId", "")
            except (json.JSONDecodeError, KeyError):
                continue
    except OSError:
        pass
    return ""


def _extract_session_id_from_pb_signature(workspace_path: Path) -> str:
    if not _CONVERSATIONS_PATH.exists():
        return ""

    workspace_bytes = str(workspace_path.resolve()).encode("utf-8", errors="ignore")

    try:
        pb_files = sorted(
            _CONVERSATIONS_PATH.glob("*.pb"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for pb_path in pb_files[:10]:
            try:
                content = pb_path.read_bytes()
                if workspace_bytes in content:
                    stem = pb_path.stem
                    if re.fullmatch(_UUID_PATTERN, stem, re.IGNORECASE):
                        return stem
            except OSError:
                continue
    except OSError:
        pass
    return ""



def _extract_session_id_from_recent_conversation_file(started_at: float) -> str:
    if not _CONVERSATIONS_PATH.exists():
        return ""

    try:
        conversation_files = sorted(
            _CONVERSATIONS_PATH.glob("*.pb"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return ""

    for conversation_path in conversation_files[:20]:
        try:
            stat = conversation_path.stat()
        except OSError:
            continue
        if stat.st_mtime < started_at - 30:
            break

        conversation_id = conversation_path.stem
        if re.fullmatch(_UUID_PATTERN, conversation_id, re.IGNORECASE):
            return conversation_id
    return ""


def _extract_session_id_from_latest_log() -> str:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return ""

    logs_dir = Path(appdata) / "Antigravity" / "logs"
    if not logs_dir.exists():
        return ""

    try:
        log_files = sorted(logs_dir.rglob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return ""

    if not log_files:
        return ""

    for log_path in log_files:
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        session_id = _extract_session_id(log_text)
        if session_id:
            return session_id
    return ""


def _agy_has_pending_tasks(session_id: str, started_at: float) -> bool:
    """True iff task.md was created/updated this turn AND still has `[ ]` items."""
    if not session_id:
        return False
    task_path = _BRAIN_PATH / session_id / "task.md"
    meta_path = _BRAIN_PATH / session_id / "task.md.metadata.json"
    if not task_path.exists():
        return False

    updated_at: float | None = None
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            iso = str(meta.get("updatedAt", "")).strip()
            if iso:
                normalized = iso
                if normalized.endswith("Z"):
                    normalized = f"{normalized[:-1]}+00:00"
                normalized = re.sub(
                    r"\.(\d{6})\d+(?=(?:[+-]\d{2}:\d{2})$)",
                    r".\1",
                    normalized,
                )
                dt = datetime.fromisoformat(normalized)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                updated_at = dt.timestamp()
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            updated_at = None
    if updated_at is None:
        try:
            updated_at = task_path.stat().st_mtime
        except OSError:
            return False
    if updated_at < started_at - 2:
        return False
    try:
        content = task_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return bool(_UNCHECKED_RE.search(content))


def _classify_output(agent_messages: str, session_id: str, error_text: str) -> BackendResult:
    full_error = error_text.strip()
    lower = f"{agent_messages}\n{full_error}".lower()
    # Strip node_tls_reject_unauthorized to avoid false-positive auth failure classification
    lower = lower.replace("node_tls_reject_unauthorized", "")

    if any(token in lower for token in ("invalid model", "unknown model", "not a valid model", "authentication", "unauthorized", "forbidden", "api key", "not logged")):
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=session_id,
            agent_messages=agent_messages,
            error=full_error or "fatal backend/auth failure",
            error_class="fatal_backend",
        )

    # Only treat soft retryable tokens as failure when we have no usable output.
    # The Antigravity CLI prints "Reconnecting..." benignly during normal
    # websocket reconnects, so matching it in a 5-minute successful run would
    # discard real work. Real retryable failures typically produce no output.
    if not agent_messages and any(
        token in lower
        for token in ("rate limit", "429", " 5xx", " 500", " 502", " 503", " 504", "timeout", "timed out")
    ):
        return BackendResult(
            outcome="RETRYABLE",
            SESSION_ID=session_id,
            agent_messages=agent_messages,
            error=full_error or "retryable backend failure",
            error_class="retryable_backend",
        )

    if not agent_messages:
        extra = f" {full_error}" if full_error else ""
        return BackendResult(
            outcome="RETRYABLE",
            SESSION_ID=session_id,
            agent_messages=agent_messages,
            error=f"Failed to get `agent_messages` from the agy session.{extra}".strip(),
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
        error=full_error,
        error_class="",
    )


async def _execute_once(params: AgyParams) -> BackendResult:
    """Execute one agy CLI session and return normalized backend result."""
    cd = Path(params.cd)
    if not cd.exists():
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error=f"The workspace root directory `{cd.absolute().as_posix()}` does not exist. Please check the path and try again.",
            error_class="bad_cd",
        )

    agy_binary = shutil.which("agy")
    if agy_binary is None:
        return BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error="The `agy` CLI was not found on PATH. Please install Antigravity CLI and ensure `agy` is available.",
            error_class="missing_cli",
        )

    cwd = cd.absolute().as_posix()
    error_text = ""
    agent_messages = ""
    started_at = time.time()

    log.info(
        "agy.execute start cwd=%s model=%s session_id=%s prompt_len=%d",
        cwd,
        params.model,
        params.SESSION_ID or "<new>",
        len(params.PROMPT),
    )

    try:
        with _temporary_disabled_plugin(_DISABLED_PLUGIN_NAME), _patch_model(params.model):
            if os.name == "nt":
                cmd = [
                    "agy", "--print", params.PROMPT,
                    "--dangerously-skip-permissions",
                    "--add-dir", cwd,
                ]
                if params.SESSION_ID:
                    cmd.extend(["--conversation", params.SESSION_ID])
                agent_messages = run_shell_command_pty(cmd, cwd=cwd)
            else:
                with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as tmp:
                    tmp_log_path = tmp.name
                try:
                    cmd = [
                        "agy", "--print", params.PROMPT,
                        "--dangerously-skip-permissions",
                        "--add-dir", cwd,
                        "--log-file", tmp_log_path,
                    ]
                    if params.SESSION_ID:
                        cmd.extend(["--conversation", params.SESSION_ID])
                    for _ in run_shell_command(cmd, cwd=cwd):
                        pass
                    try:
                        agent_messages = Path(tmp_log_path).read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        agent_messages = ""
                finally:
                    try:
                        os.unlink(tmp_log_path)
                    except OSError:
                        pass
    except subprocess.TimeoutExpired as exc:
        log.exception("agy subprocess timeout")
        error_text = f"timeout: {exc}"
    except Exception as exc:  # noqa: BLE001
        log.exception("agy: unexpected error during run")
        error_text = str(exc)

    extracted_session_id = (
        _extract_session_id(agent_messages)
        or _extract_session_id_from_history(cd, params.PROMPT)
        or _extract_session_id_from_pb_signature(cd)
        or _extract_session_id_from_recent_conversation_file(started_at)
        or _extract_session_id_from_latest_log()
        or params.SESSION_ID
    )
    if extracted_session_id:
        log.info("agy: extracted session id via fallback: %s", extracted_session_id)
    else:
        log.warning("agy: no session id extracted from output/history/pb/log/params")

    result = _classify_output(agent_messages, extracted_session_id, error_text)
    log.info(
        "agy.execute done outcome=%s session_id=%s error_class=%s msg_len=%d",
        result.outcome,
        result.SESSION_ID or "",
        result.error_class,
        len(result.agent_messages),
    )
    if result.error:
        log.warning("agy.execute error_text: %s", result.error[:500])
    if result.outcome == "RETRYABLE" and result.error_class == "no_agent_messages" and params.model:
        log.warning(
            "agy: model override %r produced no output; retrying once with agy's configured default model",
            params.model,
        )
        return await _execute_once(
            AgyParams(
                PROMPT=params.PROMPT,
                cd=cd,
                SESSION_ID=result.SESSION_ID or params.SESSION_ID,
                model="",
            )
        )
    return result


async def execute(params: AgyParams) -> BackendResult:
    """Execute an agy CLI session and continue while current-turn tasks remain pending."""
    outer_started_at = time.time()
    result = await _execute_once(params)
    if result.outcome != "OK" or not result.SESSION_ID:
        return result

    merged_messages = result.agent_messages
    session_id = result.SESSION_ID
    continuations = 0
    while continuations < _AGY_MAX_CONTINUATIONS and _agy_has_pending_tasks(session_id, outer_started_at):
        continuations += 1
        log.info("agy: task.md has pending [ ] items; continuation %d/%d", continuations, _AGY_MAX_CONTINUATIONS)
        continue_started_at = time.time()
        continuation = await _execute_once(
            AgyParams(
                PROMPT=_CONTINUE_PROMPT,
                cd=Path(params.cd),
                SESSION_ID=session_id,
                model="",
            )
        )
        if continuation.outcome != "OK":
            log.warning("agy: continuation %d returned outcome=%s; stopping loop", continuations, continuation.outcome)
            result.agent_messages = (merged_messages + "\n\n" + (continuation.agent_messages or "")).strip()
            result.error = continuation.error or result.error
            return result
        if continuation.SESSION_ID:
            session_id = continuation.SESSION_ID
        merged_messages = (merged_messages + "\n\n" + continuation.agent_messages).strip()
        outer_started_at = continue_started_at

    if continuations and _agy_has_pending_tasks(session_id, outer_started_at):
        log.warning("agy: pending [ ] items remain after %d continuations; returning partial", continuations)

    result.agent_messages = merged_messages
    result.SESSION_ID = session_id
    return result


__all__ = ["AgyParams", "execute"]
