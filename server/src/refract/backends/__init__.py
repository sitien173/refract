"""Backend interfaces for refract."""

import json
import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal


@dataclass(slots=True)
class BackendParams:
    PROMPT: str
    cd: Path
    SESSION_ID: str = ""
    args: tuple[str, ...] = ()
    timeout_s: int = 0
    cancel_event: threading.Event | None = None
    emitter: Callable[[dict[str, Any]], None] | None = None
    env: dict[str, str] | None = field(default=None, repr=False)



@dataclass(slots=True)
class BackendResult:
    outcome: Literal["OK", "FATAL"]
    SESSION_ID: str
    agent_messages: str
    error: str
    error_class: str
    usage: dict[str, int | str | None] = field(default_factory=dict)


USAGE_KEYS = ("model_name", "input_tokens", "output_tokens", "cached_input_tokens", "context_window_max", "context_window_used")


def _usage_value(value: Any) -> int | str | None:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    return value


def _usage_dict(**values: Any) -> dict[str, int | str | None]:
    result = {key: _usage_value(values.get(key)) for key in USAGE_KEYS}
    for key in USAGE_KEYS[1:]:
        value = result[key]
        if isinstance(value, str) or isinstance(value, bool):
            result[key] = None
    return result


_DEFAULT_FATAL_TOKENS = (
    "invalid model",
    "unknown model",
    "not a valid model",
    "authentication",
    "unauthorized",
    "forbidden",
    "api key",
    "not logged in",
    "not logged",
    "login required",
    "auth_unavailable",
)


def preflight(params: BackendParams, executable: str, product: str) -> tuple[Path, BackendResult | None]:
    """Resolve the workspace and report a missing workspace or CLI before launch."""
    cd = Path(params.cd).expanduser().absolute()
    if not cd.is_dir():
        return cd, BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error=f"The workspace root directory `{cd}` does not exist or is not a directory. Please check the path and try again.",
            error_class="bad_cd",
        )
    if shutil.which(executable) is None:
        return cd, BackendResult(
            outcome="FATAL",
            SESSION_ID="",
            agent_messages="",
            error=f"The `{executable}` CLI was not found on PATH. Please install {product} and ensure `{executable}` is available.",
            error_class="missing_cli",
        )
    return cd, None


def parse_json_object(line: str) -> dict[str, Any] | None:
    """Return the line's JSON object, or None for non-JSON or non-object lines."""
    try:
        value = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _normalize(text: str) -> str:
    return text.lower().replace("node_tls_reject_unauthorized", "")


def classify_backend_output(
    *,
    backend_name: str,
    agent_messages: str,
    session_id: str,
    error_text: str,
    fatal_tokens: Iterable[str] = _DEFAULT_FATAL_TOKENS,
    treat_missing_session_as_ok_warning: bool = True,
    usage: dict[str, int | str | None] | None = None,
) -> BackendResult:
    """Shared classifier for all backends.

    Rules:
      * FATAL tokens are matched only against ``error_text`` / stderr.
      * Empty agent_messages with no fatal tokens returns FATAL with descriptive error.
      * A successful run without an extracted SESSION_ID returns OK + warning.
    """
    agent_messages_stripped = (agent_messages or "").strip()
    error_text_stripped = (error_text or "").strip()

    error_lower = _normalize(error_text_stripped)
    resolved_usage = usage if usage is not None else {}

    if error_text_stripped and any(token in error_lower for token in fatal_tokens):
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=session_id,
            agent_messages=agent_messages,
            error=error_text_stripped or "fatal backend/auth failure",
            error_class="fatal_backend",
            usage=resolved_usage,
        )

    if not agent_messages_stripped:
        extra = f" {error_text_stripped}" if error_text_stripped else ""
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=session_id,
            agent_messages=agent_messages,
            error=f"Failed to get output from the {backend_name} session.{extra}".strip(),
            error_class="no_agent_messages",
            usage=resolved_usage,
        )

    if not session_id and treat_missing_session_as_ok_warning:
        return BackendResult(
            outcome="OK",
            SESSION_ID="",
            agent_messages=agent_messages,
            error="warning: no SESSION_ID",
            error_class="warning",
            usage=resolved_usage,
        )

    return BackendResult(
        outcome="OK",
        SESSION_ID=session_id,
        agent_messages=agent_messages,
        error="",
        error_class="",
        usage=resolved_usage,
    )


_VERIFIED_COMMANDS: dict[str, frozenset[str]] = {
    "claude": frozenset({"bash"}),
    "codex": frozenset({"bash"}),
}


def classify_tool_activity(provider: str, tool_name: str) -> Literal["command", "tool_call"]:
    """Classify tool activity as 'command' or 'tool_call'.

    Uses exact, case-sensitive provider and tool-name allow-lists.
    """
    commands = _VERIFIED_COMMANDS.get(provider)
    if commands is not None and tool_name in commands:
        return "command"
    return "tool_call"


__all__ = ["BackendParams", "BackendResult", "classify_backend_output", "classify_tool_activity", "parse_json_object", "preflight"]
