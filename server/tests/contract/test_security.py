"""Contract tests for loopback-only binding and Host/Origin rejection."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.contract.conftest import ContractDaemon, SERVER_DIR, write_config


def test_serve_refuses_non_loopback_and_removes_allow_remote(tmp_path: Path) -> None:
    """refract serve exits non-zero on non-loopback host and --allow-remote is removed."""
    home = tmp_path / "home"
    home.mkdir()
    write_config(home, port=8765)
    env = os.environ.copy()
    env["REFRACT_HOME"] = str(home)
    env["DO_NOT_TRACK"] = "1"

    cli_prefix = [
        sys.executable,
        "-c",
        "import sys; from refract.cli import main; sys.exit(main())",
    ]
    help_proc = subprocess.run(
        [*cli_prefix, "serve", "--help"],
        cwd=SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert help_proc.returncode == 0
    assert "--allow-remote" not in help_proc.stdout

    bad_proc = subprocess.run(
        [*cli_prefix, "serve", "--host", "0.0.0.0"],
        cwd=SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert bad_proc.returncode != 0


def test_mcp_rejects_foreign_host_and_origin(daemon: ContractDaemon) -> None:
    """/mcp accepts a valid loopback initialize request and rejects foreign Host or Origin headers."""
    init_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "contract-test", "version": "1.0"},
        },
    }
    base_headers = {
        "Host": f"127.0.0.1:{daemon.port}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    control = daemon.http_request("POST", "/mcp", body=init_body, headers=base_headers)
    assert control.status == 200

    bad_host = daemon.http_request(
        "POST",
        "/mcp",
        body=init_body,
        headers={**base_headers, "Host": f"evil.example:{daemon.port}"},
    )
    assert 400 <= bad_host.status < 500

    bad_origin = daemon.http_request(
        "POST",
        "/mcp",
        body=init_body,
        headers={**base_headers, "Origin": "https://evil.example"},
    )
    assert 400 <= bad_origin.status < 500
