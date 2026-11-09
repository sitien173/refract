"""Public structured models for the Refract daemon."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

JobState = Literal[
    "queued", "running", "succeeded", "failed", "cancelled", "interrupted"
]
TERMINAL_STATES: frozenset[str] = frozenset(
    {"succeeded", "failed", "cancelled", "interrupted"}
)
FAILURE_KINDS = ("cancelled", "circuit_open", "context_overflow", "replay_blocked", "request_fatal", "target_fatal", "transient")
class ProjectView(BaseModel):
    id: str
    root: str
    created_at: str


class JobResult(BaseModel):
    text: str = ""
    error: str = ""
    failure_kind: str | None = None
    model: str | None = None
    duration_ms: int | None = None
    tokens: dict[str, int | None] | None = None


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
    state: JobState
    session: str
    target_id: str = ""
    retry_of: str = ""
    created_at: str
    updated_at: str
    result: JobResult = Field(default_factory=JobResult)


class JobSummary(BaseModel):
    id: str
    project: str
    workflow: str
    profile: str
    target: str
    session: str
    state: JobState
    retry_of: str = ""
    created_at: str
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
    breaker_state: Literal["closed", "open", "half_open"]
    cooldown_s: int
    probing: bool


class SubmissionResult(BaseModel):
    job_id: str
    state: JobState


class ActionResult(BaseModel):
    success: bool
    job_id: str
    state: JobState
    error: str = ""


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
    prompt: str = ""
    state: JobState
    session: str
    target_id: str = ""
    created_at: str
    updated_at: str
    result: JobResult = Field(default_factory=JobResult)
    execution_plan: dict[str, Any] = Field(default_factory=dict)
    suspect: bool = False


__all__ = [
    "ActionResult",
    "ConfigHealth",
    "DashboardError",
    "DashboardJob",
    "DashboardOverview",
    "ConfigHealthSnapshot",
    "ConfigurationHealth",
    "DaemonStatusResult",
    "FAILURE_KINDS",
    "JobResult",
    "JobState",
    "JobSummary",
    "ProjectView",
    "SubmissionResult",
    "TERMINAL_STATES",
    "TargetView",
]
