"""Daemon configuration loading."""

from __future__ import annotations

import json
import math
import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from refract.logging_setup import get_logger

from refract.config_inspection import (
    REMOVED_KEYS,
    ConfigSource,
    ConfigurationLoadError,
    read_config_source,
    removed_key_message,
    sha256_bytes,
    utc_now,
)
from refract.workflows import get_workflow

log = get_logger("config")
DEFAULT_PORT = 8765
DEFAULT_ASK_TIMEOUT_S = 300
_REFRACT_DIR = ".refract"
_CONFIG_FILE = "config.toml"
_TARGET_KEYS = frozenset({
    "id", "backend", "model", "backend_profile", "reasoning", "system_prompt",
    "isolated", "read_only", "args", "max_concurrency", "context_window",
    "retry", "env",
})


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
    isolated: bool = False
    read_only: bool = False
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
class ModelPricing:
    input: float
    output: float
    cache_read: float
    cache_write: float


@dataclass(slots=True, frozen=True)
class TelemetryConfig:
    enabled: bool | None = None
    endpoint: str = "https://telemetry.example.invalid/v1/events"


@dataclass(slots=True, frozen=True)
class PricingConfig:
    currency: str = "USD"
    models: dict[str, ModelPricing] = field(default_factory=dict)


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
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    pricing: PricingConfig = field(default_factory=PricingConfig)
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



def refract_home() -> Path:
    override = os.environ.get("REFRACT_HOME", "").strip()
    return Path(override).expanduser() if override else Path.home() / _REFRACT_DIR


def load_guidance(
    home: Path,
    project_root: Path | None = None,
) -> dict[str, Any] | None:
    path = home / "task_guide.json"
    if project_root is not None:
        project_path = project_root / _REFRACT_DIR / "task_guide.json"
        if project_path.exists():
            path = project_path
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid task guide: {path}: {exc.msg}") from exc
    if not isinstance(value, dict) or not value:
        raise ValueError("Task guide must be a non-empty JSON object")
    return value


def _positive_int(value: Any, default: int | None, name: str) -> int | None:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _boolean(value: Any, default: bool, name: str) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return value


def _stripped_targets(raw: list[Any], *, profile_id: str, workflow: str) -> tuple[str, ...]:
    if not all(isinstance(value, str) for value in raw):
        raise ValueError(
            f"Profile {profile_id!r} workflow {workflow!r} targets "
            "must contain only strings"
        )
    return tuple(value.strip() for value in raw)


def _selection_timeout(raw_timeout: Any) -> int:
    if (
        isinstance(raw_timeout, bool)
        or not isinstance(raw_timeout, int)
        or raw_timeout < 0
    ):
        raise ValueError("timeout_s must be a non-negative integer")
    return raw_timeout


def _dict_selection(
    raw: dict[str, Any], *, profile_id: str, workflow: str
) -> tuple[tuple[str, ...], int]:
    if "max_attempts" in raw:
        raise ValueError(removed_key_message("profiles workflow max_attempts"))
    allowed = {"targets", "timeout_s"}
    unknown_options = set(raw) - allowed
    if unknown_options:
        raise ValueError(
            f"Profile {profile_id!r} workflow {workflow!r} has unsupported "
            f"settings: {sorted(unknown_options)}"
        )
    raw_targets = raw.get("targets", [])
    if isinstance(raw_targets, str):
        selected = (raw_targets.strip(),)
    elif isinstance(raw_targets, list):
        selected = _stripped_targets(raw_targets, profile_id=profile_id, workflow=workflow)
    else:
        selected = ()
    return selected, _selection_timeout(raw.get("timeout_s", 0))


def _target_selection(
    raw: Any,
    *,
    profile_id: str,
    workflow: str,
    target_by_id: dict[str, TargetConfig],
) -> TargetSelection:
    if isinstance(raw, str):
        name = raw.strip()
        selected = (name,) if name else ()
        timeout_s = 0
    elif isinstance(raw, list):
        selected = _stripped_targets(raw, profile_id=profile_id, workflow=workflow)
        timeout_s = 0
    elif isinstance(raw, dict):
        selected, timeout_s = _dict_selection(raw, profile_id=profile_id, workflow=workflow)
    else:
        selected = ()
        timeout_s = 0

    unknown_targets = set(selected) - target_by_id.keys()
    if not selected or unknown_targets or len(set(selected)) != len(selected):
        raise ValueError(
            f"Profile {profile_id!r} workflow {workflow!r} has invalid targets: "
            f"{sorted(unknown_targets)}"
        )
    return TargetSelection(targets=selected, timeout_s=timeout_s)


