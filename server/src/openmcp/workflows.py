"""Fixed built-in job workflow definitions."""

from __future__ import annotations

BUILTIN_WORKFLOWS = ("consult", "implement", "review")


def get_workflow(name: str) -> str:
    if name not in BUILTIN_WORKFLOWS:
        raise ValueError(
            f"Unknown workflow {name!r}; expected one of {BUILTIN_WORKFLOWS}"
        )
    return name


def validate_request(workflow: str, prompt: str) -> str:
    resolved_prompt = prompt.strip()
    if not resolved_prompt:
        raise ValueError("Prompt must contain text")
    return resolved_prompt


__all__ = [
    "BUILTIN_WORKFLOWS",
    "get_workflow",
    "validate_request",
]
