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
ERROR_CODES = Literal[
    "unknown_project", "invalid_path", "unknown_job", "unknown_profile", "invalid_state", "config_invalid",
    "daemon_stopping", "invalid_request", "response_too_large", "internal_error", "targets_unavailable",
    "unknown_card", "csrf_rejected", "forbidden", "unauthorized", "conflict", "invalid_args", "not_found",
    "runtime_unavailable", "shutdown_unavailable", "unsupported_media_type",
]
FAILURE_KINDS = ("cancelled", "circuit_open", "context_overflow", "request_fatal", "target_fatal", "transient")
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
    next_target: str | None = None


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
    def last_error(self) -> str:
        return self.latest_error


class JobView(BaseModel):
    id: str
    project_id: str
    workflow: str
    profile: str
    state: JobState
    session: str
    target_id: str = ""
    from_job: str = ""
    created_at: str
    updated_at: str
    result: JobResult = Field(default_factory=JobResult)


class JobSummary(BaseModel):
    id: str
    project: str
    workflow: str
    profile: str
    target_id: str
    session: str
    state: JobState
    from_job: str = ""
    created_at: str
    updated_at: str


class TargetView(BaseModel):
    id: str
    model: str
    backend: str = ""
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
    "LIST_JOB_ID_ACTION",
    "UNKNOWN_JOB_MESSAGE",
    "OrchestrationError",
    "ERROR_CODES",
    "ActionResult",
    "ConfigHealth",
    "DashboardError",
    "DashboardJob",
    "DashboardOverview",
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


class OrchestrationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "internal_error",
        next_action: str = "Retry once, then report the request ID.",
        retry_after_s: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.next_action = next_action
        self.retry_after_s = retry_after_s


UNKNOWN_JOB_MESSAGE = "Job does not exist."
LIST_JOB_ID_ACTION = "Call list for the project and use a listed job ID."
