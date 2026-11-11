"""Discover Refract installs, classify them against their upstream, and cache the result.

Nothing here changes an install, pulls a clone, or contacts the daemon. The only
remote call is one GET of the GitHub latest-release endpoint.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, url2pathname

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from refract.config import refract_home
from refract.daemon_control import (
    Endpoint,
    ShutdownFailure,
    wait_until_answers,
)
from refract.daemon_control import configured_endpoint as _configured_endpoint
from refract.daemon_control import daemon_answers as _daemon_answers
from refract.daemon_control import port_open as _port_open
from refract.daemon_control import post_shutdown as _post_shutdown
from refract.daemon_control import read_daemon_file as _read_daemon_file
from refract.daemon_control import shutdown_reply as _shutdown_reply
from refract.daemon_control import spawn_serve as _spawn_serve
from refract.daemon_control import wait_for_stop as _wait_for_stop
from refract.processes import kill_process_tree, prepare_command, process_group_kwargs

RELEASE_URL = "https://api.github.com/repos/sitien173/refract/releases/latest"
RELEASE_HOST = "api.github.com"
MAX_RELEASE_BYTES = 256 * 1024
HTTP_TIMEOUT_S = 10.0
CHECK_TTL_S = 24 * 60 * 60
CACHE_NAME = "update-check.json"
SUBPROCESS_TIMEOUT_S = 15.0
FETCH_TIMEOUT_S = 60.0
APPLY_TIMEOUT_S = 300.0
LATCH_WAIT_S = 10.0
RESTART_WAIT_S = 10.0
LATCH_POST_TIMEOUT_S = 5.0
POLL_S = 0.1

_TAG_RE = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+\Z")
_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+\Z")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}\Z")
_GITHUB_RE = re.compile(
    r"^(?:(?:git\+)?https://(?:www\.)?|git:|ssh://git@|git@)?github\.com[/:]sitien173/refract"
    r"(?:\.git)?/?\Z"
)
_UNTRUSTED = "untrusted source"
_NOT_A_GIT_CLONE = "not a git clone"
_CANNOT_CHECK = "cannot check"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*@[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_SERVER_SPEC = "refract @ git+https://github.com/sitien173/refract{tag}#subdirectory=server"


@dataclass(frozen=True)
class Install:
    """One discovered install. ``state`` is preset when discovery already decided it."""

    name: str
    source: str
    state: str | None
    detail: str
    path: Path | None = None
    uv_tool: bool = False
    scope: str | None = None
    installed_sha: str | None = None
    version: str | None = None
    ref: str | None = None
    marketplace: str | None = None


@dataclass(frozen=True)
class Component:
    name: str
    source: str
    state: str
    detail: str
    cache_only: bool = False


@dataclass(frozen=True)
class CheckResult:
    components: tuple[Component, ...]
    latest_version: str | None
    latest_commit: str | None


# --- subprocess helpers -------------------------------------------------


def _run(args: list[str], timeout: float, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    # npm-style .cmd shims do not start from a bare name; prepare_command swaps in the .ps1 shim.
    resolved = shutil.which(args[0])
    if resolved:
        resolved_args = [resolved, *args[1:]]
        prepared = prepare_command(resolved_args)
        if prepared != resolved_args:
            return _run_tree(prepared, timeout, cwd, env)
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
        env=env,
        check=False,
    )


def _run_tree(
    args: list[str], timeout: float, cwd: Path | None, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run a shim that starts a process tree; on timeout kill the whole tree.

    ``subprocess.run`` kills only the direct child, then waits for every pipe holder to exit.
    """
    with subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=env,
        **process_group_kwargs(),
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_process_tree(process.pid)
            process.communicate()
            raise
        return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)