def _declared_extends(raw_extends: Any, profile_id: str) -> str | None:
    if raw_extends is None:
        return None
    if not isinstance(raw_extends, str) or not raw_extends.strip():
        raise ValueError(
            f"Profile {profile_id!r} extends must be a non-empty string"
        )
    return raw_extends.strip()


def _profile_declaration(
    profile_id: str,
    mapping: Any,
    target_by_id: dict[str, TargetConfig],
) -> ProfileDeclaration:
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError(
            f"Profile {profile_id!r} must declare extends or a workflow"
        )
    extends = _declared_extends(mapping.get("extends"), profile_id)
    workflows: dict[str, TargetSelection] = {}
    for raw_workflow, value in mapping.items():
        if raw_workflow == "extends":
            continue
        workflow = get_workflow(str(raw_workflow))
        workflows[workflow] = _target_selection(
            value,
            profile_id=profile_id,
            workflow=workflow,
            target_by_id=target_by_id,
        )
    return ProfileDeclaration(extends, workflows)


def _profile_declarations(
    raw: Any,
    targets: tuple[TargetConfig, ...],
) -> dict[str, ProfileDeclaration]:
    if not isinstance(raw, dict) or not raw:
        raise ValueError("[profiles] must contain at least one profile")
    target_by_id = {target.id: target for target in targets}
    declarations: dict[str, ProfileDeclaration] = {}
    for raw_profile_id, mapping in raw.items():
        profile_id = str(raw_profile_id)
        declarations[profile_id] = _profile_declaration(profile_id, mapping, target_by_id)
    return declarations


def _snapshot_base(
    profile_id: str,
    parent: str,
    declarations: dict[str, ProfileDeclaration],
    snapshots: dict[str, dict[str, TargetSelection]] | None,
) -> dict[str, TargetSelection] | None:
    """Return the inherited base when the chain ends at ``parent``.

    ``None`` means ``parent`` is declared here and the walk continues into it.
    """
    if parent == profile_id:
        if snapshots is None:
            cycle = [profile_id, profile_id]
            raise ValueError(
                f"Profile inheritance cycle: {' -> '.join(cycle)}"
            )
        if profile_id in snapshots:
            return dict(snapshots[profile_id])
        raise ValueError(
            f"Profile {profile_id!r} extends unknown parent {parent!r}"
        )
    if parent in declarations:
        return None
    if snapshots is not None and parent in snapshots:
        return dict(snapshots[parent])
    raise ValueError(
        f"Profile {profile_id!r} extends unknown parent {parent!r}"
    )


def _walk_profile_chain(
    start_profile: str,
    declarations: dict[str, ProfileDeclaration],
    snapshots: dict[str, dict[str, TargetSelection]] | None,
    memo: dict[str, dict[str, TargetSelection]],
) -> tuple[list[str], dict[str, TargetSelection]]:
    path: list[str] = []
    path_index: dict[str, int] = {}
    profile_id = start_profile
    while True:
        if profile_id in memo:
            return path, dict(memo[profile_id])
        if profile_id in path_index:
            cycle = path[path_index[profile_id]:] + [profile_id]
            raise ValueError(
                f"Profile inheritance cycle: {' -> '.join(cycle)}"
            )
        declaration = declarations[profile_id]
        path_index[profile_id] = len(path)
        path.append(profile_id)
        parent = declaration.extends
        if parent is None:
            return path, {}
        base = _snapshot_base(profile_id, parent, declarations, snapshots)
        if base is not None:
            return path, base
        profile_id = parent


