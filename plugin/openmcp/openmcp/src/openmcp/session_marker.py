"""Shared session-id marker prompt + extractor.

We instruct the agent to print a sentinel line containing its session/
conversation id so the caller can extract it reliably regardless of CLI
output format changes. Backends fall back to their own extraction logic
when the marker is absent.
"""

from __future__ import annotations

import re

SESSION_MARKER = "OPENMCP_SESSION_ID"

PROMPT_SUFFIX = (
    "\n\n---\n"
    f"Output format requirement:\n"
    "on the FINAL line of your reply, include one final metadata line in this exact format:\n"
    f"`[{SESSION_MARKER}]: <your session_id, thread_id or conversation_id>` "
    "so the orchestrator can resume this session. Use the literal brackets."
)

_MARKER_RE = re.compile(
    rf"\[{SESSION_MARKER}\]:\s*([A-Za-z0-9][A-Za-z0-9_-]*)",
    re.IGNORECASE,
)

_STRIP_RE = re.compile(
    rf"\n?\[{SESSION_MARKER}\]:\s*\S*\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def augment_prompt(prompt: str) -> str:
    """Append the marker instruction to a user prompt."""
    if SESSION_MARKER in prompt:
        return prompt
    return prompt + PROMPT_SUFFIX


def strip_marker(text: str) -> str:
    """Remove the [OPENMCP_SESSION_ID]: ... line from agent output."""
    return _STRIP_RE.sub("", text).rstrip()


def extract_marker_session_id(text: str) -> str:
    """Return the marker-emitted id, or '' if missing/unknown."""
    if not text:
        return ""
    match = _MARKER_RE.search(text)
    if not match:
        return ""
    value = match.group(1).strip()
    if value.lower() == "unknown":
        return ""
    return value


__all__ = ["augment_prompt", "extract_marker_session_id", "strip_marker", "SESSION_MARKER"]
