"""Public structured models for the OpenMCP daemon."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JobState = Literal[
    "queued", "running", "succeeded", "failed", "cancelled", "interrupted"
]
TERMINAL_STATES: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled", "interrupted"}
)


class ProjectView(BaseModel):
    id: str
    alias: str
    root: str
    created_at: str


class JobResult(BaseModel):
    text: str = ""
    error: str = ""


class JobView(BaseModel):
    id: str
    project_id: str
    workflow: str
    profile: str
    state: JobState
    context_key: str
    target_id: str = ""
    attempts: int = 0
    created_at: str
    updated_at: str
    result: JobResult = Field(default_factory=JobResult)


class TargetView(BaseModel):
    id: str
    model: str
    max_concurrency: int
    active: int
    healthy: bool
    circuit_open_until: str = ""


class ContextStreamView(BaseModel):
    project_id: str
    context_key: str
    role: str
    turns: int
    sessions: dict[str, str]


class SubmissionResult(BaseModel):
    job_id: str
    state: JobState


class ActionResult(BaseModel):
    success: bool
    job_id: str
    state: JobState
    error: str = ""


class TaskGuideResult(BaseModel):
    task: str
    guide: dict[str, Any]


class DaemonStatusResult(BaseModel):
    status: Literal["running", "stopping"]
    workers: int
    active_jobs: int
    queued_jobs: int


class ResourcePayload(BaseModel):
    data: Any


__all__ = [
    "ActionResult",
    "ContextStreamView",
    "DaemonStatusResult",
    "JobResult",
    "JobState",
    "JobView",
    "ProjectView",
    "ResourcePayload",
    "SubmissionResult",
    "TERMINAL_STATES",
    "TargetView",
    "TaskGuideResult",
]