def _resolve_profile_maps(
    declarations: dict[str, ProfileDeclaration],
    *,
    snapshots: dict[str, dict[str, TargetSelection]] | None = None,
) -> dict[str, dict[str, TargetSelection]]:
    memo: dict[str, dict[str, TargetSelection]] = {}
    for start_profile in declarations:
        if start_profile in memo:
            continue
        path, resolved = _walk_profile_chain(start_profile, declarations, snapshots, memo)
        for profile_id in reversed(path):
            resolved = dict(resolved)
            resolved.update(declarations[profile_id].workflows)
            memo[profile_id] = resolved
    return memo


def validate_target_args(
    target_id: str,
    backend: str,
    args: tuple[str, ...],
    *,
    isolated: bool = False,
) -> None:
    """Reject argv that can override transport or isolation boundaries."""
    if not all(isinstance(value, str) for value in args):
        raise ValueError(f"Target {target_id!r} args must contain only strings")
    if any("\x00" in value for value in args):
        raise ValueError(f"Target {target_id!r} args cannot contain NUL bytes")
    if "--" in args:
        raise ValueError(
            f"Target {target_id!r} args cannot contain the reserved '--' token"
        )
    if backend == "codex" and any(
        value in {"--cd", "-C"}
        or value.startswith("--cd=")
        or (value.startswith("-C") and len(value) > 2)
        for value in args
    ):
        raise ValueError(
            f"Codex target {target_id!r} args cannot override the workspace root"
        )
    forbidden_isolated_pi_args = {"--extension", "-e", "--skill", "--prompt-template"}
    if backend == "pi" and isolated and any(
        value in forbidden_isolated_pi_args
        or value.startswith(("--extension=", "--skill=", "--prompt-template="))
        for value in args
    ):
        raise ValueError(
            f"Isolated Pi target {target_id!r} cannot explicitly load extensions, "
            "skills, or prompt templates"
        )


def _validate_env_key(key: Any, context: str) -> None:
    if not isinstance(key, str) or not key:
        raise ValueError(f"Environment key cannot be empty in {context}")
    if "=" in key:
        raise ValueError(f"Environment key cannot contain '=' in {context}")
    if "\x00" in key:
        raise ValueError(f"Environment key cannot contain NUL bytes in {context}")
    if key.startswith("REFRACT_ASK_"):
        raise ValueError(f"Environment keys cannot use protected prefix REFRACT_ASK_ in {context}")


def _validate_env_value(val: Any, context: str) -> None:
    if isinstance(val, bool) or not isinstance(val, str):
        raise ValueError(f"Environment values must be strings in {context}")
    if "\x00" in val:
        raise ValueError(f"Environment values cannot contain NUL bytes in {context}")
    if "${" in val:
        raise ValueError(removed_key_message("${NAME} in targets[].env"))


def _validate_env_mapping(mapping: Any, *, context: str) -> dict[str, str]:
    if not isinstance(mapping, dict):
        raise ValueError(f"{context} must be a TOML table")
    result: dict[str, str] = {}
    for key, val in mapping.items():
        _validate_env_key(key, context)
        _validate_env_value(val, context)
        result[key] = val
    return result


def _reject_removed(key: str) -> None:
    if key in REMOVED_KEYS:
        raise ValueError(removed_key_message(key))


def _retry(raw: Any, target_id: str) -> RetryPolicy:
    if raw is None:
        return RetryPolicy()
    error = ValueError(f"Target {target_id!r} has invalid retry settings")
    if not isinstance(raw, dict) or set(raw) - {"attempts", "codes", "patterns"}:
        raise error
    attempts = raw.get("attempts", 0)
    if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
        raise error
    rules: list[tuple[str, ...]] = []
    for name in ("codes", "patterns"):
        value = raw.get(name, [])
        if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
            raise error
        rules.append(tuple(value))
    return RetryPolicy(attempts, *rules)


def _target_env(raw: Any, target_id: str) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"Target {target_id!r} env must be a TOML table")
    return _validate_env_mapping(raw, context=f"Target {target_id!r} env")


def _target_identity(item: dict[str, Any]) -> tuple[str, str]:
    raw_target_id = item.get("id", "")
    raw_backend = item.get("backend", "")
    target_id = raw_target_id.strip() if isinstance(raw_target_id, str) else ""
    backend = raw_backend.strip() if isinstance(raw_backend, str) else ""
    if not target_id or backend not in {"agy", "codex", "pi", "claude"}:
        # Do not echo the complete declaration: it may contain prompts or
        # other operator-supplied sensitive values.
        raise ValueError("Invalid target declaration")
    return target_id, backend


