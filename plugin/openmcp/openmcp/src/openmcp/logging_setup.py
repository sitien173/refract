"""Centralized logging configuration for openmcp."""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def _resolve_log_path() -> Path:
    override = os.environ.get("OPENMCP_LOG_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".openmcp" / "openmcp.log"


def _resolve_level() -> int:
    raw = os.environ.get("OPENMCP_LOG_LEVEL", "INFO").upper()
    return getattr(logging, raw, logging.INFO)


def configure() -> None:
    """Configure root openmcp logger. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_path = _resolve_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger("openmcp")
    logger.setLevel(_resolve_level())
    logger.propagate = False

    try:
        file_handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as exc:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(fmt)
        logger.addHandler(stderr_handler)
        logger.warning("Falling back to stderr logging: %s", exc)

    try:
        crash_path = log_path.with_name(log_path.stem + ".crash.log")
        crash_fp = open(crash_path, "a", buffering=1, encoding="utf-8")
        faulthandler.enable(file=crash_fp, all_threads=True)
        logger.info("faulthandler enabled, crash traces -> %s", crash_path)
    except OSError as exc:
        logger.warning("faulthandler not enabled: %s", exc)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure()
    return logging.getLogger(f"openmcp.{name}")


__all__ = ["configure", "get_logger"]
