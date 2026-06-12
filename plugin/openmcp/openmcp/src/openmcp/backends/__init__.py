"""Backend interfaces for openmcp."""

from dataclasses import dataclass
from typing import Iterable, Literal, Optional


@dataclass(slots=True)
class BackendResult:
    outcome: Literal["OK", "RETRYABLE", "FATAL"]
    SESSION_ID: str
    agent_messages: str
    error: str
    error_class: str


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
)

_DEFAULT_RETRYABLE_TOKENS = (
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


def _normalize(text: str) -> str:
    # Strip a few benign strings that would otherwise be matched as fatal/retryable.
    return text.lower().replace("node_tls_reject_unauthorized", "")


def classify_backend_output(
    *,
    backend_name: str,
    agent_messages: str,
    session_id: str,
    error_text: str,
    fatal_tokens: Iterable[str] = _DEFAULT_FATAL_TOKENS,
    retryable_tokens: Iterable[str] = _DEFAULT_RETRYABLE_TOKENS,
    extra_retryable_signal: Optional[bool] = None,
    treat_missing_session_as_ok_warning: bool = True,
) -> BackendResult:
    """Shared classifier for all backends.

    Rules (consistent across backends):
      * FATAL tokens are matched only against ``error_text`` / stderr.
        Worker prose mentioning ``authentication`` or ``api key`` does not
        downgrade a successful run to FATAL.
      * RETRYABLE tokens are checked only when ``agent_messages`` is empty;
        otherwise the run produced usable output and benign mentions of
        ``timeout`` / ``rate limit`` inside the agent's text should not
        be treated as a transport failure.
      * A successful run without an extracted SESSION_ID returns
        ``OK`` + warning (matches the codex / agy contract).
    """
    agent_messages_stripped = (agent_messages or "").strip()
    error_text_stripped = (error_text or "").strip()

    error_lower = _normalize(error_text_stripped)

    if error_text_stripped and any(token in error_lower for token in fatal_tokens):
        return BackendResult(
            outcome="FATAL",
            SESSION_ID=session_id,
            agent_messages=agent_messages,
            error=error_text_stripped or "fatal backend/auth failure",
            error_class="fatal_backend",
        )

    if not agent_messages_stripped:
        if error_text_stripped and any(token in error_lower for token in retryable_tokens):
            return BackendResult(
                outcome="RETRYABLE",
                SESSION_ID=session_id,
                agent_messages=agent_messages,
                error=error_text_stripped or "retryable backend failure",
                error_class="retryable_backend",
            )
        if extra_retryable_signal:
            return BackendResult(
                outcome="RETRYABLE",
                SESSION_ID=session_id,
                agent_messages=agent_messages,
                error=error_text_stripped or "retryable backend failure",
                error_class="retryable_backend",
            )
        extra = f" {error_text_stripped}" if error_text_stripped else ""
        return BackendResult(
            outcome="RETRYABLE",
            SESSION_ID=session_id,
            agent_messages=agent_messages,
            error=f"Failed to get output from the {backend_name} session.{extra}".strip(),
            error_class="no_agent_messages",
        )

    if not session_id and treat_missing_session_as_ok_warning:
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
        error="",
        error_class="",
    )


__all__ = ["BackendResult", "classify_backend_output"]
