"""Transport-agnostic agy backend extracted from agymcp."""

from __future__ import annotations

import contextlib
import json
import os
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

from . import BackendResult, classify_backend_output
from ._shell import stream_shell_command_lines
from openmcp.logging_setup import get_logger

log = get_logger("agy")

_SETTINGS_PATH = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
_BRAIN_PATH = Path.home() / ".gemini" / "antigravity-cli" / "brain"
_CONTINUE_PROMPT = "Continue your work. Complete any remaining `[ ]` task items."
_AGY_MAX_CONTINUATIONS = 3
_UNCHECKED_RE = re.compile(r"^\s*-\s*`?\[\s\]`?\s", re.MULTILINE)
_settings_lock = threading.Lock()
@dataclass(slots=True)
class AgyParams:
    PROMPT: str
    cd: Path
    SESSION_ID: str = ""
    model: str = ""
    timeout_s: int = 0


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


def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON via temp file + os.replace so we never leave a half-written file."""
    serialized = json.dumps(data, indent=2, ensure_ascii=False)
    tmp_path = path.with_suffix(path.suffix + ".openmcp.tmp")
    tmp_path.write_text(serialized, encoding="utf-8")
    os.replace(tmp_path, path)


@contextlib.contextmanager
def _patch_model(model: str):
    """Temporarily override the model in agy's settings.json, then restore.

    Preserves the original file byte-for-byte on restore (so a missing
    "model" key isn't written back as ``"model": null``). Uses atomic
    file replacement and is reentrancy-safe via ``_settings_lock``.
    """
    if not model:
        yield
        return

    resolved_model_name = _resolve_agy_model_setting(model)
    if not resolved_model_name:
        yield
        return

    with _settings_lock:
        if _SETTINGS_PATH.exists():
            original_bytes = _SETTINGS_PATH.read_bytes()
            try:
                settings = json.loads(original_bytes.decode("utf-8"))
                if not isinstance(settings, dict):
                    settings = {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                log.warning("agy: settings.json is invalid; skipping model patch")
                yield
                return
        else:
            original_bytes = None
            settings = {}

        patched = dict(settings)
        patched["model"] = resolved_model_name
        try:
            _atomic_write_json(_SETTINGS_PATH, patched)
        except OSError as exc:
            log.warning("agy: could not write settings.json model patch: %s", exc)
            yield
            return

        try:
            yield
        finally:
            try:
                if original_bytes is None:
                    try:
                        _SETTINGS_PATH.unlink()
                    except FileNotFoundError:
                        pass
                else:
                    tmp_path = _SETTINGS_PATH.with_suffix(_SETTINGS_PATH.suffix + ".openmcp.tmp")
                    tmp_path.write_bytes(original_bytes)
                    os.replace(tmp_path, _SETTINGS_PATH)
            except OSError as exc:
                log.error("agy: failed to restore settings.json after model patch: %s", exc)


_UUID_PATTERN = r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
_CONVERSATION_ID_RE = re.compile(rf"(?:Created|Streaming) conversation {_UUID_PATTERN}")


def run_shell_command(
    cmd: list[str],
    cwd: str | None = None,
    timeout_s: int = 0,
) -> Generator[str, None, None]:
    """Execute a command and stream its output line-by-line (non-Windows / fallback)."""
    yield from stream_shell_command_lines(
        cmd,
        executable_name="agy",
        cwd=cwd,
        timeout_s=timeout_s,
        line_transform=lambda line: line.strip(),
        terminate_wait_s=10,
        suppress_stdout_close_errors=True,
    )


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
    result = classify_backend_output(
        backend_name="agy",
        agent_messages=agent_messages,
        session_id=session_id,
        error_text=error_text,
    )
    # Preserve historical "no_agent_messages" wording for back-compat with
    # tests that read the error string verbatim.
    if result.error_class == "no_agent_messages":
        extra = f" {error_text.strip()}" if error_text.strip() else ""
        result.error = f"Failed to get `agent_messages` from the agy session.{extra}".strip()
    return result


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
    execution_error = False
    agent_messages = ""

    log.info(
        "agy.execute start cwd=%s model=%s session_id=%s prompt_len=%d",
        cwd,
        params.model,
        params.SESSION_ID or "<new>",
        len(params.PROMPT),
    )

    try:
        with _patch_model(params.model):
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
                for _ in run_shell_command(cmd, cwd=cwd, timeout_s=params.timeout_s):
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
        log.warning("agy subprocess timeout after %ss", params.timeout_s)
        error_text = f"timeout: {exc}"
    except Exception as exc:  # noqa: BLE001
        log.exception("agy: unexpected error during run")
        error_text = str(exc)
        execution_error = True

    match = _CONVERSATION_ID_RE.search(agent_messages)
    extracted_session_id = match.group(1) if match else params.SESSION_ID
    if extracted_session_id:
        log.info("agy: resolved session id: %s", extracted_session_id)
    else:
        log.warning("agy: no session id found in log or params")

    if execution_error:
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=extracted_session_id,
            agent_messages=agent_messages,
            error=error_text or "agy execution failed",
            error_class="execution_error",
        )

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
    if result.outcome == "FATAL" and result.error_class == "no_agent_messages" and params.model:
        log.warning(
            "agy: model override %r produced no output; trying once with agy's configured default model",
            params.model,
        )
        return await _execute_once(
            AgyParams(
                PROMPT=params.PROMPT,
                cd=cd,
                SESSION_ID=result.SESSION_ID or params.SESSION_ID,
                model="",
                timeout_s=params.timeout_s,
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
                timeout_s=params.timeout_s,
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
