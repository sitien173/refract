"""Config models: runtime dataclasses and the pydantic file schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from pydantic_core import PydanticCustomError

from refract.logging_setup import is_log_file_disabled

DEFAULT_PORT = 8765
DEFAULT_ASK_TIMEOUT_S = 300
REFRACT_DIR = ".refract"
CONFIG_FILE = "config.toml"
SCHEMA_VERSION = 1

RetryCode = Literal[
    "timeout", "service_error", "execution_error", "stdin_failed", "no_output",
    "context_overflow", "bad_cwd", "invalid_prompt", "invalid_args",
    "unsupported_option", "invalid_model", "missing_cli", "spawn_failed", "auth",
]
Backend = Literal["agy", "codex", "pi", "claude"]
LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]


# Runtime values built from a validated file. Other modules import these names.


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    attempts: int = 0
    codes: tuple[str, ...] = ()
    patterns: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class TargetConfig:
    id: str
    backend: str
    model: str = ""
    backend_profile: str = ""
    reasoning: str = ""
    system_prompt: str = ""
    args: tuple[str, ...] = ()
    max_concurrency: int = 1
    context_window: int | None = None
    retry: RetryPolicy = RetryPolicy()
    env: dict[str, str] = field(default_factory=dict, repr=False)


@dataclass(slots=True, frozen=True)
class TargetSelection:
    """Targets and timeout for one workflow inside a profile."""

    targets: tuple[str, ...]
    timeout_s: int = 0


@dataclass(slots=True, frozen=True)
class ProfileDeclaration:
    """Normalized raw declaration for one profile."""

    extends: str | None = None
    workflows: dict[str, TargetSelection] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class LoggingConfig:
    """Application log sinks and retention policy."""

    level: str = "INFO"
    file: Path | None = None
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5


@dataclass(slots=True, frozen=True)
class NotificationsConfig:
    """Desktop notification settings."""

    enabled: bool = False


@dataclass(slots=True, frozen=True)
class DaemonConfig:
    home: Path
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    max_jobs: int = 4
    default_profile: str = ""
    targets: tuple[TargetConfig, ...] = field(default_factory=tuple)
    profiles: dict[str, dict[str, TargetSelection]] = field(default_factory=dict)
    profile_declarations: dict[str, ProfileDeclaration] = field(default_factory=dict)
    config_path: Path | None = None
    config_revision: str = ""
    config_modification_time: str = ""
    config_loaded_at: str = ""
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    breaker_failure_threshold: int = 3
    breaker_base_cooldown_s: int = 60
    breaker_max_cooldown_s: int = 900
    ask_timeout_s: int = DEFAULT_ASK_TIMEOUT_S

    @property
    def database_path(self) -> Path:
        return self.home / "refract.db"

    @property
    def revision(self) -> str:
        """The global source revision used by this catalog."""
        return self.config_revision


# File schema. Every model forbids unknown keys and uses strict types.

PositiveInt = Annotated[int, Field(ge=1)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _stripped(value: str) -> str:
    text = value.strip()
    if not text:
        raise PydanticCustomError("empty_string", "must not be empty")
    return text


def args_violation(backend: str, args: list[str] | tuple[str, ...]) -> str | None:
    """Return the error code for argv that overrides transport or workspace limits."""
    if any("\x00" in item for item in args):
        return "args_nul"
    if "--" in args:
        return "args_reserved_token"
    if backend == "codex" and any(
        item in {"--cd", "-C"}
        or item.startswith("--cd=")
        or (item.startswith("-C") and len(item) > 2)
        for item in args
    ):
        return "args_workspace_override"
    return None


class RetryFile(_Model):
    attempts: Annotated[int, Field(ge=0)] = 0
    codes: list[RetryCode] = []
    patterns: list[Annotated[str, Field(min_length=1)]] = []


class SelectionFile(_Model):
    targets: Annotated[list[str], Field(min_length=1)]
    timeout_s: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, value: Any) -> Any:
        """Accept ``"id"`` and ``["id", ...]`` as shorthand for ``{targets = ...}``."""
        if isinstance(value, str):
            return {"targets": [value]}
        if isinstance(value, list):
            return {"targets": value}
        if isinstance(value, dict) and isinstance(value.get("targets"), str):
            return {**value, "targets": [value["targets"]]}
        return value

    @field_validator("targets")
    @classmethod
    def _strip_targets(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value]


class ProfileFile(_Model):
    extends: str | None = None
    consult: SelectionFile | None = None
    implement: SelectionFile | None = None
    other: SelectionFile | None = None
    review: SelectionFile | None = None

    @field_validator("extends")
    @classmethod
    def _extends(cls, value: str | None) -> str | None:
        return None if value is None else _stripped(value)

    @model_validator(mode="after")
    def _declares_something(self) -> ProfileFile:
        if self.extends is None and not self.workflows():
            raise PydanticCustomError("empty_profile", "must declare extends or a workflow")
        return self

    def workflows(self) -> dict[str, SelectionFile]:
        return {
            name: selection
            for name in ("consult", "implement", "other", "review")
            if (selection := getattr(self, name)) is not None
        }


def _check_env(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise PydanticCustomError("env_key_empty", "key must not be empty")
        if "=" in key:
            raise PydanticCustomError("env_key_equals", "key must not contain '='")
        if "\x00" in key:
            raise PydanticCustomError("env_key_nul", "key must not contain NUL")
        if key.startswith("REFRACT_ASK_"):
            raise PydanticCustomError("env_key_reserved", "key uses a protected prefix")
        if isinstance(item, str):
            if "\x00" in item:
                raise PydanticCustomError("env_value_nul", "value must not contain NUL")
            if "${" in item:
                raise PydanticCustomError("env_value_interpolation", "value must be literal")
    return value


class TargetFile(_Model):
    id: str
    backend: Backend
    model: str = ""
    backend_profile: str = ""
    reasoning: str = ""
    system_prompt: str = ""
    args: list[str] = []
    max_concurrency: PositiveInt = 1
    context_window: PositiveInt | None = None
    retry: RetryFile = RetryFile()
    env: dict[str, str] = {}

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        return _stripped(value)

    @field_validator("args")
    @classmethod
    def _args(cls, value: list[str], info: ValidationInfo) -> list[str]:
        code = args_violation(info.data.get("backend", ""), value)
        if code is not None:
            raise PydanticCustomError(code, "invalid target args")
        return value

    @field_validator("env", mode="before")
    @classmethod
    def _env(cls, value: Any) -> Any:
        return _check_env(value)


class DaemonFile(_Model):
    host: str = "127.0.0.1"
    port: Annotated[int, Field(ge=1, le=65535)] = DEFAULT_PORT
    max_jobs: PositiveInt = 4
    default_profile: str
    breaker_failure_threshold: PositiveInt = 3
    breaker_base_cooldown_s: PositiveInt = 60
    breaker_max_cooldown_s: PositiveInt = 900
    ask_timeout_s: PositiveInt = DEFAULT_ASK_TIMEOUT_S

    @field_validator("host", "default_profile")
    @classmethod
    def _text(cls, value: str) -> str:
        return _stripped(value)

    @field_validator("breaker_max_cooldown_s")
    @classmethod
    def _ordered(cls, value: int, info: ValidationInfo) -> int:
        if value < info.data.get("breaker_base_cooldown_s", 0):
            raise PydanticCustomError("breaker_order", "must be >= breaker_base_cooldown_s")
        return value


class LoggingFile(_Model):
    level: str = "INFO"
    file: Any = "refract.log"
    max_bytes: PositiveInt = 10 * 1024 * 1024
    backup_count: Annotated[int, Field(ge=0)] = 5

    @field_validator("level")
    @classmethod
    def _level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in LogLevel.__args__:
            raise PydanticCustomError("log_level", "must be a known log level")
        return level

    @field_validator("file")
    @classmethod
    def _file(cls, value: Any) -> str | None:
        """A path string, or ``None`` when the value is a disable sentinel."""
        if value is False:
            return None
        if not isinstance(value, str):
            raise PydanticCustomError("log_file_type", "must be a path string or false")
        return None if is_log_file_disabled(value) else value


class NotificationsFile(_Model):
    enabled: bool = False


def _check_schema_version(value: Any) -> Any:
    """Reject booleans and floats, which ``Literal[1]`` would accept as ``1``."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise PydanticCustomError("literal_error", "must be the integer 1")
    return value


class ConfigFile(_Model):
    schema_version: Annotated[Literal[1], BeforeValidator(_check_schema_version)]
    daemon: DaemonFile
    logging: LoggingFile = LoggingFile()
    notifications: NotificationsFile = NotificationsFile()
    targets: Annotated[list[TargetFile], Field(min_length=1)]
    profiles: Annotated[dict[str, ProfileFile], Field(min_length=1)]


class ProjectTargetFile(_Model):
    id: str
    env: dict[str, str] = {}

    @field_validator("id")
    @classmethod
    def _id(cls, value: str) -> str:
        return _stripped(value)

    @field_validator("env", mode="before")
    @classmethod
    def _env(cls, value: Any) -> Any:
        return _check_env(value)


class ProjectConfigFile(_Model):
    schema_version: Annotated[Literal[1], BeforeValidator(_check_schema_version)] | None = None
    targets: list[ProjectTargetFile] | None = None
    profiles: Annotated[dict[str, ProfileFile], Field(min_length=1)] | None = None
