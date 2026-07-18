from __future__ import annotations

import json
import logging
import queue
from pathlib import Path

import pytest

import openmcp.logging_setup as logging_setup
from openmcp.config import LoggingConfig, load_config
from openmcp.logging_setup import (
    configure,
    get_logger,
    log_context,
    resolve_config,
    shutdown,
)


@pytest.fixture(autouse=True)
def _close_test_logging():
    shutdown()
    yield
    shutdown()


def test_logging_config_loads_relative_to_openmcp_home(tmp_path, monkeypatch) -> None:
    home = tmp_path / "state"
    home.mkdir()
    path = home / "config.toml"
    path.write_text(
        """
[logging]
level = "debug"
format = "json"
file = "logs/service.jsonl"
console = true
max_bytes = 4096
backup_count = 7
capture_warnings = false
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENMCP_HOME", str(home))

    settings = load_config(path).logging

    assert settings.level == "DEBUG"
    assert settings.format == "json"
    assert settings.file == home / "logs" / "service.jsonl"
    assert settings.console is True
    assert settings.max_bytes == 4096
    assert settings.backup_count == 7
    assert settings.capture_warnings is False


def test_logging_environment_overrides_configuration(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENMCP_LOG_LEVEL", "ERROR")
    monkeypatch.setenv("OPENMCP_LOG_FORMAT", "json")
    monkeypatch.setenv("OPENMCP_LOG_FILE", "off")
    monkeypatch.setenv("OPENMCP_LOG_CONSOLE", "yes")
    monkeypatch.setenv("OPENMCP_LOG_MAX_BYTES", "1234")
    monkeypatch.setenv("OPENMCP_LOG_BACKUP_COUNT", "2")
    options = LoggingConfig(file=tmp_path / "ignored.log")

    settings = resolve_config(options)

    assert settings.level == "ERROR"
    assert settings.format == "json"
    assert settings.file is None
    assert settings.console is True
    assert settings.max_bytes == 1234
    assert settings.backup_count == 2


def test_relative_environment_log_file_uses_openmcp_home(
    tmp_path,
    monkeypatch,
) -> None:
    home = tmp_path / "state"
    monkeypatch.setenv("OPENMCP_HOME", str(home))
    monkeypatch.setenv("OPENMCP_LOG_FILE", "logs/application.log")

    settings = resolve_config(LoggingConfig(file=tmp_path / "configured.log"))

    assert settings.file == home / "logs" / "application.log"


def test_json_logging_has_context_structure_and_redaction(tmp_path) -> None:
    path = tmp_path / "application.jsonl"
    configure(
        LoggingConfig(
            level="INFO",
            format="json",
            file=path,
            capture_warnings=False,
        )
    )
    logger = get_logger("test")

    with log_context(project_id="project-1", job_id="job-1", stage_id="review"):
        logger.warning(
            "request failed authorization=Bearer secret-token-value",
            extra={
                "event": "test.failed",
                "target_id": "target-1",
                "api_key": "sk-thismustnotappear",
                "duration_ms": 12.5,
            },
        )
    shutdown()

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    record = next(item for item in records if item.get("event") == "test.failed")
    assert record["timestamp"].endswith("Z")
    assert record["logger"] == "openmcp.test"
    assert record["project_id"] == "project-1"
    assert record["job_id"] == "job-1"
    assert record["stage_id"] == "review"
    assert record["target_id"] == "target-1"
    assert record["api_key"] == "[REDACTED]"
    assert record["duration_ms"] == 12.5
    assert "secret-token-value" not in json.dumps(record)


def test_configure_retries_a_degraded_file_sink(tmp_path, monkeypatch) -> None:
    path = tmp_path / "recovered.log"
    options = LoggingConfig(file=path, capture_warnings=False)
    real_handler = logging_setup._SecureRotatingFileHandler
    attempts = 0

    def flaky_handler(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("transient sink failure")
        return real_handler(*args, **kwargs)

    monkeypatch.setattr(logging_setup, "_SecureRotatingFileHandler", flaky_handler)

    configure(options)
    configure(options)
    get_logger("recovery").info("file sink recovered")
    shutdown()

    assert attempts == 2
    assert "file sink recovered" in path.read_text(encoding="utf-8")


def test_bounded_queue_summarizes_dropped_records() -> None:
    records: queue.Queue[logging.LogRecord] = queue.Queue(maxsize=1)
    handler = logging_setup._BoundedQueueHandler(records)
    first = logging.makeLogRecord({"msg": "first"})
    second = logging.makeLogRecord({"msg": "second"})

    handler.emit(first)
    handler.emit(second)
    assert records.get_nowait().getMessage() == "first"

    handler.emit_drop_notice(block=False)
    notice = records.get_nowait()
    assert notice.event == "logging.records_dropped"
    assert notice.dropped_records == 1


def test_configure_is_idempotent_and_rotates_files(tmp_path) -> None:
    path = tmp_path / "application.log"
    options = LoggingConfig(
        level="INFO",
        format="text",
        file=path,
        max_bytes=300,
        backup_count=2,
        capture_warnings=False,
    )
    configure(options)
    configure(options)
    logger = get_logger("rotation")
    for index in range(30):
        logger.info("rotation record %s %s", index, "x" * 40)
    shutdown()

    assert path.exists()
    assert list(tmp_path.glob("application.log.*"))
    combined = "".join(
        candidate.read_text(encoding="utf-8")
        for candidate in tmp_path.glob("application.log*")
    )
    assert "rotation record" in combined


def test_invalid_logging_configuration_is_rejected(tmp_path, monkeypatch) -> None:
    home = tmp_path / "state"
    home.mkdir()
    path = home / "config.toml"
    path.write_text("[logging]\nformat = 'xml'\n", encoding="utf-8")
    monkeypatch.setenv("OPENMCP_HOME", str(home))

    with pytest.raises(ValueError, match="format"):
        load_config(path)


def test_shutdown_restores_warning_logger(tmp_path) -> None:
    warnings_logger = logging.getLogger("py.warnings")
    original_handlers = list(warnings_logger.handlers)
    original_level = warnings_logger.level
    original_propagate = warnings_logger.propagate

    configure(LoggingConfig(file=tmp_path / "warning.log", capture_warnings=True))
    shutdown()

    assert warnings_logger.handlers == original_handlers
    assert warnings_logger.level == original_level
    assert warnings_logger.propagate is original_propagate
