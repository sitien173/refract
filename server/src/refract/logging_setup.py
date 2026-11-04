"""Production logging configuration for Refract.

Library modules only acquire namespaced loggers. The application entrypoint owns
handler configuration so importing Refract never changes the process root logger.
"""

from __future__ import annotations

import atexit
import logging
import logging.handlers
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator, Mapping, Protocol


class LoggingOptions(Protocol):
    """Structural type accepted by :func:`configure`."""

    level: str
    file: Path | None
    max_bytes: int
    backup_count: int


@dataclass(slots=True, frozen=True)
class ResolvedLoggingConfig:
    level: str
    file: Path | None
    max_bytes: int
    backup_count: int


_CONTEXT_FIELDS = ("request_id", "project_id", "job_id", "stage_id", "target_id")
_CONTEXT: ContextVar[Mapping[str, str]] = ContextVar("refract_log_context", default=MappingProxyType({}))
_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|password|passwd|secret|token|api[_-]?key|credential)",
    re.IGNORECASE,
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(
        r"(?i)((?:api[_-]?key|token|password|secret|authorization)\s*[:=]\s*)"
        r"([^\s,;]+)"
    ),
    re.compile(r"\b(sk-[A-Za-z0-9_-]{12,})\b"),
)

_LOCK = threading.RLock()
_HANDLERS: list[logging.Handler] = []
_CONFIGURED_PID: int | None = None
_FINGERPRINT: ResolvedLoggingConfig | None = None
_FILE_SINK_DEGRADED = False
_ATEXIT_REGISTERED = False