def _git(root: Path, *args: str, timeout: float = SUBPROCESS_TIMEOUT_S) -> subprocess.CompletedProcess[str] | None:
    """Run git in ``root``; None means git could not run or timed out."""
    try:
        return _run(["git", "-C", str(root), *args], timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def _host_json(executable: str, *args: str) -> tuple[str, Any]:
    """Return ("missing" | "failed" | "ok", parsed JSON or short failure detail)."""
    if shutil.which(executable) is None:
        return "missing", None
    try:
        proc = _run([executable, *args], SUBPROCESS_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return "failed", "timeout"
    except OSError:
        return "failed", "cannot run"
    if proc.returncode != 0:
        return "failed", f"exit {proc.returncode}"
    try:
        return "ok", json.loads(proc.stdout)
    except ValueError:
        return "failed", "malformed output"


# --- source parsing -----------------------------------------------------


def _parse_source(value: object, base: Path | None) -> tuple[str, Path | None] | None:
    """Return ("github", None), ("clone", path), or None when the source is untrusted."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or text.startswith("-"):
        return None
    if _GITHUB_RE.match(text):
        return "github", None
    if text.startswith("file://"):
        text = _file_url_path(text)
    local = text.startswith(("/", "./", "../", "~")) or Path(text).is_absolute()
    if not local and base is not None and ":" not in text and (base / text).exists():
        local = True
    if not local:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        if base is None:
            return None
        path = base / path
    return "clone", path


def _file_url_path(url: str) -> str:
    return url2pathname(urlsplit(url).path)


def _git_root(path: Path) -> Path | None:
    """Canonical git root of ``path``, or None when it is not inside a git work tree."""
    probe = path if path.is_dir() else path.parent
    proc = _git(probe, "rev-parse", "--show-toplevel")
    if proc is None or proc.returncode != 0 or not proc.stdout.strip():
        return None
    return Path(proc.stdout.strip()).resolve()


def _plugin_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("plugins", "installed", "marketplaces"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _item_name(item: dict[str, Any]) -> str:
    raw = item.get("id") or item.get("name") or ""
    return str(raw).split("@", 1)[0]


# --- discovery ----------------------------------------------------------


def _uv_tool_prefix() -> bool:
    if shutil.which("uv") is None:
        return False
    try:
        proc = _run(["uv", "tool", "dir"], SUBPROCESS_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0 or not proc.stdout.strip():
        return False
    return Path(sys.prefix).resolve().is_relative_to(Path(proc.stdout.strip()).resolve())


def discover_server() -> Install:
    uv_tool = _uv_tool_prefix()
    try:
        dist = metadata.distribution("refract")
    except metadata.PackageNotFoundError:
        return Install("server", "unknown", "manual", "refract is not installed as a package", uv_tool=uv_tool)
    version = dist.version if _VERSION_RE.match(dist.version or "") else None
    try:
        direct = json.loads(dist.read_text("direct_url.json") or "")
    except ValueError:
        direct = None
    url = direct.get("url") if isinstance(direct, dict) else None
    if not isinstance(url, str):
        return Install("server", "unknown", "manual", "unknown install source", uv_tool=uv_tool, version=version)
    dir_info = direct.get("dir_info")
    if url.startswith("file://") and isinstance(dir_info, dict) and dir_info.get("editable") is True:
        path = Path(_file_url_path(url))
        root = _git_root(path)
        if root is None:
            return Install("server", "clone", "skipped", _NOT_A_GIT_CLONE, uv_tool=uv_tool, version=version)
        return Install("server", "clone", None, "editable clone", path=root, uv_tool=uv_tool, version=version)
    if _GITHUB_RE.match(url) or url.startswith("https://github.com/sitien173/refract/"):
        return Install("server", "github", None, "github install", uv_tool=uv_tool, version=version)
    return Install("server", "unknown", "manual", "unknown install source", uv_tool=uv_tool, version=version)


def _claude_plugins_file() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    base = Path(override).expanduser() if override else Path.home() / ".claude"
    return base / "plugins" / "installed_plugins.json"


def _installed_records() -> dict[str, list[dict[str, Any]]]:
    try:
        data = json.loads(_claude_plugins_file().read_text())
    except (OSError, ValueError):
        return {}
    plugins = data.get("plugins", data) if isinstance(data, dict) else {}
    if not isinstance(plugins, dict):
        return {}
    return {
        str(key): [r for r in value if isinstance(r, dict)]
        for key, value in plugins.items()
        if isinstance(value, list)
    }


def _record_sha(records: dict[str, list[dict[str, Any]]], plugin_id: str, scope: str | None) -> str | None:
    for record in records.get(plugin_id, []):
        candidate = record.get("gitCommitSha")
        if (scope is None or record.get("scope") == scope) and isinstance(candidate, str):
            return candidate if _SHA_RE.match(candidate) else None
    return None


_MARKETPLACE_KEYS = ("path", "url", "source")


def _item_marketplace(item: dict[str, Any]) -> str:
    plugin_id = str(item.get("id") or item.get("name"))
    return str(item.get("marketplace") or (plugin_id.split("@", 1) + [""])[1])


def _marketplace_source(entry: dict[str, Any]) -> tuple[str, Path | None] | None:
    repo = entry.get("repo")
    if isinstance(repo, str) and repo.strip() and not repo.strip().startswith("-"):
        return _parse_source(f"github.com/{repo.strip()}", None)
    for key in _MARKETPLACE_KEYS:
        if key in entry:
            parsed = _parse_source(entry[key], None)
            if parsed is not None or key != "source":
                return parsed
    return None


def _claude_clone_install(parsed_path: Path | None, common: dict[str, Any]) -> Install:
    root = _git_root(parsed_path) if parsed_path is not None else None
    if root is None:
        return Install("claude", "clone", "skipped", _NOT_A_GIT_CLONE, **common)
    return Install("claude", "clone", None, "clone marketplace", path=root, **common)


def _claude_install(
    item: dict[str, Any], market_sources: dict[str, tuple[str, Path | None] | None], records: Any
) -> Install:
    plugin_id = str(item.get("id") or item.get("name"))
    market = _item_marketplace(item)
    scope = item.get("scope") if isinstance(item.get("scope"), str) else None
    version = item.get("version") if _VERSION_RE.match(str(item.get("version"))) else None
    common = {
        "scope": scope,
        "installed_sha": _record_sha(records, plugin_id, scope),
        "version": version,
        "ref": plugin_id,
        "marketplace": market if _NAME_RE.match(market) else None,
    }
    parsed = market_sources.get(market)
    if parsed is None:
        return Install("claude", "unknown", "skipped", _UNTRUSTED, **common)
    if parsed[0] == "github":
        return Install("claude", "github", None, "github marketplace", **common)
    return _claude_clone_install(parsed[1], common)


def discover_claude() -> list[Install]:
    status, plugins = _host_json("claude", "plugin", "list", "--json")
    if status == "missing":
        return []
    if status == "failed":
        return [Install("claude", "unknown", "failed", f"cannot list plugins: {plugins}")]
    mine = [item for item in _plugin_items(plugins) if _item_name(item) == "refract"]
    if not mine:
        return []
    status, markets = _host_json("claude", "plugin", "marketplace", "list", "--json")
    if status != "ok":
        return [Install("claude", "unknown", "failed", "cannot list marketplaces")]
    market_sources = {str(m.get("name")): _marketplace_source(m) for m in _plugin_items(markets)}
    records = _installed_records()
    return [_claude_install(item, market_sources, records) for item in mine]


def _is_refract_package(path: Path) -> bool:
    for candidate in (path, path / "plugin"):
        try:
            if json.loads((candidate / "package.json").read_text()).get("name") == "refract":
                return True
        except (OSError, ValueError, AttributeError):
            continue
    return False


def _package_version(path: Path) -> str | None:
    try:
        version = json.loads((path / "package.json").read_text()).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return version if isinstance(version, str) and _VERSION_RE.match(version) else None


def _pi_install(entry: Any, base: Path) -> Install | None:
    source = entry.get("source") if isinstance(entry, dict) else entry
    if not isinstance(source, str):
        return None
    parsed = _parse_source(source, base)
    if parsed is None:
        if source.strip().startswith("-") or "refract" in source.lower():
            return Install("pi", "unknown", "skipped", _UNTRUSTED, ref=source)
        return None
    if parsed[0] == "github":
        # Pi clones user-scope git packages to <agent dir>/git/<host>/<path>.
        checkout = base / "git" / "github.com" / "sitien173" / "refract"
        return Install("pi", "github", None, "github package", ref=source, version=_package_version(checkout / "plugin"))
    if not _is_refract_package(parsed[1]):
        return None
    root = _git_root(parsed[1])
    if root is None:
        return Install("pi", "clone", "skipped", _NOT_A_GIT_CLONE, ref=source)
    return Install("pi", "clone", None, "local package", path=root, ref=source)


def _pi_agent_dir() -> Path:
    override = os.environ.get("PI_CODING_AGENT_DIR", "").strip()
    return Path(override).expanduser() if override else Path.home() / ".pi" / "agent"


def discover_pi() -> list[Install]:
    return discover_pi_at(_pi_agent_dir())


def discover_pi_at(base: Path) -> list[Install]:
    """Pi installs recorded in ``base/settings.json``; the installer reads ``<cwd>/.pi`` for ``-l``."""
    try:
        data = json.loads((base / "settings.json").read_text())
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        return [Install("pi", "unknown", "failed", "cannot read settings")]
    packages = data.get("packages") if isinstance(data, dict) else None
    entries = packages if isinstance(packages, list) else []
    return [install for install in (_pi_install(entry, base) for entry in entries) if install is not None]


def discover_detect_only(host: str) -> list[Install]:
    """Codex and agy: detect a Refract plugin and classify it as manual."""
    status, data = _host_json(host, "plugin", "list", "--json")
    if status == "missing":
        return []
    if status == "failed":
        return [Install(host, "unknown", "failed", f"cannot list plugins: {data}")]
    mine = [item for item in _plugin_items(data) if _item_name(item) == "refract"]
    if not mine:
        return []
    plugin_id = str(mine[0].get("id") or "")
    return [Install(host, "unknown", "manual", "manual update required", ref=plugin_id if _ID_RE.match(plugin_id) else None)]


def discover() -> list[Install]:
    return [
        discover_server(),
        *discover_claude(),
        *discover_pi(),
        *discover_detect_only("codex"),
        *discover_detect_only("agy"),
    ]


# --- classification -----------------------------------------------------


@dataclass(frozen=True)
class _CloneResult:
    state: str
    detail: str
    commit: str | None = None


def _clone_blocker(root: Path) -> _CloneResult | None:
    """The reason ``root`` must not be pulled, or None when it is clean, on a branch, and has an upstream."""
    proc = _git(root, "rev-parse", "--absolute-git-dir")
    if proc is None or proc.returncode != 0:
        return _CloneResult("failed", _CANNOT_CHECK)
    git_dir = Path(proc.stdout.strip())
    if any((git_dir / marker).exists() for marker in ("MERGE_HEAD", "rebase-merge", "rebase-apply")):
        return _CloneResult("skipped", "unfinished operation")
    proc = _git(root, "status", "--porcelain")
    if proc is None or proc.returncode != 0:
        return _CloneResult("failed", _CANNOT_CHECK)
    if proc.stdout.strip():
        return _CloneResult("skipped", "dirty")
    proc = _git(root, "symbolic-ref", "-q", "HEAD")
    if proc is None or proc.returncode != 0:
        return _CloneResult("skipped", "detached HEAD")
    proc = _git(root, "rev-parse", "--abbrev-ref", "@{upstream}")
    if proc is None or proc.returncode != 0:
        return _CloneResult("skipped", "no upstream")
    return None


def classify_clone(root: Path) -> _CloneResult:
    blocker = _clone_blocker(root)
    if blocker is not None:
        return blocker
    proc = _git(root, "fetch", timeout=FETCH_TIMEOUT_S)
    if proc is None or proc.returncode != 0:
        return _CloneResult("failed", _CANNOT_CHECK)
    proc = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
    try:
        ahead, behind = (int(n) for n in proc.stdout.split()) if proc and proc.returncode == 0 else (None, None)
    except ValueError:
        ahead = behind = None
    if ahead is None or behind is None:
        return _CloneResult("failed", _CANNOT_CHECK)
    proc = _git(root, "rev-parse", "--short=12", "@{upstream}")
    sha = proc.stdout.strip() if proc is not None and proc.returncode == 0 else ""
    commit = sha if _SHA_RE.match(sha) else None
    if behind == 0:
        return _CloneResult("current", "up to date", commit)
    if ahead > 0:
        return _CloneResult("skipped", "diverged", commit)
    return _CloneResult("update", "behind upstream", commit)


class _SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        parts = urlsplit(newurl)
        if parts.scheme != "https" or parts.hostname != RELEASE_HOST:
            raise URLError("cross-host redirect refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_release(request: Request, timeout: float):  # type: ignore[no-untyped-def]
    return build_opener(_SameHostRedirect()).open(request, timeout=timeout)


@dataclass(frozen=True)
class _ReleaseResult:
    state: str
    detail: str
    version: str | None = None


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def check_release(installed: str | None) -> _ReleaseResult:
    """Compare the latest stable release with ``installed``. Remote text never leaves this function."""
    failed = _ReleaseResult("failed", _CANNOT_CHECK)
    if installed is None or not _VERSION_RE.match(installed):
        return failed
    request = Request(
        RELEASE_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "refract-updater"},
    )
    try:
        with _open_release(request, HTTP_TIMEOUT_S) as response:
            body = response.read(MAX_RELEASE_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 404:
            return _ReleaseResult("current", "no published release")
        return failed
    except (URLError, OSError, ValueError):
        return failed
    if len(body) > MAX_RELEASE_BYTES:
        return failed
    try:
        release = json.loads(body)
    except ValueError:
        return failed
    if not isinstance(release, dict) or not isinstance(release.get("tag_name"), str):
        return failed
    if release.get("draft") is True or release.get("prerelease") is True:
        return _ReleaseResult("current", "no stable release")
    tag = release["tag_name"]
    if not _TAG_RE.match(tag):
        return failed
    latest = tag.removeprefix("v")
    if _version_tuple(latest) > _version_tuple(installed):
        return _ReleaseResult("update", f"release {latest} available", latest)
    return _ReleaseResult("current", "up to date", latest)


def _claude_reinstall_command(plugin_id: str, scope: str | None) -> str:
    """Manual fix for a cache that differs from its clone; non-user scopes act on the cwd project."""
    plugin_id = plugin_id if _ID_RE.match(plugin_id) else "<id>"
    scope = scope if scope and _NAME_RE.match(scope) else None
    manual = " && ".join(
        shlex.join(["claude", "plugin", verb, plugin_id, "-s", scope or "<scope>", *extra])
        for verb, extra in (("uninstall", ["--keep-data"]), ("install", []))
    )
    return f"from the project directory run: {manual}"


def _stale_claude_cache(install: Install, path: Path, heads: dict[Path, str | None]) -> tuple[str, str, bool] | None:
    """(state, detail, cache_only) when the Claude plugin cache differs from the clone HEAD, else None."""
    if path not in heads:
        proc = _git(path, "rev-parse", "HEAD")
        head = proc.stdout.strip() if proc is not None and proc.returncode == 0 else ""
        heads[path] = head if _SHA_RE.match(head) else None
    head = heads[path]
    sha = install.installed_sha or ""
    if not (_SHA_RE.match(sha) and head and not _same_commit(sha, head)):
        return None
    if install.scope == "user":
        return "update", f"plugin cache {sha[:12]} differs from clone {head[:12]}", True
    return "manual", _claude_reinstall_command(install.ref or "<id>", install.scope), False


def _clone_server_version(root: Path) -> str | None:
    try:
        version = tomllib.loads((root / "server" / "pyproject.toml").read_text()).get("project", {}).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return version if isinstance(version, str) and _VERSION_RE.match(version) else None


def _clone_component(
    install: Install, path: Path, clones: dict[Path, _CloneResult], heads: dict[Path, str | None]
) -> tuple[str, str, bool]:
    if path not in clones:
        clones[path] = classify_clone(path)
    result = clones[path]
    if install.name == "claude" and result.state == "current" and install.installed_sha is not None:
        stale = _stale_claude_cache(install, path, heads)
        if stale is not None:
            return stale
    if install.name == "server" and result.state == "current" and install.version is not None:
        # An editable install keeps its metadata version until it is reinstalled.
        cloned = _clone_server_version(path)
        if cloned is not None and cloned != install.version:
            return "update", f"installed {install.version} differs from clone {cloned}", True
    return result.state, result.detail, False


def _release_for(install: Install, server_version: str | None, releases: dict[str, _ReleaseResult]) -> _ReleaseResult:
    installed = install.version or server_version
    key = installed or ""
    if key not in releases:
        releases[key] = check_release(installed)
    return releases[key]


def _newer_version(latest: str | None, candidate: str | None) -> str | None:
    if candidate and (latest is None or _version_tuple(candidate) > _version_tuple(latest)):
        return candidate
    return latest


def classify(installs: list[Install]) -> CheckResult:
    clones: dict[Path, _CloneResult] = {}
    heads: dict[Path, str | None] = {}
    releases: dict[str, _ReleaseResult] = {}
    server_version = next((i.version for i in installs if i.name == "server"), None)
    latest_version: str | None = None
    components = []
    for install in installs:
        state, detail = install.state, install.detail
        cache_only = False
        if state is None and install.source == "clone" and install.path is not None:
            state, detail, cache_only = _clone_component(install, install.path, clones, heads)
        elif state is None:
            rel = _release_for(install, server_version, releases)
            state, detail = rel.state, rel.detail
            latest_version = _newer_version(latest_version, rel.version)
        components.append(Component(install.name, install.source, state or "failed", detail, cache_only))
    server_clone = next((i.path for i in installs if i.name == "server" and i.path in clones), None)
    ordered = ([server_clone] if server_clone is not None else []) + sorted(clones, key=str)
    latest_commit = next((clones[p].commit for p in ordered if clones[p].commit), None)
    return CheckResult(tuple(components), latest_version, latest_commit)


# --- cache --------------------------------------------------------------


def cache_path() -> Path:
    return refract_home() / CACHE_NAME


def read_cache(path: Path) -> dict[str, Any] | None:
    """Return the cache when it is a regular, schema-1 JSON object; otherwise None."""
    if path.is_symlink():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != 1:
        return None
    checked_at = data.get("checked_at")
    if isinstance(checked_at, bool) or not isinstance(checked_at, (int, float)):
        return None
    return data


def _valid(value: object, pattern: re.Pattern[str]) -> str | None:
    return value if isinstance(value, str) and pattern.match(value) else None


def write_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".update-check-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(payload, handle)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _payload(checked_at: float, previous: dict[str, Any] | None, result: CheckResult | None) -> dict[str, Any]:
    prev = previous or {}
    components = (
        [
            {"name": c.name, "source": c.source, "state": c.state, "detail": c.detail}
            for c in result.components
        ]
        if result is not None
        else prev.get("components", [])
    )
    version = (result.latest_version if result else None) or _valid(prev.get("latest_version"), _VERSION_RE)
    commit = (result.latest_commit if result else None) or _valid(prev.get("latest_commit"), _SHA_RE)
    return {
        "schema": 1,
        "checked_at": checked_at,
        "update_available": any(c.get("state") == "update" for c in components if isinstance(c, dict)),
        "latest_version": version if version and _VERSION_RE.match(version) else None,
        "latest_commit": commit if commit and _SHA_RE.match(commit) else None,
        "components": components if isinstance(components, list) else [],
    }


@contextmanager
def _file_lock(path: Path) -> Iterator[bool]:
    """Hold an exclusive non-blocking lock on ``path``; yield False when another process holds it.

    Raises OSError when the lock file cannot be opened, including when it is a symlink.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_NOFOLLOW: a symlinked lock path raises OSError instead of creating or locking the target.
    # Windows has no O_NOFOLLOW, so refuse a symlink explicitly there.
    if not hasattr(os, "O_NOFOLLOW") and path.is_symlink():
        raise OSError(f"{path} is a symlink")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    held = False
    try:
        try:
            if sys.platform == "win32":
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            held = True
        except OSError:
            pass
        yield held
    finally:
        if held:
            try:
                if sys.platform == "win32":
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)


def run_check(
    force: bool = False,
    *,
    now: Callable[[], float] = time.time,
    out: Callable[[str], None] = print,
) -> int:
    """Run the update check. Always returns 0; failures are reported per component."""
    path = cache_path()
    # A separate lock from update.lock: a hook-spawned check must never block ``refract update``.
    with ExitStack() as stack:
        try:
            held = stack.enter_context(_file_lock(path.with_name("update-check.lock")))
        except OSError:
            return 0
        if not held:
            return 0
        previous = read_cache(path)
        checked_at = now()
        if previous is not None and not force and 0 <= checked_at - previous["checked_at"] < CHECK_TTL_S:
            out("update check is fresh; use --force to recheck")
            return 0
        # Record the attempt first so a crash cannot start a second remote check.
        write_cache(path, _payload(checked_at, previous, None))
        result = classify(discover())
        write_cache(path, _payload(checked_at, previous, result))
        for component in result.components:
            out(f"{component.name}: {component.state} ({component.detail})")
    return 0


# --- daemon latch -------------------------------------------------------

_MANUAL_STOP = (
    "The running Refract daemon predates the update latch and cannot be stopped remotely. "
    "Stop the running Refract daemon once by hand, then run refract update again. Nothing was changed."
)
_MAY_BE_STOPPING = "The daemon may be stopping; run: refract serve"
_UNCHANGED = "Nothing was changed."
_Endpoint = Endpoint


def _shutdown_http_failure(code: int) -> str:
    if code == 404:
        return _MANUAL_STOP
    if code == 401:
        return f"Failed: the daemon rejected the runtime token. {_UNCHANGED}"
    if code == 503:
        return f"Failed: the daemon cannot stop on request. {_UNCHANGED}"
    return f"Failed: the daemon answered HTTP {code}. {_UNCHANGED}"


def _shutdown_failure_text(failure: ShutdownFailure) -> str:
    if failure.kind == "http":
        return _shutdown_http_failure(failure.code or 0)
    if failure.kind == "timeout":
        return f"Failed: the daemon did not answer in time. {_MAY_BE_STOPPING} No update was applied."
    return f"Failed: cannot reach the daemon. {_UNCHANGED}"


def _latch(out: Callable[[str], None]) -> tuple[bool, _Endpoint | None]:
    """Latch the daemon shut when idle. Returns (proceed, endpoint of a daemon this run stopped)."""
    info = _read_daemon_file()
    if info is None:
        host, port = _configured_endpoint()
        if _port_open(host, port):
            out(_MANUAL_STOP)
            return False, None
        return True, None
    token, host, port, _pid = info
    raw = _post_shutdown(token, host, port, LATCH_POST_TIMEOUT_S)
    if isinstance(raw, ShutdownFailure):
        out(_shutdown_failure_text(raw))
        return False, None
    if isinstance(raw, bool):
        return raw, None
    reply = _shutdown_reply(raw)
    if reply is None:
        out(f"Failed: the daemon sent an unreadable reply. {_UNCHANGED}")
        return False, None
    stopping, running, queued = reply
    if not stopping:
        out(f"Refused: {running} running, {queued} queued job(s). {_UNCHANGED}")
        return False, None
    if not _wait_for_stop(host, port, LATCH_WAIT_S, POLL_S):
        out(f"Failed: the daemon did not stop in time. {_MAY_BE_STOPPING} No update was applied.")
        return False, None
    return True, (host, port)


# --- apply --------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    name: str
    source: str
    status: str
    detail: str = ""


def _step(args: list[str], timeout: float = APPLY_TIMEOUT_S) -> str | None:
    """Run one apply command; None means success, otherwise a short failure reason."""
    try:
        proc = _run(args, timeout)
    except subprocess.TimeoutExpired:
        return "timeout"
    except (OSError, subprocess.SubprocessError):
        return "cannot run"
    return None if proc.returncode == 0 else f"exit {proc.returncode}"


def _pull(root: Path, pulls: dict[Path, _CloneResult]) -> _CloneResult:
    """Pull ``root`` at most once per run, after rechecking that it is still safe."""
    if root not in pulls:
        blocker = _clone_blocker(root)
        if blocker is not None:
            pulls[root] = blocker
        else:
            proc = _git(root, "pull", "--ff-only", timeout=FETCH_TIMEOUT_S)
            ok = proc is not None and proc.returncode == 0
            pulls[root] = _CloneResult("updated", "") if ok else _CloneResult("failed", "pull failed")
    return pulls[root]


def _manual_command(install: Install) -> str:
    if install.name == "server":
        return shlex.join(["uv", "pip", "install", "-p", sys.executable, _SERVER_SPEC.format(tag="")])
    if install.name == "codex":
        return f"codex plugin marketplace upgrade && codex plugin add {install.ref or 'refract@<marketplace>'}"
    if install.name == "agy":
        return "agy plugin install https://github.com/sitien173/refract"
    return install.detail


def _apply_server(install: Install, result: CheckResult) -> tuple[str, str]:
    if install.source == "clone" and install.path is not None:
        server_dir = install.path / "server"
        if not server_dir.is_dir():
            return "failed", "server directory missing"
        args = ["uv", "pip", "install", "-p", sys.executable, "-e", str(server_dir)]
    elif install.source == "github":
        version = result.latest_version
        if version is None or not _VERSION_RE.match(version):
            return "failed", "no valid release version"
        spec = _SERVER_SPEC.format(tag=f"@v{version}")
        if not install.uv_tool:
            return "manual", shlex.join(["uv", "pip", "install", "-p", sys.executable, spec])
        args = ["uv", "tool", "install", "--force", spec]
    else:
        return "manual", _manual_command(install)
    reason = _step(args)
    return ("failed", f"install failed ({reason})") if reason else ("updated", "")


def _claude_enabled(plugin_id: str, scope: str | None) -> bool | None:
    status, data = _host_json("claude", "plugin", "list", "--json")
    if status != "ok":
        return None
    for item in _plugin_items(data):
        if item.get("id") == plugin_id and (scope is None or item.get("scope") == scope):
            enabled = item.get("enabled")
            return enabled if isinstance(enabled, bool) else None
    return None


def _same_commit(sha: str | None, head: str) -> bool:
    return sha is not None and (head.startswith(sha) or sha.startswith(head))


def _claude_reinstall(plugin_id: str, scope: str, head: str) -> tuple[str, str] | None:
    """Uninstall and reinstall the plugin; a failure result, or None once the cache matches ``head``."""
    restore = shlex.join(["claude", "plugin", "install", plugin_id, "-s", scope])
    reason = _step(["claude", "plugin", "uninstall", plugin_id, "-s", scope, "--keep-data"])
    if reason:
        return "failed", f"uninstall failed ({reason})"
    reason = _step(["claude", "plugin", "install", plugin_id, "-s", scope])
    if reason:
        return "failed", f"reinstall failed ({reason}); restore with: {restore}"
    if not _same_commit(_record_sha(_installed_records(), plugin_id, scope), head):
        return "failed", "plugin cache still differs from the clone"
    return None


def _claude_sync_cache(path: Path, plugin_id: str, scope: str | None) -> tuple[str, str] | None:
    """A failure result, or None once the plugin cache matches the clone HEAD."""
    proc = _git(path, "rev-parse", "HEAD")
    head = proc.stdout.strip() if proc is not None and proc.returncode == 0 else ""
    if not head:
        return "failed", "cannot read the clone HEAD"
    if _same_commit(_record_sha(_installed_records(), plugin_id, scope), head):
        return None
    if scope != "user":
        # Non-user scopes act on the current directory's project; never run them from here.
        manual = _claude_reinstall_command(plugin_id, scope)
        return "failed", f"plugin cache differs from the clone; {manual}"
    return _claude_reinstall(plugin_id, scope, head)


def _claude_enabled_drift(plugin_id: str, scope: str | None, before: bool) -> tuple[str, str] | None:
    """A failure result when the enabled state changed during the update, else None."""
    after = _claude_enabled(plugin_id, scope)
    if after is before:
        return None
    if after is None:
        verb = "install"
    elif before:
        verb = "enable"
    else:
        verb = "disable"
    restore = shlex.join(["claude", "plugin", verb, plugin_id, *(["-s", scope] if scope else [])])
    return "failed", f"enabled state was not preserved; restore with: {restore}"


def _apply_claude(install: Install) -> tuple[str, str]:
    plugin_id, scope = install.ref, install.scope
    if plugin_id is None or not _ID_RE.match(plugin_id):
        return "failed", "invalid plugin id"
    market = install.marketplace
    if market is None or not _NAME_RE.match(market):
        return "failed", "invalid marketplace name"
    before = _claude_enabled(plugin_id, scope)
    for label, args in (
        ("marketplace update", ["claude", "plugin", "marketplace", "update", market]),
        ("plugin update", ["claude", "plugin", "update", plugin_id]),
    ):
        reason = _step(args)
        if reason:
            return "failed", f"{label} failed ({reason})"
    failure = _claude_sync_cache(install.path, plugin_id, scope) if install.source == "clone" and install.path is not None else None
    if failure is None and before is not None:
        failure = _claude_enabled_drift(plugin_id, scope, before)
    return failure or ("updated", "")


def _apply_pi(install: Install) -> tuple[str, str]:
    if install.source == "clone":
        return "updated", ""
    if install.ref is None or install.ref.startswith("-"):
        return "failed", _UNTRUSTED
    reason = _step(["pi", "update", "--extension", install.ref])
    return ("failed", f"pi update failed ({reason})") if reason else ("updated", "")


def _apply_install(install: Install, component: Component, result: CheckResult, pulls: dict[Path, _CloneResult]) -> Outcome:
    def outcome(status: str, detail: str = "") -> Outcome:
        return Outcome(install.name, install.source, status, detail)

    if component.state == "manual":
        return outcome("manual", component.detail if install.name == "claude" else _manual_command(install))
    if component.state != "update":
        return outcome(component.state, component.detail)
    if install.source == "clone" and install.path is not None and not component.cache_only:
        pulled = _pull(install.path, pulls)
        if pulled.state != "updated":
            return outcome(pulled.state, pulled.detail)
    if install.name == "server":
        return outcome(*_apply_server(install, result))
    if install.name == "claude":
        return outcome(*_apply_claude(install))
    if install.name == "pi":
        return outcome(*_apply_pi(install))
    return outcome("failed", "unsupported component")


def _apply_updates(installs: list[Install], result: CheckResult) -> list[Outcome]:
    """Apply every component in isolation; one failure never stops the others."""
    pulls: dict[Path, _CloneResult] = {}
    outcomes = []
    for install, component in zip(installs, result.components):
        try:
            outcomes.append(_apply_install(install, component, result, pulls))
        except Exception:  # noqa: BLE001 - isolate each step; the detail stays generic
            outcomes.append(Outcome(install.name, install.source, "failed", "unexpected error"))
    return outcomes


def _restart() -> bool:
    """Spawn a detached daemon and wait for the `refract status` probe to see it on the configured endpoint."""
    try:
        _spawn_serve()
    except OSError:
        return False
    host, port = _configured_endpoint()
    return wait_until_answers(host, port, RESTART_WAIT_S, POLL_S, _daemon_answers)


def _line(outcome: Outcome) -> str:
    detail = f" {outcome.detail}" if outcome.detail else ""
    return f"{outcome.name} ({outcome.source}): {outcome.status}{detail}"


def run_update(*, out: Callable[[str], None] = print) -> int:
    """Apply every available update. Returns 1 on refusal, any failed component, or a failed restart."""
    lock_path = refract_home() / "update.lock"
    with ExitStack() as stack:
        try:
            held = stack.enter_context(_file_lock(lock_path))
        except OSError:
            out(f"Failed: cannot open {lock_path}. Nothing was changed.")
            return 1
        if not held:
            out("Another refract update is running.")
            return 1
        installs = discover()
        result = classify(installs)
        changing = any(c.state == "update" for c in result.components)
        restarted: bool | None = None
        stopped: _Endpoint | None = None
        if changing:
            proceed, stopped = _latch(out)
            if not proceed:
                return 1
        outcomes = _apply_updates(installs, result)
        if changing and stopped is not None:
            restarted = _restart()
        for outcome in outcomes:
            out(_line(outcome))
        if restarted is not None:
            out("daemon: restarted" if restarted else "daemon: failed cannot restart; run: refract serve")
        if changing:
            out("Restart open Claude Code, Pi, Codex, and agy sessions to load the update.")
            result = classify(discover())
        path = cache_path()
        try:
            write_cache(path, _payload(time.time(), read_cache(path), result))
        except OSError:
            out(f"Warning: could not rewrite {CACHE_NAME}.")
        return 1 if restarted is False or any(o.status == "failed" for o in outcomes) else 0
