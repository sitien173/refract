"""CLI entrypoint for openmcp."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Sequence

from openmcp import server
from openmcp.config import load_config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="openmcp")
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="Run the local MCP daemon")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    commands.add_parser("doctor", help="Inspect daemon prerequisites")
    return parser


def _doctor() -> int:
    config = load_config()
    writable_path = config.home
    while not writable_path.exists() and writable_path != writable_path.parent:
        writable_path = writable_path.parent
    payload = {
        "home": config.home.as_posix(),
        "home_writable": writable_path.is_dir() and os.access(writable_path, os.W_OK),
        "git": shutil.which("git") or "",
        "targets": {
            target.id: {
                "backend": target.backend,
                "executable": shutil.which(target.backend) or "",
            }
            for target in config.targets
        },
    }
    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0 if payload["git"] else 1


def main(argv: Sequence[str] | None = None) -> None:
    """Run the daemon or inspect local prerequisites."""
    args = _parser().parse_args(argv)
    if args.command == "doctor":
        raise SystemExit(_doctor())
    if args.command not in {None, "serve"}:
        raise SystemExit(2)
    if getattr(args, "host", None):
        server.mcp.settings.host = args.host
    if getattr(args, "port", None):
        server.mcp.settings.port = args.port
    try:
        server.mcp.run(transport="streamable-http")
    except KeyboardInterrupt:
        return


__all__ = ["main"]
