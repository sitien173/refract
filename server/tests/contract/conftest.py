"""Harness fixtures for black-box contract tests."""

from __future__ import annotations

import asyncio
import http.client
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests.launchers import install_launcher

SERVER_DIR = Path(__file__).resolve().parents[2]
E2E_BACKEND = SERVER_DIR / "tests" / "fixtures" / "fake_cli" / "e2e_backend.py"


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _render_config(port: int, *, schema_version: bool, extra_toml: str) -> str:
    header = "schema_version = 1\n\n" if schema_version else ""
    content = header + f"""[daemon]
host = "127.0.0.1"
port = {port}
max_jobs = 4
default_profile = "contract"
ask_timeout_s = 15

[logging]
level = "WARNING"

[[targets]]
id = "claude-primary"
backend = "claude"
model = "fake-claude"
retry = {{ attempts = 2, codes = ["service_error"] }}

[[targets]]
id = "claude-secondary"
backend = "claude"
model = "fake-claude-2"
retry = {{ attempts = 1 }}

[[targets]]
id = "agy-nonstream"
backend = "agy"
model = "fake-agy"
retry = {{ attempts = 2, codes = ["service_error"] }}

[[targets]]
id = "codex-primary"
backend = "codex"
model = "fake-codex"
retry = {{ attempts = 1 }}

[[targets]]
id = "codex-retry"
backend = "codex"
model = "fake-codex"
retry = {{ attempts = 2, codes = ["service_error"] }}

[profiles.contract]
consult = {{ targets = ["claude-primary", "claude-secondary"], timeout_s = 30 }}
implement = {{ targets = ["claude-primary", "claude-secondary"], timeout_s = 30 }}
review = {{ targets = ["claude-primary", "claude-secondary"], timeout_s = 30 }}
other = {{ targets = ["claude-primary", "claude-secondary"], timeout_s = 30 }}

[profiles.nonstream]
consult = {{ targets = ["agy-nonstream", "claude-secondary"], timeout_s = 30 }}
implement = {{ targets = ["agy-nonstream", "claude-secondary"], timeout_s = 30 }}
review = {{ targets = ["agy-nonstream", "claude-secondary"], timeout_s = 30 }}
other = {{ targets = ["agy-nonstream", "claude-secondary"], timeout_s = 30 }}

[profiles.codex]
consult = {{ targets = ["codex-primary"], timeout_s = 30 }}
implement = {{ targets = ["codex-primary"], timeout_s = 30 }}
review = {{ targets = ["codex-primary"], timeout_s = 30 }}
other = {{ targets = ["codex-primary"], timeout_s = 30 }}

[profiles.codex-retry]
consult = {{ targets = ["codex-retry"], timeout_s = 30 }}
implement = {{ targets = ["codex-retry"], timeout_s = 30 }}
review = {{ targets = ["codex-retry"], timeout_s = 30 }}
other = {{ targets = ["codex-retry"], timeout_s = 30 }}

[profiles.fallback]
consult = {{ targets = ["claude-secondary", "claude-primary"], timeout_s = 30 }}
implement = {{ targets = ["claude-secondary", "claude-primary"], timeout_s = 30 }}
review = {{ targets = ["claude-secondary", "claude-primary"], timeout_s = 30 }}
other = {{ targets = ["claude-secondary", "claude-primary"], timeout_s = 30 }}
"""
    if extra_toml:
        content += "\n" + extra_toml
    return content


def _wait_for_release(path: Path, timeout_s: float = 10.0) -> None:
    """Wait until no process holds path open.

    On Windows the venv python.exe is a launcher that runs the interpreter as a child, and
    stopping the launcher does not wait for the child to close the database. A rename fails
    with a sharing violation while SQLite still holds the file.
    """
    deadline = time.monotonic() + timeout_s
    probe = path.with_name(path.name + ".release-probe")
    while path.exists() and time.monotonic() < deadline:
        try:
            os.replace(path, probe)
        except PermissionError:
            time.sleep(0.1)
            continue
        os.replace(probe, path)
        return


def doctor_command() -> list[str]:
    return [sys.executable, "-c", "import sys; from refract.cli import main; sys.exit(main())", "doctor"]


def write_config(
    home: Path, *, port: int, extra_toml: str = "", with_schema_version: bool = True
) -> Path:
    """Write the daemon config.toml in one place.

    schema_version = 1 is written unless with_schema_version=False; only the
    missing-version test passes False.
    """
    config_path = home / "config.toml"
    content = _render_config(
        port,
        schema_version=with_schema_version,
        extra_toml=extra_toml,
    )
    config_path.write_text(content, encoding="utf-8")
    return config_path


