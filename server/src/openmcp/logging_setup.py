"""Production logging configuration for OpenMCP.

Library modules only acquire namespaced loggers. The application entrypoint owns
handler configuration so importing OpenMCP never changes the process root logger.
"""

from __future__ import annotations

import atexit
import copy
import faulthandler
import json
import logging
import logging.handlers
import os
import queue
import re
import sys
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Protocol


class LoggingOptions(Protocol):
    """Structural type accepted by :func:`configure`."""

    level: str
    format: str
    file: Path | None
    console: bool
    max_bytes: int
    backup_count: int
    capture_warnings: bool


@dataclass(slots=True, frozen=True)
class ResolvedLoggingConfig:
    level: str
    format: str
    file: Path | None
    console: bool
    max_bytes: int
    backup_count: int
    capture_warnings: bool


_CONTEXT_FIELDS = ("request_id", "project_id", "job_id", "stage_id", "target_id")
_CONTEXT: ContextVar[dict[str, str]] = ContextVar("openmcp_log_context", default={})
_STANDARD_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
}
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

_LOG_QUEUE_CAPACITY = 10_000
_LOCK = threading.RLock()
_LISTENER: logging.handlers.QueueListener | None = None
_QUEUE_HANDLER: logging.Handler | None = None
_TARGET_HANDLERS: list[logging.Handler] = []
_CRASH_FILE: Any | None = None
_FAULT_HANDLER_OWNED = False
_CONFIGURED_PID: int | None = None
_FINGERPRINT: tuple[Any, ...] | None = None
_FILE_SINK_DEGRADED = False
_ATEXIT_REGISTERED = False
_WARNING_STATE: tuple[list[logging.Handler], int, bool, bool] | None = None


def _environment_value(name: str) -> str | None:
    value = os.environ.get(name)
    return value if value is not None and value.strip() else None


