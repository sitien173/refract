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
JOB_RESOURCE_URI_TEMPLATE = "openmcp://jobs/{job_id}"


def job_resource_uri(job_id: str) -> str:
    return JOB_RESOURCE_URI_TEMPLATE.format(job_id=job_id)


class ProjectView(BaseModel):
    id: str
    alias: str
    root: str
    created_at: str


class JobResult(BaseModel):
    text: str = ""
    error: str = ""


class ConfigRevision(BaseModel):
    """Identity and display metadata for one global configuration source."""

    content_hash: str = ""
    source_path: str = ""
    modification_time: str = ""
    loaded_at: str = ""
    valid: bool = False

    @property
    def revision(self) -> str:
        return self.content_hash

    @property
    def hash(self) -> str:
        return self.content_hash

    @property
    def path(self) -> str:
        return self.source_path

    @property
    def mtime(self) -> str:
        return self.modification_time


class ConfigHealth(BaseModel):
    """Latest global configuration load evidence."""

    attempted_at: str = ""
    successful_at: str = ""
    source_path: str = ""
    modification_time: str = ""
    revision: str = ""
    valid: bool = False
    latest_error: str = ""
    last_known_good_revision: str = ""

    @property
    def path(self) -> str:
        return self.source_path

    @property
    def last_attempted_at(self) -> str:
        return self.attempted_at

    @property
    def last_successful_at(self) -> str:
        return self.successful_at

    @property
    def current_revision(self) -> str:
        return self.revision

    @property
    def last_error(self) -> str:
        return self.latest_error

    @property
    def mtime(self) -> str:
        return self.modification_time


# The longer names are useful to callers that do not use the dashboard shorthand.
ConfigurationHealth = ConfigHealth
ConfigHealthSnapshot = ConfigHealth


class JobView(BaseModel):
    id: str
    project_id: str
    workflow: str
    profile: str
    config_revision: str = ""
    state: JobState
    context_key: str
    target_id: str = ""
    attempts: int = 0
    created_at: str
    updated_at: str
    result: JobResult = Field(default_factory=JobResult)


class JobSummary(BaseModel):
    id: str
    workflow: str
    profile: str
    state: JobState
    context_key: str
    attempts: int = 0
    updated_at: str


class TargetView(BaseModel):
    id: str
    model: str
    backend: str = ""
    isolated: bool = False
    read_only: bool = False
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
    resource_uri: str


class ActionResult(BaseModel):
    success: bool
    job_id: str
    state: JobState
    error: str = ""


class TaskGuideResult(BaseModel):
    guide: dict[str, Any]


class ContextInstructionsResult(BaseModel):
    project_id: str
    instructions: dict[str, str]


class DaemonStatusResult(BaseModel):
    status: Literal["running", "stopping"]
    workers: int
    active_jobs: int
    queued_jobs: int


class DashboardError(BaseModel):
    """Stable, non-sensitive dashboard error envelope."""

    error: str
    code: str = ""
    unchanged: str = ""
    recovery: str = ""
    source_path: str = ""
    current: str | None = None


class DashboardBootstrap(BaseModel):
    csrf_token: str


class DashboardOverview(BaseModel):
    daemon: DaemonStatusResult
    configuration: ConfigHealth
    projects: int
    unhealthy_targets: int


class DashboardJob(BaseModel):
    id: str
    project_id: str
    workflow: str
    profile: str
    state: JobState
    context_key: str
    config_revision: str = ""
    target_id: str = ""
    attempts: int = 0
    created_at: str
    updated_at: str
    result: JobResult = Field(default_factory=JobResult)
    execution_plan: dict[str, Any] = Field(default_factory=dict)


class DashboardContextInstruction(BaseModel):
    project_id: str
    workflow: str
    instruction: str = ""


class ResourcePayload(BaseModel):
    data: Any


__all__ = [
    "ActionResult",
    "ConfigHealth",
    "DashboardBootstrap",
    "DashboardContextInstruction",
    "DashboardError",
    "DashboardJob",
    "DashboardOverview",
    "ConfigHealthSnapshot",
    "ConfigRevision",
    "ConfigurationHealth",
    "ContextInstructionsResult",
    "ContextStreamView",
    "DaemonStatusResult",
    "JobResult",
    "JobState",
    "JobSummary",
    "JOB_RESOURCE_URI_TEMPLATE",
    "JobView",
    "job_resource_uri",
    "ProjectView",
    "ResourcePayload",
    "SubmissionResult",
    "TERMINAL_STATES",
    "TargetView",
    "TaskGuideResult",
]