def _environment_value(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value is not None and value.strip() else None


def _refract_home() -> Path:
    override = _environment_value("REFRACT_HOME")
    return Path(override).expanduser() if override else Path.home() / ".refract"


def _integer(value: str, name: str, *, minimum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return parsed


def _log_file_override(value: str) -> Path | None:
    if value.strip().lower() in {"none", "off", "-"}:
        return None
    candidate = Path(value).expanduser()
    return candidate if candidate.is_absolute() else _refract_home() / candidate


def resolve_config(
    options: LoggingOptions | None = None,
    *,
    overrides: Mapping[str, str] | None = None,
) -> ResolvedLoggingConfig:
    """Resolve CLI overrides before environment variables and configuration."""
    def option(name: str) -> str | None:
        if overrides is not None and name in overrides:
            return overrides[name]
        return _environment_value(name)
    defaults = options if options is not None else ResolvedLoggingConfig(
        level="INFO", file=_refract_home() / "refract.log",
        max_bytes=10 * 1024 * 1024, backup_count=5,
    )
    level = defaults.level
    file = defaults.file
    max_bytes = defaults.max_bytes
    backup_count = defaults.backup_count

    if value := option("REFRACT_LOG_LEVEL"):
        level = value
    if value := option("REFRACT_LOG_FILE"):
        file = _log_file_override(value)
    if value := option("REFRACT_LOG_MAX_BYTES"):
        max_bytes = _integer(value, "REFRACT_LOG_MAX_BYTES", minimum=1)
    if value := option("REFRACT_LOG_BACKUP_COUNT"):
        backup_count = _integer(value, "REFRACT_LOG_BACKUP_COUNT", minimum=0)

    return _resolved_logging_config(level, file, max_bytes, backup_count)


def _resolved_logging_config(
    level: str, file: Path | None, max_bytes: int, backup_count: int,
) -> ResolvedLoggingConfig:
    resolved_level = str(level).strip().upper()
    if resolved_level not in logging.getLevelNamesMapping() or not isinstance(
        logging.getLevelNamesMapping()[resolved_level], int
    ):
        raise ValueError(f"Invalid logging level: {level!r}")
    resolved_file = Path(file).expanduser() if file is not None else None
    return ResolvedLoggingConfig(
        level=resolved_level,
        file=resolved_file,
        max_bytes=max(1, int(max_bytes)),
        backup_count=max(0, int(backup_count)),
    )


def redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 1:
            redacted = pattern.sub("[REDACTED]", redacted)
        else:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


_redact_text = redact_text


def _safe_value(value: Any, key: str = "") -> Any:
    if key and _SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(k): _safe_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe_value(item) for item in value]
    return _redact_text(str(value))


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = _CONTEXT.get()
        for field in _CONTEXT_FIELDS:
            if not hasattr(record, field):
                setattr(record, field, context.get(field, ""))
        return True


class _TextFormatter(logging.Formatter):
    converter = time.gmtime

    def formatException(self, ei: Any) -> str:
        return _redact_text(super().formatException(ei))

    def format(self, record: logging.LogRecord) -> str:
        original_message = record.msg
        original_args = record.args
        try:
            record.msg = _redact_text(record.getMessage())
            record.args = None
            rendered = super().format(record)
        finally:
            record.msg = original_message
            record.args = original_args
        context_fields = [
            f"{field}={_safe_value(getattr(record, field))}"
            for field in _CONTEXT_FIELDS
            if getattr(record, field, "")
        ]
        progress_token_present = getattr(record, "progress_token_present", None)
        if type(progress_token_present) is bool:
            context_fields.append(f"progress_token_present={progress_token_present}")
        context = " ".join(context_fields)
        return f"{rendered} [{context}]" if context else rendered


def _rotate_private_log(source: str, destination: str) -> None:
    """Create the next private log before the stdlib handler reopens it."""
    os.rename(source, destination)
    Path(source).touch(mode=0o600)


def _formatter() -> logging.Formatter:
    return _TextFormatter(
        "%(asctime)s.%(msecs)03dZ %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _secure_parent(path: Path) -> None:
    existed = path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Never change permissions on an operator-managed existing directory such
    # as /var/log. Only harden a directory created for this sink.
    if os.name != "nt" and not existed:
        try:
            path.parent.chmod(0o700)
        except OSError:
            pass


def _stop_locked() -> None:
    global _CONFIGURED_PID, _FINGERPRINT, _FILE_SINK_DEGRADED
    logger = logging.getLogger("refract")
    for handler in _HANDLERS:
        logger.removeHandler(handler)
        try:
            handler.flush()
            handler.close()
        except (OSError, ValueError):
            pass
    _HANDLERS.clear()
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    _CONFIGURED_PID = None
    _FINGERPRINT = None
    _FILE_SINK_DEGRADED = False


def _file_log_handler(
    settings: ResolvedLoggingConfig, formatter: logging.Formatter,
) -> logging.handlers.RotatingFileHandler:
    path = settings.file
    assert path is not None
    _secure_parent(path)
    path.touch(mode=0o600)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=settings.max_bytes, backupCount=settings.backup_count,
        encoding="utf-8", delay=False,
    )
    if os.name != "nt":
        try:
            path.chmod(0o600)
        except OSError:
            pass
    handler.rotator = _rotate_private_log
    handler.setFormatter(formatter)
    return handler


def configure(
    options: LoggingOptions | None = None,
    *,
    overrides: Mapping[str, str] | None = None,
) -> ResolvedLoggingConfig:
    """Configure Refract's rotating log file.

    Calls are idempotent for identical settings and safely replace prior
    Refract-owned handlers when settings change. The process root logger is not
    modified. Without a usable file, logs go to stderr.
    """
    global _CONFIGURED_PID, _FINGERPRINT, _ATEXIT_REGISTERED, _FILE_SINK_DEGRADED

    settings = resolve_config(options, overrides=overrides)
    with _LOCK:
        if (
            _FINGERPRINT == settings
            and _CONFIGURED_PID == os.getpid()
            and not _FILE_SINK_DEGRADED
        ):
            return settings
        _stop_locked()

        formatter = _formatter()
        handler: logging.Handler | None = None
        file_error: OSError | None = None
        if settings.file is not None:
            try:
                handler = _file_log_handler(settings, formatter)
            except OSError as exc:
                file_error = exc
        if handler is None:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(formatter)
        handler.addFilter(_ContextFilter())
        logger = logging.getLogger("refract")
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(logging.getLevelNamesMapping()[settings.level])
        logger.propagate = False
        _HANDLERS.append(handler)
        _CONFIGURED_PID = os.getpid()
        _FINGERPRINT = settings
        _FILE_SINK_DEGRADED = file_error is not None

        if not _ATEXIT_REGISTERED:
            atexit.register(shutdown)
            _ATEXIT_REGISTERED = True

        logger.info(
            "Application logging configured",
            extra={
                "event": "logging.configured",
                "log_file": os.fspath(settings.file) if settings.file else "",
            },
        )
        if file_error is not None:
            logger.warning(
                "File logging unavailable; using stderr",
                extra={"event": "logging.file_failed", "error": str(file_error)},
            )
    return settings


def shutdown() -> None:
    """Flush and close all Refract-owned logging resources."""
    with _LOCK:
        _stop_locked()


@contextmanager
def log_context(**values: Any) -> Iterator[None]:
    """Bind correlation fields to logs in the current async/thread context."""
    current = dict(_CONTEXT.get())
    current.update(
        {
            key: str(value)
            for key, value in values.items()
            if key in _CONTEXT_FIELDS and value not in {None, ""}
        }
    )
    token = _CONTEXT.set(current)
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def get_logger(name: str) -> logging.Logger:
    """Return an Refract namespaced logger without global side effects."""
    return logging.getLogger(f"refract.{name}")


logging.getLogger("refract").addHandler(logging.NullHandler())

__all__ = [
    "ResolvedLoggingConfig",
    "configure",
    "get_logger",
    "log_context",
    "redact_text",
    "resolve_config",
    "shutdown",
]