def _boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _integer(value: str, name: str, *, minimum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if parsed < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return parsed


def resolve_config(options: LoggingOptions | None = None) -> ResolvedLoggingConfig:
    """Resolve logging options with environment variables taking precedence."""
    default_file = Path.home() / ".openmcp" / "openmcp.log"
    level = options.level if options is not None else "INFO"
    log_format = options.format if options is not None else "text"
    file = options.file if options is not None else default_file
    console = options.console if options is not None else False
    max_bytes = options.max_bytes if options is not None else 10 * 1024 * 1024
    backup_count = options.backup_count if options is not None else 5
    capture_warnings = options.capture_warnings if options is not None else True

    if value := _environment_value("OPENMCP_LOG_LEVEL"):
        level = value
    if value := _environment_value("OPENMCP_LOG_FORMAT"):
        log_format = value
    if value := _environment_value("OPENMCP_LOG_FILE"):
        file = None if value.strip().lower() in {"none", "off", "-"} else Path(value)
    if value := _environment_value("OPENMCP_LOG_CONSOLE"):
        console = _boolean(value, "OPENMCP_LOG_CONSOLE")
    if value := _environment_value("OPENMCP_LOG_MAX_BYTES"):
        max_bytes = _integer(value, "OPENMCP_LOG_MAX_BYTES", minimum=1)
    if value := _environment_value("OPENMCP_LOG_BACKUP_COUNT"):
        backup_count = _integer(value, "OPENMCP_LOG_BACKUP_COUNT", minimum=0)
    if value := _environment_value("OPENMCP_LOG_CAPTURE_WARNINGS"):
        capture_warnings = _boolean(value, "OPENMCP_LOG_CAPTURE_WARNINGS")

    resolved_level = str(level).strip().upper()
    if resolved_level not in logging.getLevelNamesMapping() or not isinstance(
        logging.getLevelNamesMapping()[resolved_level], int
    ):
        raise ValueError(f"Invalid logging level: {level!r}")
    resolved_format = str(log_format).strip().lower()
    if resolved_format not in {"text", "json"}:
        raise ValueError("Logging format must be 'text' or 'json'")
    resolved_file = Path(file).expanduser() if file is not None else None
    return ResolvedLoggingConfig(
        level=resolved_level,
        format=resolved_format,
        file=resolved_file,
        # Never permit an accidental configuration with no observable sink.
        console=bool(console or resolved_file is None),
        max_bytes=max(1, int(max_bytes)),
        backup_count=max(0, int(backup_count)),
        capture_warnings=bool(capture_warnings),
    )


def _redact_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 1:
            redacted = pattern.sub("[REDACTED]", redacted)
        else:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


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


def _timestamp(record: logging.LogRecord) -> str:
    return datetime.fromtimestamp(record.created, timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = _CONTEXT.get()
        for field in _CONTEXT_FIELDS:
            if not hasattr(record, field):
                setattr(record, field, context.get(field, ""))
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": _timestamp(record),
            "service": "openmcp",
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_text(record.getMessage()),
            "process_id": record.process,
            "thread": record.threadName,
            "source": {
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            },
        }
        for field in _CONTEXT_FIELDS:
            if value := getattr(record, field, ""):
                payload[field] = _safe_value(value, field)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS and key not in _CONTEXT_FIELDS:
                payload[key] = _safe_value(value, key)
        if record.exc_info:
            payload["exception"] = _redact_text(self.formatException(record.exc_info))
        if record.stack_info:
            payload["stack"] = _redact_text(self.formatStack(record.stack_info))
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


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
        context = " ".join(
            f"{field}={_safe_value(getattr(record, field))}"
            for field in _CONTEXT_FIELDS
            if getattr(record, field, "")
        )
        return f"{rendered} [{context}]" if context else rendered


class _SecureRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Keep newly created files private after every rollover."""

    def _secure_file(self) -> None:
        if os.name != "nt":
            try:
                Path(self.baseFilename).chmod(0o600)
            except OSError:
                pass

    def doRollover(self) -> None:
        super().doRollover()
        self._secure_file()


class _BoundedQueueHandler(logging.handlers.QueueHandler):
    """Preserve exceptions and shed load safely when sinks fall behind."""

    def __init__(self, records: queue.Queue[logging.LogRecord]) -> None:
        super().__init__(records)
        self._drop_lock = threading.Lock()
        self._dropped = 0

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        prepared = copy.copy(record)
        prepared.msg = record.getMessage()
        prepared.args = None
        return prepared

    def _drop_notice(self) -> logging.LogRecord:
        record = logging.LogRecord(
            name="openmcp.logging_setup",
            level=logging.WARNING,
            pathname=__file__,
            lineno=0,
            msg="Dropped %d application log records because sinks were unavailable",
            args=(self._dropped,),
            exc_info=None,
        )
        record.event = "logging.records_dropped"
        record.dropped_records = self._dropped
        return record

    def enqueue(self, record: logging.LogRecord) -> None:
        # QueueHandler's default implementation reports queue.Full through
        # logging's internal stderr path. Count and summarize drops instead.
        with self._drop_lock:
            if self._dropped:
                try:
                    self.queue.put_nowait(self._drop_notice())
                except queue.Full:
                    self._dropped += 1
                    return
                self._dropped = 0
            try:
                self.queue.put_nowait(record)
            except queue.Full:
                self._dropped += 1

    def emit_drop_notice(self, *, block: bool) -> None:
        """Publish pending drop telemetry, including during graceful shutdown."""
        with self._drop_lock:
            if not self._dropped:
                return
            notice = self._drop_notice()
            try:
                if block:
                    self.queue.put(notice, timeout=1.0)
                else:
                    self.queue.put_nowait(notice)
            except queue.Full:
                return
            self._dropped = 0


class _GracefulQueueListener(logging.handlers.QueueListener):
    def enqueue_sentinel(self) -> None:
        # QueueListener uses put_nowait(), which can fail exactly when a bounded
        # queue is under pressure. Block while a healthy listener drains it,
        # but never deadlock shutdown if a sink failure killed that thread.
        if self._thread is not None and self._thread.is_alive():
            self.queue.put(self._sentinel)
            return
        try:
            self.queue.put_nowait(self._sentinel)
        except queue.Full:
            pass


def _formatter(name: str) -> logging.Formatter:
    if name == "json":
        return _JsonFormatter()
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
    global _LISTENER, _QUEUE_HANDLER, _TARGET_HANDLERS
    global _CRASH_FILE, _FAULT_HANDLER_OWNED, _CONFIGURED_PID, _FINGERPRINT
    global _FILE_SINK_DEGRADED, _WARNING_STATE
    logger = logging.getLogger("openmcp")
    if _QUEUE_HANDLER is not None:
        logger.removeHandler(_QUEUE_HANDLER)
        warnings_logger = logging.getLogger("py.warnings")
        warnings_logger.removeHandler(_QUEUE_HANDLER)
    if isinstance(_QUEUE_HANDLER, _BoundedQueueHandler):
        _QUEUE_HANDLER.emit_drop_notice(block=True)
    if _LISTENER is not None:
        try:
            _LISTENER.stop()
        except (AttributeError, RuntimeError):
            pass
    for handler in _TARGET_HANDLERS:
        try:
            handler.flush()
            handler.close()
        except (OSError, ValueError):
            pass
    if _FAULT_HANDLER_OWNED and faulthandler.is_enabled():
        faulthandler.disable()
    if _CRASH_FILE is not None:
        try:
            _CRASH_FILE.close()
        except OSError:
            pass
    if _WARNING_STATE is not None:
        handlers, level, propagate, was_captured = _WARNING_STATE
        warnings_logger = logging.getLogger("py.warnings")
        warnings_logger.handlers[:] = handlers
        warnings_logger.setLevel(level)
        warnings_logger.propagate = propagate
        if not was_captured:
            logging.captureWarnings(False)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    _WARNING_STATE = None
    _LISTENER = None
    _QUEUE_HANDLER = None
    _TARGET_HANDLERS = []
    _CRASH_FILE = None
    _FAULT_HANDLER_OWNED = False
    _CONFIGURED_PID = None
    _FINGERPRINT = None
    _FILE_SINK_DEGRADED = False


def configure(options: LoggingOptions | None = None) -> ResolvedLoggingConfig:
    """Configure OpenMCP's asynchronous rotating logs.

    Calls are idempotent for identical settings and safely replace prior
    OpenMCP-owned handlers when settings change. The process root logger is not
    modified.
    """
    global _LISTENER, _QUEUE_HANDLER, _TARGET_HANDLERS
    global _CRASH_FILE, _FAULT_HANDLER_OWNED, _CONFIGURED_PID, _FINGERPRINT
    global _ATEXIT_REGISTERED, _FILE_SINK_DEGRADED, _WARNING_STATE

    settings = resolve_config(options)
    fingerprint = (
        settings.level,
        settings.format,
        os.fspath(settings.file) if settings.file else None,
        settings.console,
        settings.max_bytes,
        settings.backup_count,
        settings.capture_warnings,
    )
    with _LOCK:
        if (
            _FINGERPRINT == fingerprint
            and _CONFIGURED_PID == os.getpid()
            and not _FILE_SINK_DEGRADED
        ):
            return settings
        _stop_locked()

        formatter = _formatter(settings.format)
        context_filter = _ContextFilter()
        targets: list[logging.Handler] = []
        file_error: OSError | None = None
        if settings.file is not None:
            try:
                _secure_parent(settings.file)
                file_handler = _SecureRotatingFileHandler(
                    settings.file,
                    maxBytes=settings.max_bytes,
                    backupCount=settings.backup_count,
                    encoding="utf-8",
                    delay=False,
                )
                if os.name != "nt":
                    try:
                        settings.file.chmod(0o600)
                    except OSError:
                        pass
                file_handler.setFormatter(formatter)
                file_handler.addFilter(context_filter)
                targets.append(file_handler)
            except OSError as exc:
                file_error = exc
        if settings.console or not targets:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setFormatter(formatter)
            console_handler.addFilter(context_filter)
            targets.append(console_handler)

        records: queue.Queue[logging.LogRecord] = queue.Queue(
            maxsize=_LOG_QUEUE_CAPACITY
        )
        queue_handler = _BoundedQueueHandler(records)
        # Bind context in the producer thread/task; ContextVars intentionally
        # do not flow into the QueueListener's worker thread.
        queue_handler.addFilter(context_filter)
        logger = logging.getLogger("openmcp")
        logger.handlers.clear()
        logger.addHandler(queue_handler)
        logger.setLevel(logging.getLevelNamesMapping()[settings.level])
        logger.propagate = False
        listener = _GracefulQueueListener(
            records,
            *targets,
            respect_handler_level=True,
        )
        listener.start()
        _QUEUE_HANDLER = queue_handler
        _TARGET_HANDLERS = targets
        _LISTENER = listener
        _CONFIGURED_PID = os.getpid()
        _FINGERPRINT = fingerprint
        _FILE_SINK_DEGRADED = file_error is not None

        if settings.capture_warnings:
            warnings_logger = logging.getLogger("py.warnings")
            was_captured = getattr(logging, "_warnings_showwarning", None) is not None
            _WARNING_STATE = (
                list(warnings_logger.handlers),
                warnings_logger.level,
                warnings_logger.propagate,
                was_captured,
            )
            logging.captureWarnings(True)
            warnings_logger.handlers[:] = [queue_handler]
            warnings_logger.setLevel(logging.getLevelNamesMapping()[settings.level])
            warnings_logger.propagate = False

        if settings.file is not None and not faulthandler.is_enabled():
            try:
                crash_path = settings.file.with_name(
                    f"{settings.file.stem}.crash{settings.file.suffix or '.log'}"
                )
                _secure_parent(crash_path)
                _CRASH_FILE = crash_path.open("a", buffering=1, encoding="utf-8")
                if os.name != "nt":
                    crash_path.chmod(0o600)
                faulthandler.enable(file=_CRASH_FILE, all_threads=True)
                _FAULT_HANDLER_OWNED = True
            except OSError as exc:
                logger.warning(
                    "Could not enable crash logging",
                    extra={"event": "logging.crash_file_failed", "error": str(exc)},
                )

        if not _ATEXIT_REGISTERED:
            atexit.register(shutdown)
            _ATEXIT_REGISTERED = True

        logger.info(
            "Application logging configured",
            extra={
                "event": "logging.configured",
                "log_format": settings.format,
                "log_file": os.fspath(settings.file) if settings.file else "",
                "console": settings.console or file_error is not None,
            },
        )
        if file_error is not None:
            logger.warning(
                "File logging unavailable; using stderr",
                extra={"event": "logging.file_failed", "error": str(file_error)},
            )
    return settings


def shutdown() -> None:
    """Flush and close all OpenMCP-owned logging resources."""
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
    """Return an OpenMCP namespaced logger without global side effects."""
    return logging.getLogger(f"openmcp.{name}")


logging.getLogger("openmcp").addHandler(logging.NullHandler())

__all__ = [
    "ResolvedLoggingConfig",
    "configure",
    "get_logger",
    "log_context",
    "resolve_config",
    "shutdown",
]