def _target_text_fields(item: dict[str, Any], target_id: str) -> dict[str, Any]:
    text_fields = {
        "model": item.get("model", ""),
        "reasoning": item.get("reasoning", ""),
        "system_prompt": item.get("system_prompt", ""),
    }
    invalid_text = [
        name for name, value in text_fields.items() if not isinstance(value, str)
    ]
    if invalid_text:
        raise ValueError(
            f"Target {target_id!r} settings must be strings: {invalid_text}"
        )
    return text_fields


def _target_backend_profile(item: dict[str, Any], target_id: str) -> str:
    raw_backend_profile = item.get("backend_profile")
    if raw_backend_profile is None:
        return ""
    if isinstance(raw_backend_profile, str):
        return raw_backend_profile
    raise ValueError(
        f"Target {target_id!r} backend_profile must be a string"
    )


def _target_config(item: Any) -> TargetConfig:
    if not isinstance(item, dict):
        raise ValueError("Each target must be a TOML table")
    target_id, backend = _target_identity(item)
    for key in item:
        _reject_removed(f"targets[].{key}")
    unknown = set(item) - _TARGET_KEYS
    if unknown:
        raise ValueError(f"Unsupported target settings: {sorted(unknown)}")
    args = item.get("args", [])
    if not isinstance(args, list) or not all(isinstance(value, str) for value in args):
        raise ValueError(f"Target {target_id!r} args must be a list of strings")
    isolated = _boolean(item.get("isolated"), False, f"Target {target_id!r} isolated")
    read_only = _boolean(
        item.get("read_only"), False, f"Target {target_id!r} read_only"
    )
    text_fields = _target_text_fields(item, target_id)
    backend_profile = _target_backend_profile(item, target_id)
    validate_target_args(target_id, backend, tuple(args), isolated=isolated)
    return TargetConfig(
        id=target_id,
        backend=backend,
        model=text_fields["model"],
        backend_profile=backend_profile,
        reasoning=text_fields["reasoning"],
        system_prompt=text_fields["system_prompt"],
        isolated=isolated,
        read_only=read_only,
        args=tuple(args),
        max_concurrency=_positive_int(
            item.get("max_concurrency"),
            1,
            f"Target {target_id!r} max_concurrency",
        ),
        context_window=_positive_int(
            item.get("context_window"), None, f"Target {target_id!r} context_window"
        ),
        retry=_retry(item.get("retry"), target_id),
        env=_target_env(item.get("env"), target_id),
    )


def _targets(raw: Any) -> tuple[TargetConfig, ...]:
    if isinstance(raw, dict) and not raw:
        raise ValueError("[targets] must contain at least one target")
    if not isinstance(raw, list):
        raise ValueError("[targets] must be a TOML array of tables")
    if not raw:
        raise ValueError("[targets] must contain at least one target")
    targets = [_target_config(item) for item in raw]
    if len({target.id for target in targets}) != len(targets):
        raise ValueError("Target identifiers must be unique")
    return tuple(targets)


def _logging_file(raw_file: Any, home: Path) -> Path | None:
    if raw_file is None or raw_file is False or str(raw_file).strip().lower() in {
        "",
        "none",
        "off",
    }:
        return None
    if not isinstance(raw_file, str):
        raise ValueError("logging.file must be a path string or false")
    candidate = Path(raw_file).expanduser()
    return candidate if candidate.is_absolute() else home / candidate


def _logging_retention(raw: dict[str, Any]) -> tuple[int, int]:
    try:
        max_bytes = int(raw.get("max_bytes", 10 * 1024 * 1024))
        backup_count = int(raw.get("backup_count", 5))
    except (TypeError, ValueError) as exc:
        raise ValueError("Logging retention settings must be integers") from exc
    if isinstance(raw.get("max_bytes"), bool) or max_bytes < 1:
        raise ValueError("logging.max_bytes must be at least 1")
    if isinstance(raw.get("backup_count"), bool) or backup_count < 0:
        raise ValueError("logging.backup_count must be at least 0")
    return max_bytes, backup_count


