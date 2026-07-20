"""Public structured models for the OpenMCP daemon."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


JobState = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
    "integrated",
    "integration_conflict",
]
StageState = Literal[
    "pending",
    "ready",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "interrupted",
    "skipped",
]


class ProjectView(BaseModel):
    id: str
    alias: str
    root: str
    head_commit: str
    clean: bool
    created_at: str


class ArtifactView(BaseModel):
    kind: str
    path: str


class StageView(BaseModel):
    id: str
    state: StageState
    mode: Literal["read", "write"]
    attempts: int = 0
    target_id: str = ""
    text: str = ""
    error: str = ""
    commit: str = ""


class JobResult(BaseModel):
    text: str = ""
    commit: str = ""
    artifacts: list[ArtifactView] = Field(default_factory=list)
    error: str = ""


class JobView(BaseModel):
    id: str
    project_id: str
    workflow: str
    routing_profile: str
    state: JobState
    context_key: str
    parent_job_id: str
    base_commit: str
    integration_base: str
    branch: str
    created_at: str
    updated_at: str
    stages: list[StageView] = Field(default_factory=list)
    result: JobResult = Field(default_factory=JobResult)


class ModelTargetView(BaseModel):
    id: str
    model: str
    capabilities: list[str]
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


class TaskRouteResult(BaseModel):
    task: str
    template: dict[str, Any]


class ClientInstructionResult(BaseModel):
    root: str
    instructions: str


class DaemonStatusResult(BaseModel):
    status: Literal["running", "stopping"]
    workers: int
    active_jobs: int
    queued_jobs: int


class DaemonReloadResult(BaseModel):
    success: bool
    targets: int
    routes: int
    routing_profiles: int
    restart_required: list[str] = Field(default_factory=list)


class ResourcePayload(BaseModel):
    data: Any


__all__ = [
    "ActionResult",
    "ArtifactView",
    "ClientInstructionResult",
    "ContextStreamView",
    "DaemonReloadResult",
    "DaemonStatusResult",
    "JobResult",
    "JobState",
    "JobView",
    "ModelTargetView",
    "ProjectView",
    "ResourcePayload",
    "StageState",
    "StageView",
    "SubmissionResult",
    "TaskRouteResult",
]
