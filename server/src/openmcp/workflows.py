"""Fixed built-in job workflow definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class WorkflowDefinition:
    name: str
    capability: str


_WORKFLOWS = {
    "implement": WorkflowDefinition("implement", "code"),
    "review": WorkflowDefinition("review", "review"),
    "consult": WorkflowDefinition("consult", "consult"),
}
BUILTIN_WORKFLOWS = tuple(sorted(_WORKFLOWS))


def get_workflow(name: str) -> WorkflowDefinition:
    try:
        return _WORKFLOWS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown workflow {name!r}; expected one of {BUILTIN_WORKFLOWS}"
        ) from exc


def validate_request(workflow: WorkflowDefinition, prompt: str) -> str:
    resolved_prompt = prompt.strip()
    if not resolved_prompt:
        raise ValueError("Prompt must contain text")
    return resolved_prompt


__all__ = [
    "BUILTIN_WORKFLOWS",
    "WorkflowDefinition",
    "get_workflow",
    "validate_request",
]