def _logging_config(raw: Any, home: Path) -> LoggingConfig:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("[logging] must be a TOML table")
    for key in ("format", "console", "capture_warnings"):
        if key in raw:
            _reject_removed(f"[logging].{key}")
    unknown = set(raw) - {"level", "file", "max_bytes", "backup_count"}
    if unknown:
        raise ValueError(f"Unsupported logging settings: {sorted(unknown)}")
    level = str(raw.get("level", "INFO")).strip().upper()
    if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
        raise ValueError(f"Invalid logging level: {level!r}")
    log_file = _logging_file(raw.get("file", "refract.log"), home)
    max_bytes, backup_count = _logging_retention(raw)
    return LoggingConfig(
        level=level,
        file=log_file,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )


def _notifications_config(raw: Any) -> NotificationsConfig:
    if raw is None:
        return NotificationsConfig()
    if not isinstance(raw, dict):
        raise ValueError("[notifications] must be a TOML table")
    unknown = set(raw) - {"enabled"}
    if unknown:
        raise ValueError(f"Unsupported notifications settings: {sorted(unknown)}")
    if "enabled" in raw and not isinstance(raw["enabled"], bool):
        raise ValueError("notifications.enabled must be true or false")
    return NotificationsConfig(enabled=raw.get("enabled", False))


def _telemetry_config(raw: Any) -> TelemetryConfig:
    if raw is None:
        return TelemetryConfig()
    if not isinstance(raw, dict) or set(raw) - {"enabled", "endpoint"}:
        raise ValueError("Invalid telemetry configuration")
    enabled = raw.get("enabled")
    endpoint = raw.get("endpoint", "https://telemetry.example.invalid/v1/events")
    if enabled is not None and not isinstance(enabled, bool):
        raise ValueError("telemetry.enabled must be true or false")
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise ValueError("telemetry.endpoint must be a non-empty string")
    return TelemetryConfig(enabled, endpoint.strip())


def _pricing_config(raw: Any) -> PricingConfig:
    if raw is None:
        return PricingConfig()
    if not isinstance(raw, dict) or set(raw) - {"currency", "models"}:
        raise ValueError("Invalid pricing configuration")
    currency = raw.get("currency", "USD")
    models = raw.get("models", {})
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("pricing.currency must be a non-empty string")
    if not isinstance(models, dict):
        raise ValueError("pricing.models must be a TOML table")
    parsed: dict[str, ModelPricing] = {}
    for model, values in models.items():
        if not isinstance(values, dict) or set(values) != {"input", "output", "cache_read", "cache_write"}:
            raise ValueError("Invalid pricing model settings")
        prices = []
        for key in ("input", "output", "cache_read", "cache_write"):
            value = values[key]
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0):
                raise ValueError("Pricing values must be non-negative numbers")
            prices.append(float(value))
        parsed[model] = ModelPricing(*prices)
    return PricingConfig(currency=currency.strip(), models=parsed)


def load_config(path: Path | None = None) -> DaemonConfig:
    home = refract_home()
    config_path = path or home / _CONFIG_FILE
    try:
        source = read_config_source(config_path)
    except FileNotFoundError as exc:
        raise ConfigurationLoadError(
            f"Missing config file: {config_path}", path=config_path
        ) from exc
    except OSError as exc:
        raise ConfigurationLoadError(
            f"Unable to read config file: {config_path}", path=config_path
        ) from exc
    return _load_config_source(config_path, home, source)


def load_config_bytes(data: bytes, path: Path) -> DaemonConfig:
    """Load candidate global config bytes as if they were stored at path."""
    source = ConfigSource(
        path=path,
        data=data,
        revision=sha256_bytes(data),
        modification_time="",
        loaded_at=utc_now(),
    )
    return _load_config_source(path, refract_home(), source)


