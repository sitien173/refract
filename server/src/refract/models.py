"""Public structured models for the Refract daemon."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    source_path: str = ""
    current: str | None = None
    references: list[dict[str, Any]] | None = None


class TargetReference(BaseModel):
    scope: Literal["global", "project"]
    project_id: str | None = None
    profile_id: str
    workflow: str


class TargetEditorData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    backend: str = ""
    model: str = ""
    backend_profile: str = ""
    reasoning: str = ""
    system_prompt: str = ""
    isolated: bool = False
    read_only: bool = False
    args: list[str] = Field(default_factory=list)
    max_concurrency: int = 1

    @model_validator(mode="before")
    @classmethod
    def _normalize_profile(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "backend_profile" in data and "profile" in data:
                raise ValueError(
                    "Use 'backend_profile', not both 'backend_profile' and legacy 'profile'"
                )
            if "backend_profile" not in data and "profile" in data:
                data = dict(data)
                data["backend_profile"] = data.pop("profile")
        return data


class TargetListResponse(BaseModel):
    revision: str
    source_path: str
    targets: list[TargetEditorData]


class TargetResponse(BaseModel):
    revision: str
    source_path: str
    target: TargetEditorData


class TargetDeleteResponse(BaseModel):
    revision: str
    source_path: str
    deleted: str


class WorkflowPolicyData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: list[str]
    timeout_s: int = 0


class ProfileEditorData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    extends: str | None = None
    workflows: dict[str, WorkflowPolicyData | None] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_workflows(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = dict(data)
            workflows = dict(data.get("workflows") or {})
            for wf in ("consult", "implement", "review", "other"):
                if wf in data and wf not in workflows:
                    workflows[wf] = data.pop(wf)
            if workflows:
                data["workflows"] = workflows
        return data

    @field_validator("extends", mode="before")
    @classmethod
    def _normalize_extends(cls, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()
            return value if value else None
        return value


class ProfileEditorResponse(BaseModel):
    id: str
    extends: str | None = None
    workflows: dict[str, WorkflowPolicyData | None] = Field(default_factory=dict)
    declared: dict[str, WorkflowPolicyData | None] = Field(default_factory=dict)
    inherited: dict[str, WorkflowPolicyData | None] = Field(default_factory=dict)
    effective: dict[str, WorkflowPolicyData | None] = Field(default_factory=dict)
    sources: dict[str, str] = Field(default_factory=dict)


class ProfileReference(BaseModel):
    scope: Literal["global", "project"]
    project_id: str | None = None
    profile_id: str | None = None
    relationship: Literal["default_profile", "extends"]


class ProfileListResponse(BaseModel):
    revision: str
    source_path: str
    default_profile: str
    available_targets: list[str]
    profiles: list[ProfileEditorResponse]


class ProfileResponse(BaseModel):
    revision: str
    source_path: str
    default_profile: str
    available_targets: list[str]
    profile: ProfileEditorResponse


class ProfileDeleteResponse(BaseModel):
    revision: str
    source_path: str
    deleted: str


class ProjectOverrideListResponse(BaseModel):
    revision: str
    source_path: str
    global_default_profile: str
    project_default_profile: str
    available_targets: list[str]
    overrides: list[ProfileEditorResponse]


class ProjectOverrideResponse(BaseModel):
    revision: str
    source_path: str
    override: ProfileEditorResponse


class ProjectOverrideDeleteResponse(BaseModel):
    revision: str
    source_path: str
    deleted: str
    fallback: ProfileEditorResponse | None = None


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


__all__ = [
    "ActionResult",
    "ConfigHealth",
    "DashboardBootstrap",
    "DashboardError",
    "DashboardJob",
    "DashboardOverview",
    "ConfigHealthSnapshot",
    "ConfigurationHealth",
    "ContextStreamView",
    "DaemonStatusResult",
    "JobOutputResponse",
    "JobResult",
    "JobState",
    "JobStreamEvent",
    "JobSummary",
    "Measurement",
    "ProfileDeleteResponse",
    "ProfileEditorData",
    "ProfileEditorResponse",
    "ProfileListResponse",
    "ProfileReference",
    "ProfileResponse",
    "ProjectOverrideDeleteResponse",
    "ProjectOverrideListResponse",
    "ProjectOverrideResponse",
    "ProjectView",
    "StreamStatus",
    "StreamTotals",
    "SubmissionResult",
    "TERMINAL_STATES",
    "TargetDeleteResponse",
    "TargetEditorData",
    "TargetListResponse",
    "TargetReference",
    "TargetResponse",
    "TargetView",
    "TelemetryData",
    "WorkflowPolicyData",
]
