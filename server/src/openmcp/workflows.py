"""Fixed built-in job workflow definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class WorkflowDefinition:
    name: str
    capability: str
    writes: bool


_WORKFLOWS = {
    "implement": WorkflowDefinition("implement", "code", True),
    "review": WorkflowDefinition("review", "review", False),
    "consult": WorkflowDefinition("consult", "consult", False),
}
BUILTIN_WORKFLOWS = tuple(sorted(_WORKFLOWS))


def get_workflow(name: str) -> WorkflowDefinition:
    try:
        return _WORKFLOWS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown workflow {name!r}; expected one of {BUILTIN_WORKFLOWS}"
        ) from exc


def validate_request(
    workflow: WorkflowDefinition,
    prompt: str,
    commit_message: str,
) -> tuple[str, str]:
    resolved_prompt = prompt.strip()
    resolved_message = commit_message.strip()
    if not resolved_prompt:
        raise ValueError("Prompt must contain text")
    if resolved_message and not workflow.writes:
        raise ValueError("commit_message is only valid for implement")
    return resolved_prompt, resolved_message


__all__ = [
    "BUILTIN_WORKFLOWS",
    "WorkflowDefinition",
    "get_workflow",
    "validate_request",
]