def _load_config_source(
    config_path: Path, home: Path, source: ConfigSource
) -> DaemonConfig:
    try:
        # Decode and parse the same buffer that was hashed above.
        raw = tomllib.loads(source.data.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ConfigurationLoadError(
            f"Invalid config file: {config_path}: invalid UTF-8",
            path=config_path,
            revision=source.revision,
            modification_time=source.modification_time,
            attempted_at=source.loaded_at,
        ) from exc
    except ValueError as exc:
        raise ConfigurationLoadError(
            str(exc),
            path=config_path,
            revision=source.revision,
            modification_time=source.modification_time,
            attempted_at=source.loaded_at,
        ) from exc
    try:
        return _load_config_values(config_path, home, raw, source)
    except ConfigurationLoadError:
        raise
    except ValueError as exc:
        raise ConfigurationLoadError(
            str(exc),
            path=config_path,
            revision=source.revision,
            modification_time=source.modification_time,
            attempted_at=source.loaded_at,
        ) from exc


def _load_config_values(
    config_path: Path, home: Path, raw: dict[str, Any], source: Any
) -> DaemonConfig:
    for key in raw:
        _reject_removed(f"[{key}]")
    unsupported = set(raw) - {
        "daemon",
        "logging",
        "targets",
        "profiles",
        "notifications",
        "telemetry",
        "pricing",
    }
    if unsupported:
        raise ValueError(f"Unsupported config sections: {sorted(unsupported)}")
    daemon = raw.get("daemon", {})
    if not isinstance(daemon, dict):
        raise ValueError("[daemon] must be a TOML table")
    for key in daemon:
        _reject_removed(f"[daemon].{key}")
    unsupported_daemon = set(daemon) - {
        "host",
        "port",
        "max_jobs",
        "default_profile",
        "breaker_failure_threshold",
        "breaker_base_cooldown_s",
        "breaker_max_cooldown_s",
        "ask_timeout_s",
    }
    if unsupported_daemon:
        raise ValueError(f"Unsupported daemon settings: {sorted(unsupported_daemon)}")
    if "targets" not in raw:
        raise ValueError("Missing required [targets] section")
    if "profiles" not in raw:
        raise ValueError("Missing required [profiles] section")
    targets = _targets(raw["targets"])
    profile_declarations = _profile_declarations(raw["profiles"], targets)
    profiles = _resolve_profile_maps(profile_declarations)
    default_profile = str(daemon.get("default_profile", "")).strip()
    if not default_profile:
        raise ValueError("[daemon].default_profile must be set")
    if default_profile not in profiles:
        raise ValueError(
            f"Unknown [daemon].default_profile: {default_profile!r}"
        )
    host = daemon.get("host", "127.0.0.1")
    if not isinstance(host, str) or not host.strip():
        raise ValueError("[daemon].host must be a non-empty string")
    port = _positive_int(daemon.get("port"), DEFAULT_PORT, "[daemon].port")
    if port > 65535:
        raise ValueError("[daemon].port must not exceed 65535")
    breaker_base = _positive_int(daemon.get("breaker_base_cooldown_s"), 60, "[daemon].breaker_base_cooldown_s")
    breaker_max = _positive_int(daemon.get("breaker_max_cooldown_s"), 900, "[daemon].breaker_max_cooldown_s")
    if breaker_max < breaker_base:
        raise ValueError("[daemon].breaker_max_cooldown_s must be >= breaker_base_cooldown_s")
    return DaemonConfig(
        home=home,
        config_path=config_path,
        config_revision=source.revision,
        config_modification_time=source.modification_time,
        config_loaded_at=source.loaded_at,
        host=host.strip(),
        port=port,
        max_jobs=_positive_int(daemon.get("max_jobs"), 4, "[daemon].max_jobs"),
        default_profile=default_profile,
        targets=targets,
        profiles=profiles,
        profile_declarations=profile_declarations,
        logging=_logging_config(raw.get("logging"), home),
        notifications=_notifications_config(raw.get("notifications")),
        telemetry=_telemetry_config(raw.get("telemetry")),
        pricing=_pricing_config(raw.get("pricing")),
        breaker_failure_threshold=_positive_int(daemon.get("breaker_failure_threshold"), 3, "[daemon].breaker_failure_threshold"),
        breaker_base_cooldown_s=breaker_base,
        breaker_max_cooldown_s=breaker_max,
        ask_timeout_s=_positive_int(daemon.get("ask_timeout_s"), DEFAULT_ASK_TIMEOUT_S, "[daemon].ask_timeout_s"),
    )


def load_project_config(
    project_root: Path, base: DaemonConfig, data: bytes | None = None
) -> DaemonConfig:
    """Load a project overlay from disk, or from candidate bytes when given."""
    try:
        return _load_project_config_values(project_root, base, data)
    except ConfigurationLoadError:
        raise
    except ValueError as exc:
        path = project_root / _REFRACT_DIR / _CONFIG_FILE
        raise ConfigurationLoadError(
            str(exc), path=path
        ) from exc


def _project_target_override(
    item: Any,
    target_by_id: dict[str, tuple[int, TargetConfig]],
    seen_target_ids: set[str],
) -> tuple[int, TargetConfig]:
    if not isinstance(item, dict):
        raise ValueError("Each target must be a TOML table")
    raw_target_id = item.get("id")
    target_id = raw_target_id.strip() if isinstance(raw_target_id, str) else ""
    if target_id not in target_by_id:
        raise ValueError(f"Project config cannot add targets: {target_id!r}")
    if target_id in seen_target_ids:
        raise ValueError(f"Duplicate project target override: {target_id!r}")
    seen_target_ids.add(target_id)
    for key in item:
        _reject_removed(f"targets[].{key}")
    unsupported_fields = set(item) - {"id", "env"}
    if unsupported_fields:
        raise ValueError(
            f"Unsupported project target settings: {sorted(unsupported_fields)}"
        )
    idx, base_target = target_by_id[target_id]
    env = dict(base_target.env)
    env.update(_target_env(item.get("env"), target_id))
    return idx, replace(base_target, env=env)


def _project_targets(raw_targets: Any, base: DaemonConfig) -> list[TargetConfig]:
    targets = list(base.targets)
    target_by_id = {t.id: (i, t) for i, t in enumerate(base.targets)}
    if not isinstance(raw_targets, list):
        raise ValueError("[targets] must be a TOML array of tables")
    seen_target_ids: set[str] = set()
    for item in raw_targets:
        idx, override = _project_target_override(item, target_by_id, seen_target_ids)
        targets[idx] = override
    return targets


def _project_profiles(
    raw: dict[str, Any], base: DaemonConfig, targets: list[TargetConfig]
) -> tuple[dict[str, dict[str, TargetSelection]], dict[str, ProfileDeclaration]]:
    profiles = {profile_id: dict(mapping) for profile_id, mapping in base.profiles.items()}
    profile_declarations = dict(base.profile_declarations)
    if "profiles" in raw:
        project_declarations = _profile_declarations(raw["profiles"], tuple(targets))
        project_profiles = _resolve_profile_maps(
            project_declarations,
            snapshots=base.profiles,
        )
        profiles.update(project_profiles)
        profile_declarations.update(project_declarations)
    return profiles, profile_declarations


def _load_project_config_values(
    project_root: Path, base: DaemonConfig, data: bytes | None
) -> DaemonConfig:
    path = project_root / _REFRACT_DIR / _CONFIG_FILE
    if data is None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return base
    raw = tomllib.loads(data.decode("utf-8"))
    for key in raw:
        _reject_removed(f"[{key}]")
    unsupported = set(raw) - {"profiles", "targets"}
    if unsupported:
        raise ValueError(f"Unsupported project config sections: {sorted(unsupported)}")

    targets = _project_targets(raw["targets"], base) if "targets" in raw else list(base.targets)
    profiles, profile_declarations = _project_profiles(raw, base, targets)

    return replace(
        base,
        targets=tuple(targets),
        profiles=profiles,
        profile_declarations=profile_declarations,
    )


def resolve_target_environment(
    catalog: DaemonConfig,
    target: TargetConfig | str,
) -> dict[str, str]:
    """Return the literal environment overrides configured for a target."""
    if isinstance(target, str):
        target = next((item for item in catalog.targets if item.id == target), None)
        if target is None:
            raise ValueError("Unknown target")
    return dict(target.env)


__all__ = [
    "DaemonConfig",
    "LoggingConfig",
    "NotificationsConfig",
    "ProfileDeclaration",
    "RetryPolicy",
    "TargetConfig",
    "TargetSelection",
    "load_config",
    "load_project_config",
    "load_guidance",
    "refract_home",
    "resolve_target_environment",
    "validate_target_args",
]
