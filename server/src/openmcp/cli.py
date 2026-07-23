"""CLI entrypoint for openmcp."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Sequence

from openmcp.config import DaemonConfig, load_config
from openmcp.logging_setup import configure as configure_logging, get_logger, resolve_config


log = get_logger("cli")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openmcp")
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="Run the local MCP daemon")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default=None,
        help="Override the configured application log level",
    )
    serve.add_argument(
        "--log-format",
        choices=("text", "json"),
        default=None,
        help="Override the configured application log format",
    )
    serve.add_argument(
        "--log-file",
        default=None,
        help="Override the log path; use '-' to disable file logging",
    )
    serve.add_argument(
        "--log-console",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable stderr application logs",
    )
    commands.add_parser("doctor", help="Inspect daemon prerequisites")
    return parser


def _doctor(config: DaemonConfig | None = None) -> int:
    if config is None:
        try:
            config = load_config()
        except ValueError as exc:
            sys.stderr.write(f"Configuration error: {exc}\n")
            return 1
    configure_logging(config.logging)
    logging_config = resolve_config(config.logging)
    writable_path = config.home
    while not writable_path.exists() and writable_path != writable_path.parent:
        writable_path = writable_path.parent
    payload = {
        "home": config.home.as_posix(),
        "home_writable": writable_path.is_dir() and os.access(writable_path, os.W_OK),
        "logging": {
            "level": logging_config.level,
            "format": logging_config.format,
            "file": logging_config.file.as_posix() if logging_config.file else "",
            "console": logging_config.console,
        },
        "targets": {
            target.id: {
                "backend": target.backend,
                "executable": shutil.which(target.backend) or "",
            }
            for target in config.targets
        },
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    log.info(
        "Prerequisite check completed",
        extra={
            "event": "doctor.completed",
            "target_count": len(config.targets),
        },
    )
    return 0


def _apply_logging_overrides(args: argparse.Namespace) -> None:
    overrides = {
        "OPENMCP_LOG_LEVEL": getattr(args, "log_level", None),
        "OPENMCP_LOG_FORMAT": getattr(args, "log_format", None),
        "OPENMCP_LOG_FILE": getattr(args, "log_file", None),
    }
    for name, value in overrides.items():
        if value is not None:
            os.environ[name] = str(value)
    console = getattr(args, "log_console", None)
    if console is not None:
        os.environ["OPENMCP_LOG_CONSOLE"] = "true" if console else "false"


def main(argv: Sequence[str] | None = None) -> None:
    """Run the daemon or inspect local prerequisites."""
    args = _parser().parse_args(argv)
    if args.command == "doctor":
        raise SystemExit(_doctor())
    if args.command not in {None, "serve"}:
        raise SystemExit(2)

    _apply_logging_overrides(args)
    try:
        config = load_config()
    except ValueError as exc:
        sys.stderr.write(f"Configuration error: {exc}\n")
        raise SystemExit(1) from exc
    # Import after configuration so startup uses the final settings.
    from openmcp import server

    server._DAEMON_CONFIG = config
    server.mcp.settings.host = config.host
    server.mcp.settings.port = config.port
    if getattr(args, "host", None) is not None:
        server.mcp.settings.host = args.host
    if getattr(args, "port", None) is not None:
        server.mcp.settings.port = args.port
    log.info(
        "Launching HTTP transport",
        extra={
            "event": "cli.serve",
            "host": server.mcp.settings.host,
            "port": server.mcp.settings.port,
        },
    )
    try:
        server.mcp.run(transport="streamable-http")
    except KeyboardInterrupt:
        log.info("Shutdown requested", extra={"event": "cli.interrupted"})
    except Exception:
        log.exception("Daemon terminated unexpectedly", extra={"event": "cli.failed"})
        raise
    finally:
        server._DAEMON_CONFIG = None


__all__ = ["main"]
