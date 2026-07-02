"""Centralized logging configuration for openmcp."""

from __future__ import annotations

import faulthandler
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def _read_openmcp_dotenv_value(key: str) -> str:
    """Read a single key from ~/.openmcp/.env. Cheap and stand-alone so
    logging_setup has no import cycle with server.py."""
    try:
        env_path = Path.home() / ".openmcp" / ".env"
        if not env_path.exists():
            return ""
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            k, value = line.split("=", 1)
            if k.strip() != key:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            return value
    except OSError:
        return ""
    return ""


def _resolve_env(key: str, default: str = "") -> str:
    """Process env > ~/.openmcp/.env > default."""
    value = os.environ.get(key)
    if value is not None and value != "":
        return value
    dotenv_value = _read_openmcp_dotenv_value(key)
    if dotenv_value:
        return dotenv_value
    return default


def _resolve_log_path() -> Path:
    override = _resolve_env("OPENMCP_LOG_FILE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".openmcp" / "openmcp.log"


def _resolve_level() -> int:
    raw = _resolve_env("OPENMCP_LOG_LEVEL", "INFO").upper()
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
