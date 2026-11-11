"""Daemon control primitives shared by `refract update` and the daemon stop and restart commands.

Callers own the wording: helpers here return statuses and take timeouts as parameters.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import time
import tomllib
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from urllib.error import HTTPError, URLError

from refract.config import DEFAULT_PORT, refract_home

DAEMON_FILE = "daemon.json"
MAX_REPLY_BYTES = 64 * 1024
SHUTDOWN_POST_TIMEOUT_S = 5.0
STOP_WAIT_S = 10.0
FORCED_STOP_WAIT_S = 30.0
START_WAIT_S = 10.0
POLL_S = 0.1

Endpoint = tuple[str, int]


@dataclass(frozen=True)
class ShutdownFailure:
    """Why a shutdown request failed: `http` (with `code`), `timeout`, or `unreachable`."""

    kind: str
    code: int | None = None


def read_daemon_file() -> tuple[str, str, int, int | None] | None:
    try:
        data = json.loads((refract_home() / DAEMON_FILE).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    token, host, port = data.get("token"), data.get("host"), data.get("port")
    if not (isinstance(token, str) and token and isinstance(host, str) and host):
        return None
    if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
        return None
    pid = data.get("pid")
    if isinstance(pid, bool) or not isinstance(pid, int):
        pid = None
    return token, host, port, pid


def netloc(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def port_open(host: str, port: int) -> bool:
    try:
        socket.create_connection((host, port), timeout=1.0).close()
    except OSError:
        return False
    return True


def open_direct(request: str | urllib.request.Request, timeout: float):  # type: ignore[no-untyped-def]
    """Open a loopback URL without proxies, so the bearer token only ever goes to the daemon."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout)


def daemon_answers(host: str, port: int) -> bool:
    """The `refract status` probe: any HTTP reply means running."""
    try:
        with open_direct(f"http://{netloc(host, port)}/mcp", 2):
            return True
    except HTTPError:
        return True
    except (OSError, URLError):
        return False


def count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def configured_endpoint() -> Endpoint:
    """The daemon host and port from [daemon] in config.toml, without full validation."""
    try:
        daemon = tomllib.loads((refract_home() / "config.toml").read_text()).get("daemon")
    except (OSError, ValueError):
        daemon = None
    daemon = daemon if isinstance(daemon, dict) else {}
    host, port = daemon.get("host"), daemon.get("port")
    ok_port = isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536
    return (host if isinstance(host, str) and host else "127.0.0.1"), (port if ok_port else DEFAULT_PORT)


def post_shutdown(
    token: str, host: str, port: int, timeout: float, *, force: bool = False
) -> bytes | bool | ShutdownFailure:
    """POST the shutdown request. Returns the raw reply, True when nothing is listening, or the failure."""
    request = urllib.request.Request(
        f"http://{netloc(host, port)}/dashboard/api/shutdown",
        data=b'{"force": true}' if force else b"",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if force else {}),
        },
    )
    try:
        with open_direct(request, timeout) as response:
            return response.read(MAX_REPLY_BYTES)
    except HTTPError as exc:
        return ShutdownFailure("http", exc.code)
    except (URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ConnectionRefusedError):
            return True
        return ShutdownFailure("timeout" if isinstance(reason, TimeoutError) else "unreachable")


def shutdown_reply(raw: bytes) -> tuple[bool, int, int] | None:
    """(stopping, running, queued) from the shutdown reply, or None when it is unreadable."""
    try:
        reply = json.loads(raw)
    except ValueError:
        reply = None
    if not isinstance(reply, dict):
        return None
    stopping, running, queued = reply.get("stopping"), count(reply.get("running")), count(reply.get("queued"))
    if not isinstance(stopping, bool) or running is None or queued is None:
        return None
    return stopping, running, queued


def wait_for_stop(host: str, port: int, wait_s: float, poll_s: float) -> bool:
    """True once the daemon file is gone and the port is closed; False after `wait_s`."""
    deadline = time.monotonic() + wait_s
    while (refract_home() / DAEMON_FILE).exists() or port_open(host, port):
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_s)
    return True


def spawn_serve() -> None:
    subprocess.Popen(
        [shutil.which("refract") or "refract", "serve"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def wait_until_answers(
    host: str,
    port: int,
    wait_s: float,
    poll_s: float,
    answers: Callable[[str, int], bool] | None = None,
) -> bool:
    """True once the daemon answers the probe; False after `wait_s`."""
    probe = daemon_answers if answers is None else answers
    deadline = time.monotonic() + wait_s
    while not probe(host, port):
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_s)
    return True