@dataclass(slots=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


class ContractDaemon:
    """Manages a real subprocess Refract daemon on an ephemeral loopback port."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.home = tmp_path / "refract-home"
        self.home.mkdir(parents=True, exist_ok=True)
        self.bin_dir = tmp_path / "bin"
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir = tmp_path / "e2e-state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.ready_dir = tmp_path / "ready"
        self.ready_dir.mkdir(parents=True, exist_ok=True)
        self.repo = tmp_path / "repo"
        self.repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init"], cwd=self.repo, check=True, capture_output=True)

        for name in ("claude", "agy", "codex", "pi"):
            install_launcher(self.bin_dir, name, E2E_BACKEND)

        self.port = _free_loopback_port()
        self.config_path = write_config(self.home, port=self.port)
        self.log_file = tmp_path / "daemon.log"
        self.process: subprocess.Popen[bytes] | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def mcp_url(self) -> str:
        return f"{self.base_url}/mcp"

    @property
    def db_path(self) -> Path:
        return self.home / "refract.db"

    def ready_file(self, name: str) -> Path:
        return self.ready_dir / name

    def env(self) -> dict[str, str]:
        environment = os.environ.copy()
        for key in ("REFRACT_ASK_URL", "REFRACT_ASK_TOKEN", "REFRACT_ASK_TIMEOUT_S"):
            environment.pop(key, None)
        environment["REFRACT_HOME"] = str(self.home)
        environment["DO_NOT_TRACK"] = "1"
        environment["E2E_STATE_DIR"] = str(self.state_dir)
        environment["E2E_READY_DIR"] = str(self.ready_dir)
        environment["PATH"] = f"{self.bin_dir}{os.pathsep}{environment.get('PATH', '')}"
        return environment

    def start(self, timeout_s: float = 15.0) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        log_handle = self.log_file.open("ab")
        try:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import sys; from refract.cli import main; sys.exit(main())",
                    "serve",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self.port),
                    "--log-file",
                    "-",
                ],
                cwd=SERVER_DIR,
                env=self.env(),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        finally:
            log_handle.close()
        deadline = time.monotonic() + timeout_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                output = self.log_file.read_text(encoding="utf-8", errors="replace") if self.log_file.exists() else ""
                raise RuntimeError(
                    f"Daemon exited early with code {self.process.returncode}:\n{output}"
                )
            try:
                resp = self.http_request("GET", "/dashboard/api/jobs", timeout=1.0)
                if resp.status == 200:
                    return
            except OSError as exc:
                last_error = exc
            time.sleep(0.05)
        output = self.log_file.read_text(encoding="utf-8", errors="replace") if self.log_file.exists() else ""
        raise TimeoutError(f"Daemon did not become ready within {timeout_s}s: {last_error}\n{output}")

    def stop(self, *, kill: bool = False, timeout_s: float = 10.0) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            if kill:
                self.process.kill()
            else:
                self.process.terminate()
            try:
                self.process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        if os.name == "nt":
            _wait_for_release(self.db_path)

    def restart(self, *, kill: bool = False) -> None:
        self.stop(kill=kill)
        self.start()

    def http_request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> HttpResponse:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            req_headers = dict(headers or {})
            payload: bytes | None = None
            if body is not None:
                if isinstance(body, (dict, list)):
                    payload = json.dumps(body).encode("utf-8")
                    req_headers.setdefault("Content-Type", "application/json")
                elif isinstance(body, str):
                    payload = body.encode("utf-8")
                else:
                    payload = body
            conn.request(method, path, body=payload, headers=req_headers)
            resp = conn.getresponse()
            raw = resp.read()
            resp_headers = {k.lower(): v for k, v in resp.getheaders()}
            return HttpResponse(status=resp.status, headers=resp_headers, body=raw)
        finally:
            conn.close()

    async def async_http_request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 10.0,
    ) -> HttpResponse:
        return await asyncio.to_thread(
            self.http_request, method, path, body=body, headers=headers, timeout=timeout
        )

    @asynccontextmanager
    async def mcp_session(self) -> AsyncIterator[ClientSession]:
        async with streamable_http_client(self.mcp_url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session

    def query_db(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Read-only SQLite query against the daemon DB for state not yet exposed via MCP/HTTP."""
        uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()


async def call_tool_json(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call an MCP tool and parse its JSON text response."""
    result = await session.call_tool(name, arguments)
    assert result.content, f"Tool {name} returned empty content"
    text = getattr(result.content[0], "text", "")
    assert text, f"Tool {name} returned non-text content: {result.content[0]}"
    return json.loads(text)


async def wait_for_job(
    session: ClientSession, job_id: str, *, timeout_s: float = 15.0
) -> dict[str, Any]:
    """Call wait using job_ids (Phase 6+) or job_id (Phases 1-5) based on the advertised schema."""
    tools = {t.name: t for t in (await session.list_tools()).tools}
    props = tools["wait"].input_schema.get("properties", {}) if "wait" in tools else {}
    if "job_ids" in props:
        args: dict[str, Any] = {"job_ids": [job_id], "timeout_s": timeout_s}
    else:
        args = {"job_id": job_id, "timeout_s": timeout_s}
    return await call_tool_json(session, "wait", args)


def wait_for_file(path: Path, timeout_s: float = 10.0) -> None:
    """Wait deterministically for a marker file created by a fake CLI."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.02)
    raise TimeoutError(f"Marker file {path} did not appear within {timeout_s}s")


@pytest.fixture
def daemon(tmp_path: Path) -> Iterator[ContractDaemon]:
    instance = ContractDaemon(tmp_path)
    instance.start()
    try:
        yield instance
    finally:
        instance.stop()
