from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from openmcp.models import JobResult, JobView, ProjectView, TargetView
from openmcp.server import _DOCTOR_INSTRUCTIONS, _project_root, mcp, workflows_resource


def _serve_config(host: str = "127.0.0.1", port: int = 8765) -> str:
    return f"""[daemon]
host = "{host}"
port = {port}
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
capabilities = ["code", "review", "consult"]

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
other = "primary"
"""


def test_doctor_instructions_do_not_claim_git_ownership() -> None:
    assert "Git" not in _DOCTOR_INSTRUCTIONS
    assert "git" not in _DOCTOR_INSTRUCTIONS
    assert "implement, review, consult, and other" in _DOCTOR_INSTRUCTIONS
    assert "all four workflows" in _DOCTOR_INSTRUCTIONS


def test_workflows_resource_discovers_other(monkeypatch) -> None:
    class Database:
        @staticmethod
        def project(project_id):
            return object()

    runtime = SimpleNamespace(database=Database())
    ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=runtime))
    assert tuple(json.loads(asyncio.run(workflows_resource("project", ctx)))) == (
        "consult", "implement", "other", "review"
    )


def test_project_root_accepts_plain_directory_and_rejects_files(tmp_path) -> None:
    root = tmp_path / "plain-project"
    root.mkdir()
    assert _project_root(str(root)) == root.resolve().as_posix()
    with pytest.raises(ValueError):
        _project_root(str(tmp_path / "missing"))
    file_path = tmp_path / "project.txt"
    file_path.write_text("file\n", encoding="utf-8")
    with pytest.raises(ValueError):
        _project_root(str(file_path))


def test_server_import_does_not_load_daemon_config(tmp_path) -> None:
    env = os.environ.copy()
    env["OPENMCP_HOME"] = str(tmp_path / "missing-home")
    completed = subprocess.run(
        [sys.executable, "-c", "import openmcp.server"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_serve_uses_configured_transport(tmp_path, monkeypatch) -> None:
    from openmcp import cli, server

    home = tmp_path / "openmcp"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("127.0.0.2", 9123), encoding="utf-8")
    monkeypatch.setenv("OPENMCP_HOME", str(home))
    captured: dict[str, object] = {}
    old_host = server.mcp.settings.host
    old_port = server.mcp.settings.port

    def fake_run(*, transport: str) -> None:
        captured["transport"] = transport
        captured["host"] = server.mcp.settings.host
        captured["port"] = server.mcp.settings.port

    monkeypatch.setattr(server.mcp, "run", fake_run)
    try:
        cli.main(["serve"])
    finally:
        server.mcp.settings.host = old_host
        server.mcp.settings.port = old_port

    assert captured == {"transport": "streamable-http", "host": "127.0.0.2", "port": 9123}


def test_serve_cli_transport_overrides_config(tmp_path, monkeypatch) -> None:
    from openmcp import cli, server

    home = tmp_path / "openmcp"
    home.mkdir()
    (home / "config.toml").write_text(_serve_config("127.0.0.2", 9123), encoding="utf-8")
    monkeypatch.setenv("OPENMCP_HOME", str(home))
    captured: dict[str, object] = {}
    old_host = server.mcp.settings.host
    old_port = server.mcp.settings.port

    def fake_run(*, transport: str) -> None:
        captured["transport"] = transport
        captured["host"] = server.mcp.settings.host
        captured["port"] = server.mcp.settings.port

    monkeypatch.setattr(server.mcp, "run", fake_run)
    try:
        cli.main(["serve", "--host", "127.0.0.3", "--port", "9234"])
    finally:
        server.mcp.settings.host = old_host
        server.mcp.settings.port = old_port

    assert captured == {"transport": "streamable-http", "host": "127.0.0.3", "port": 9234}


@pytest.mark.asyncio
async def test_mcp_exposes_direct_job_contract() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    assert "job_integrate" not in tools
    assert set(tools["job_submit"].inputSchema["properties"]) == {"project_id", "workflow", "prompt", "context_key", "profile"}
    assert set(tools["job_wait"].inputSchema["properties"]) == {"job_id", "timeout_s"}
    assert set(tools["job_retry"].inputSchema["properties"]) == {"job_id"}
    assert {"stages", "parent_job_id", "branch", "integration_base", "artifacts", "base_commit"}.isdisjoint(JobView.model_fields)
    assert "commit" not in JobResult.model_fields
    assert {"head_commit", "clean"}.isdisjoint(ProjectView.model_fields)
    capability_key = "capabil" + "ities"
    assert capability_key not in TargetView.model_fields


@pytest.mark.asyncio
async def test_lifespan_clears_state_when_runtime_close_fails(monkeypatch) -> None:
    import openmcp.server as server

    config = SimpleNamespace(logging=object())

    class FailingRuntime:
        def __init__(self, received_config) -> None:
            assert received_config is config

        async def start(self) -> None:
            return None

        async def close(self) -> None:
            raise RuntimeError("close failed")

    monkeypatch.setattr(server, "load_config", lambda: config)
    monkeypatch.setattr(server, "configure_logging", lambda _: None)
    monkeypatch.setattr(server, "Runtime", FailingRuntime)
    server._DAEMON_CONFIG = None
    server._ACTIVE_RUNTIME = None

    try:
        with pytest.raises(RuntimeError, match="close failed"):
            async with server._lifespan(server.mcp):
                assert server._ACTIVE_RUNTIME is not None
        observed = (server._ACTIVE_RUNTIME, server._DAEMON_CONFIG)
    finally:
        server._ACTIVE_RUNTIME = None
        server._DAEMON_CONFIG = None

    assert observed == (None, None)
