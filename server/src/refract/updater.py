"""Check GitHub for the latest Refract release, cache the result, and print upgrade commands."""

from __future__ import annotations

import http.client
import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from refract.config import refract_home
from refract.installer import _file_lock

RELEASE_URL = "https://api.github.com/repos/sitien173/refract/releases/latest"
RELEASE_HOST = "api.github.com"
MAX_RELEASE_BYTES = 256 * 1024
HTTP_TIMEOUT_S = 10.0
CHECK_TTL_S = 24 * 60 * 60
CACHE_NAME = "update-check.json"

_TAG_RE = re.compile(r"^v?[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}\Z")
_VERSION_RE = re.compile(r"^[0-9]{1,9}\.[0-9]{1,9}\.[0-9]{1,9}\Z")

UPDATE_COMMANDS: tuple[tuple[str, str], ...] = (
    ("server", 'uv tool install --force "refract @ git+https://github.com/sitien173/refract#subdirectory=server"'),
    ("claude", "claude plugin marketplace update refract && claude plugin update refract@refract"),
    ("codex", "codex plugin marketplace upgrade && codex plugin add refract@refract"),
    ("agy", "agy plugin install https://github.com/sitien173/refract"),
    ("agy-ide", "refract uninstall -p agy-ide && refract install -p agy-ide"),
    ("pi", "pi update https://github.com/sitien173/refract"),
)


class _SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Request | None:
        parts = urlsplit(newurl)
        if parts.scheme != "https" or parts.hostname != RELEASE_HOST:
            raise URLError("cross-host redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_release(request: Request, timeout: float) -> Any:
    return build_opener(_SameHostRedirect()).open(request, timeout=timeout)


@dataclass(frozen=True, slots=True)
class _ReleaseResult:
    state: str
    detail: str
    version: str | None = None


def _installed_version() -> str | None:
    try:
        version = metadata.version("refract")
    except metadata.PackageNotFoundError:
        return None
    return version if _VERSION_RE.match(version) else None


def check_release(installed: str | None) -> _ReleaseResult:
    """Compare the latest stable release with ``installed``. Remote text never leaves this function."""
    failed = _ReleaseResult("failed", "cannot check")
    if installed is None or not _VERSION_RE.match(installed):
        return failed
    req = Request(RELEASE_URL, headers={"Accept": "application/vnd.github+json", "User-Agent": "refract-updater"})
    try:
        with _open_release(req, HTTP_TIMEOUT_S) as r: body = r.read(MAX_RELEASE_BYTES + 1)
    except HTTPError as exc:
        return _ReleaseResult("current", "no published release") if exc.code == 404 else failed
    except (http.client.HTTPException, URLError, OSError, ValueError):
        return failed
    if len(body) > MAX_RELEASE_BYTES: return failed
    try:
        release = json.loads(body)
    except ValueError:
        return failed
    if not isinstance(release, dict) or not isinstance(tag := release.get("tag_name"), str): return failed
    if release.get("draft") is True or release.get("prerelease") is True:
        return _ReleaseResult("current", "no stable release")
    if not _TAG_RE.match(tag): return failed
    latest = tag.removeprefix("v")
    if tuple(int(p) for p in latest.split(".")) > tuple(int(p) for p in installed.split(".")):
        return _ReleaseResult("update", f"release {latest} available", latest)
    return _ReleaseResult("current", "up to date", latest)


def write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".update-check-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle)
        os.replace(tmp, path)
    except BaseException:
        with suppress(OSError): os.unlink(tmp)
        raise


def _cache_payload(checked_at: float, result: _ReleaseResult | None) -> dict[str, Any]:
    ver = result.version if result and result.version and _VERSION_RE.match(result.version) else None
    return {"schema": 1, "checked_at": checked_at, "latest_version": ver, "update_available": bool(result and result.state == "update")}


def run_check(*, now: Callable[[], float] | None = None) -> int:
    """Run a quiet, 24-hour-throttled update check and write the cache."""
    path = refract_home() / CACHE_NAME
    try:
        with _file_lock(path.with_name("update-check.lock")) as held:
            if not held: return 0
            checked_at = (now or time.time)()
            if not path.is_symlink():
                with suppress(OSError, ValueError):
                    prev = json.loads(path.read_text())
                    ts = prev.get("checked_at") if isinstance(prev, dict) and prev.get("schema") == 1 else None
                    if not isinstance(ts, bool) and isinstance(ts, (int, float)) and 0 <= checked_at - ts < CHECK_TTL_S:
                        return 0
            write_cache(path, _cache_payload(checked_at, None))
            write_cache(path, _cache_payload(checked_at, check_release(_installed_version())))
    except OSError:
        return 0
    return 0


def run_update(*, now: Callable[[], float] | None = None, out: Callable[[str], None] = print) -> int:
    """Check the latest release, update the cache, and print the per-component upgrade commands."""
    installed = _installed_version()
    result = check_release(installed)
    with suppress(OSError):
        write_cache(refract_home() / CACHE_NAME, _cache_payload((now or time.time)(), result))
    out(
        "Update check failed." if result.state == "failed" else (
            f"Update available: {result.version} (installed {installed})."
            if result.state == "update"
            else f"Up to date: {result.version or result.detail} (installed {installed})."
        )
    )
    for name, command in UPDATE_COMMANDS:
        out(f"{name}: {command}")
    return 0
