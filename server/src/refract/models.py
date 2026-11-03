"""Public structured models for the Refract daemon."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from refract.telemetry import Measurement, TelemetryData
from refract.result_metadata import JobResultMetadata


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
    metadata: JobResultMetadata = Field(default_factory=JobResultMetadata)


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
    project_id: str
    workflow: str
    profile: str
    state: JobState
    context_key: str
    attempts: int = 0
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
    context_key: str
    config_revision: str = ""
    target_id: str = ""
    attempts: int = 0
    created_at: str
    updated_at: str
    result: JobResult = Field(default_factory=JobResult)
    execution_plan: dict[str, Any] = Field(default_factory=dict)
    suspect: bool = False
    diagnostic_count: int = 0


StreamStatus = Literal["unavailable", "active", "complete", "truncated", "failed"]


class JobStreamEvent(BaseModel):
    id: int = 0
    version: int = 1
    job_id: str = ""
    created_at: str = ""
    attempt: int = 1
    target_id: str = ""
    backend: str = ""
    kind: str = ""
    entity_id: str = ""
    parent_entity_id: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class StreamTotals(BaseModel):
    events: int = 0
    bytes: int = 0

    def __iter__(self):
        return iter((self.events, self.bytes))


class JobOutputResponse(BaseModel):
    events: list[JobStreamEvent] = Field(default_factory=list)
    cursor: int = 0
    has_more: bool = False
    retained_from: int = 0
    stream_status: StreamStatus = "unavailable"


class DiagnosticReport(BaseModel):
    id: str
    job_id: str
    category: Literal["protocol", "output"]
    created_at: str
    expected: str
    observed: str
    project_id: str
    current_state: JobState


class DiagnosticReportResult(BaseModel):
    report: DiagnosticReport
    duplicate: bool


__all__ = [
    "ActionResult",
    "ConfigHealth",
    "DashboardError",
    "DashboardJob",
    "DashboardOverview",
    "ConfigHealthSnapshot",
    "ConfigurationHealth",
    "ContextStreamView",
    "DaemonStatusResult",
    "DiagnosticReport",
    "DiagnosticReportResult",
    "JobOutputResponse",
    "JobResult",
    "JobState",
    "JobStreamEvent",
    "JobSummary",
    "Measurement",
    "ProjectView",
    "StreamStatus",
    "StreamTotals",
    "SubmissionResult",
    "TERMINAL_STATES",
    "TargetView",
    "TelemetryData",
]
