"""Install and remove the Refract plugin by driving each host's own CLI.

Each host is probed read-only, turned into an ordered list of argv lists, and then
executed or, with ``--dry-run``, printed. Refract never writes host files itself,
with one exception: ``agy-ide``. The standalone Antigravity IDE exposes no plugin CLI,
so Refract copies the plugin directory into place and removes only a directory it
copied, which it recognises by an ownership marker written at install.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from refract import updater
from refract.config import refract_home

DEFAULT_SOURCE = "https://github.com/sitien173/refract"
MARKETPLACE_REPO = "sitien173/refract"
MARKETPLACE = "refract"
PLUGIN_ID = "refract@refract"
HOSTS = ("claude", "codex", "agy", "agy-ide", "pi")
SCOPES = ("user", "project", "local")
_SCOPES_BY_HOST = {
    "claude": SCOPES,
    "pi": ("user", "project"),
    "codex": ("user",),
    "agy": ("user",),
    "agy-ide": ("user", "project"),
}
# Written into the copied tree so a removal can tell a Refract copy from the `agy` CLI's own
# install at the same path. The dotted, Refract-specific name is not an Antigravity file.
_AGY_IDE_MARKER = ".refract-agy-ide-install.json"
_SOURCE_KEYS = ("repo", *updater._MARKETPLACE_KEYS)
_ALREADY_INSTALLED = "already installed"
_NOT_INSTALLED = "not installed"
# Verbs for `<host> plugin <verb>` on the hosts that use a marketplace.
_VERBS = {"claude": ("install", "uninstall"), "codex": ("add", "remove")}


@dataclass(frozen=True, slots=True)
class _Step:
    argv: list[str]
    undo: list[str] | None = None


@dataclass(frozen=True, slots=True)
class _FileStep:
    """A file operation: ``copy`` the tree at ``src`` to ``dst``, or ``remove`` ``dst``."""

    kind: Literal["copy", "remove"]
    src: Path | None
    dst: Path


@dataclass(frozen=True, slots=True)
class _Plan:
    steps: list[_Step | _FileStep]
    noop: str = ""
    done: str = ""
    error: str | None = None
    notes: tuple[str, ...] = ()


def _is_remote(source: str) -> bool:
    return "://" in source or source.startswith("git@")


def resolve_source(value: str | None) -> str:
    """The default URL, a URL or git address as given, or a local path made absolute."""
    if value is None:
        return DEFAULT_SOURCE
    if _is_remote(value):
        return value
    return str(Path(value).expanduser().resolve())


def marketplace_arg(source: str) -> str:
    """The Claude and Codex marketplace argument: the short repo name for the default source."""
    return MARKETPLACE_REPO if source == DEFAULT_SOURCE else source


# --- agy-ide ------------------------------------------------------------------


def _agy_ide_present() -> bool:
    """Whether the Antigravity IDE has left its config directories under the home directory."""
    gemini = Path.home() / ".gemini"
    return (gemini / "antigravity-ide").exists() or (gemini / "config").exists()


def _agy_ide_destination(scope: str) -> Path:
    if scope == "user":
        return Path.home() / ".gemini" / "config" / "plugins" / "refract"
    return Path.cwd() / ".agents" / "plugins" / "refract"


def _agy_ide_plugin_root(source: str) -> Path | None:
    """The directory holding ``.antigravity-plugin/plugin.json``: the source or its ``plugin/``."""
    base = Path(source)
    for root in (base, base / "plugin"):
        if (root / ".antigravity-plugin" / "plugin.json").is_file():
            return root
    return None


def _agy_ide_has_refract_manifest(dst: Path) -> bool:
    for manifest in (dst / ".antigravity-plugin" / "plugin.json", dst / "plugin.json"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("name") == "refract":
            return True
    return False


def _is_link(path: Path) -> bool:
    return path.is_symlink() or os.path.isjunction(path)


def _agy_ide_owned(dst: Path) -> bool:
    """Whether Refract copied ``dst``: a regular marker file that names ``dst`` itself.

    A marker without a ``path`` key, or naming another location, travelled with a copy of the
    tree and proves nothing.
    """
    marker_path = dst / _AGY_IDE_MARKER
    if marker_path.is_symlink() or not marker_path.is_file():
        return False
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(marker, dict) or marker.get("owner") != "refract":
        return False
    return marker.get("path") == str(dst.resolve())


def _plan_agy_ide(action: str, source: str, scope: str) -> _Plan:
    dst = _agy_ide_destination(scope)
    installed = _agy_ide_has_refract_manifest(dst)
    if action == "uninstall":
        if _is_link(dst):
            return _Plan([], error=f"{dst} is a link; not removing it")
        if not dst.exists():
            return _Plan([], noop="not installed")
        if not installed:
            return _Plan([], error=f"{dst} is not a Refract plugin; not removing it")
        if not _agy_ide_owned(dst):
            reason = "has no Refract install marker for this location, so it belongs to another tool"
            return _Plan([], error=f"{dst} {reason}; not removing it")
        return _Plan([_FileStep("remove", None, dst)], done="removed")
    if _is_remote(source):
        return _Plan([], error="agy-ide needs a local path source; pass --source <path>")
    root = _agy_ide_plugin_root(source)
    if root is None:
        return _Plan([], error=f"no .antigravity-plugin/plugin.json in {source} or its plugin/")
    if installed:
        return _Plan([], noop="already installed")
    if dst.resolve().is_relative_to(root.resolve()):
        return _Plan([], error=f"destination {dst} is inside the source {root}; copy would recurse")
    return _Plan([_FileStep("copy", root, dst)], done="installed")


# --- host selection -----------------------------------------------------------


def _usage(message: str) -> int:
    sys.stderr.write(f"{message}\n")
    return 2


def _expand_hosts(values: Sequence[str]) -> list[str] | None:
    """Split comma lists, expand ``all`` to the hosts on PATH, dedupe in first-seen order."""
    hosts: list[str] = []
    for token in (part.strip() for value in values for part in value.split(",")):
        if token == "all":
            names = [host for host in HOSTS if _host_present(host)]
        elif token in HOSTS:
            names = [token]
        else:
            return None
        hosts.extend(name for name in names if name not in hosts)
    return hosts


def _host_present(host: str) -> bool:
    return _agy_ide_present() if host == "agy-ide" else shutil.which(host) is not None


def _scope_error(hosts: Sequence[str], scope: str) -> str | None:
    bad = [host for host in hosts if scope not in _SCOPES_BY_HOST[host]]
    return f"--scope {scope} is not supported for {', '.join(bad)}" if bad else None


# --- probes -------------------------------------------------------------------


def _probe(host: str, *args: str) -> list[dict[str, Any]] | None:
    status, data = updater._host_json(host, *args)
    return updater._plugin_items(data) if status == "ok" else None


def _installed(host: str, scope: str) -> tuple[list[updater.Install], str | None]:
    """Existing installs of the plugin in ``scope``, and the reason discovery failed, if it did."""
    if host == "claude":
        found = updater.discover_claude()
    elif host == "pi":
        base = updater._pi_agent_dir() if scope == "user" else Path.cwd() / ".pi"
        found = updater.discover_pi_at(base)
    elif host == "codex":
        found = _codex_installs()
    else:
        found = updater.discover_detect_only(host)
    failed = next((item.detail for item in found if item.state == "failed"), None)
    if failed:
        # A launch failure reads "cannot list plugins: cannot run"; report the host failing to run.
        return [], f"cannot run {host}" if failed.endswith("cannot run") else failed
    mine = [item for item in found if item.scope in (None, scope)]
    if host in _VERBS:
        mine = [item for item in mine if _is_refract_plugin(item)]
    return mine, None


def _codex_installs() -> list[updater.Install]:
    """Codex installs read from the raw plugin list, which discovery trims to its first item."""
    status, data = updater._host_json("codex", "plugin", "list", "--json")
    if status == "failed":
        return [updater.Install("codex", "unknown", "failed", f"cannot list plugins: {data}")]
    items = updater._plugin_items(data) if status == "ok" else []
    # A bare name or an empty marketplace is accepted; refract@other is another plugin.
    mine = any(
        updater._item_name(item) == "refract"
        and updater._item_marketplace(item) in (MARKETPLACE, "")
        for item in items
    )
    return [updater.Install("codex", "unknown", "manual", "", ref=PLUGIN_ID)] if mine else []


def _is_refract_plugin(item: updater.Install) -> bool:
    """True for ``refract@refract``; ``refract@other`` is a different plugin."""
    return item.ref == PLUGIN_ID if item.ref else item.marketplace == MARKETPLACE


def _source_text(entry: dict[str, Any]) -> str:
    return next((str(entry[key]) for key in _SOURCE_KEYS if key in entry), "unknown")


def _same_source(entry: dict[str, Any], source: str) -> bool:
    have, want = updater._marketplace_source(entry), updater._parse_source(source, None)
    if have is None or want is None:
        wanted = (source, marketplace_arg(source))
        return any(entry.get(key) in wanted for key in _SOURCE_KEYS)
    if have[0] != want[0]:
        return False
    return have[0] == "github" or Path(str(have[1])).resolve() == Path(str(want[1])).resolve()


# --- plans --------------------------------------------------------------------


def _cmd(host: str, *words: str, flag: str = "", scope: str = "user") -> list[str]:
    """``<host> plugin <words>``; Claude takes the scope through ``flag``, the others take none."""
    return [host, "plugin", *words, *([flag, scope] if flag and host == "claude" else [])]


def _find_marketplace(markets: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((m for m in markets if m.get("name") == MARKETPLACE), None)


def _plan_market_install(host: str, source: str, scope: str) -> _Plan:
    installed, failure = _installed(host, scope)
    if failure:
        return _Plan([], error=failure)
    if installed:
        return _Plan([], noop=_ALREADY_INSTALLED)
    verbs = _VERBS[host]
    steps: list[_Step] = []
    markets = _probe(host, "plugin", "marketplace", "list", "--json")
    if markets is None:
        return _Plan([], error="cannot list marketplaces")
    entry = _find_marketplace(markets)
    if entry is None:
        add = _cmd(host, "marketplace", "add", marketplace_arg(source), flag="--scope", scope=scope)
        undo = _cmd(host, "marketplace", "remove", MARKETPLACE, flag="--scope", scope=scope)
        steps.append(_Step(add, undo))
    elif not _same_source(entry, source):
        have, want = _source_text(entry), marketplace_arg(source)
        return _Plan([], error=f"marketplace {MARKETPLACE} has source {have}, wanted {want}")
    install = _cmd(host, verbs[0], PLUGIN_ID, flag="-s", scope=scope)
    steps.append(_Step(install, _cmd(host, verbs[1], PLUGIN_ID, flag="-s", scope=scope)))
    return _Plan(steps, done="installed")


def _is_target(item: dict[str, Any], host: str, scope: str) -> bool:
    market = updater._item_marketplace(item)
    plugin = updater._item_name(item) == "refract" and market == MARKETPLACE
    return plugin and (host != "claude" or item.get("scope") in (None, scope))


def _is_other_plugin(item: dict[str, Any], host: str, scope: str) -> bool:
    return updater._item_marketplace(item) == MARKETPLACE and not _is_target(item, host, scope)


def _is_refract_source(entry: dict[str, Any]) -> bool:
    parsed = updater._marketplace_source(entry)
    if parsed is None:
        return False
    return parsed[0] == "github" or updater._is_refract_package(Path(str(parsed[1])))


def _marketplace_removal(host: str, scope: str) -> tuple[list[_Step], tuple[str, ...]]:
    """The marketplace removal step, or a note saying why the marketplace stays."""
    markets = _probe(host, "plugin", "marketplace", "list", "--json")
    plugins = _probe(host, "plugin", "list", "--json")
    if markets is None or plugins is None:
        return [], (f"marketplace {MARKETPLACE} kept: cannot confirm it is unused",)
    entry = _find_marketplace(markets)
    if entry is None:
        return [], ()
    if not _is_refract_source(entry):
        reason = f"source {_source_text(entry)} is not a Refract source"
    elif any(_is_other_plugin(p, host, scope) for p in plugins):
        reason = "another plugin from it is still installed"
    else:
        remove = _cmd(host, "marketplace", "remove", MARKETPLACE, flag="--scope", scope=scope)
        return [_Step(remove)], ()
    return [], (f"marketplace {MARKETPLACE} kept: {reason}",)


def _plan_market_uninstall(host: str, scope: str) -> _Plan:
    installed, failure = _installed(host, scope)
    if failure:
        return _Plan([], error=failure)
    if not installed:
        return _Plan([], noop=_NOT_INSTALLED)
    remove_plugin = _cmd(host, _VERBS[host][1], PLUGIN_ID, flag="-s", scope=scope)
    reinstall = _cmd(host, _VERBS[host][0], PLUGIN_ID, flag="-s", scope=scope)
    steps, notes = _marketplace_removal(host, scope)
    return _Plan([_Step(remove_plugin, reinstall), *steps], done="removed", notes=notes)


def _plan_agy(action: str, source: str, scope: str) -> _Plan:
    installed, failure = _installed("agy", scope)
    if failure:
        return _Plan([], error=failure)
    if action == "install":
        if installed:
            return _Plan([], noop=_ALREADY_INSTALLED)
        return _Plan([_Step(["agy", "plugin", "install", source])], done="installed")
    if not installed:
        return _Plan([], noop=_NOT_INSTALLED)
    return _Plan([_Step(["agy", "plugin", "uninstall", "refract"])], done="removed")


def _plan_pi(action: str, source: str, scope: str) -> _Plan:
    installed, failure = _installed("pi", scope)
    if failure:
        return _Plan([], error=failure)
    flag = ["-l"] if scope == "project" else []
    if action == "install":
        if installed:
            return _Plan([], noop=_ALREADY_INSTALLED)
        return _Plan([_Step(["pi", "install", source, *flag])], done="installed")
    # The stored string is passed back unchanged; Pi matches packages on it.
    refs = list(dict.fromkeys(item.ref for item in installed if item.ref))
    if not refs:
        return _Plan([], noop=_NOT_INSTALLED)
    return _Plan([_Step(["pi", "remove", ref, *flag]) for ref in refs], done="removed")


def _plan(host: str, action: str, source: str, scope: str) -> _Plan:
    if host == "agy":
        return _plan_agy(action, source, scope)
    if host == "agy-ide":
        return _plan_agy_ide(action, source, scope)
    if host == "pi":
        return _plan_pi(action, source, scope)
    if action == "install":
        return _plan_market_install(host, source, scope)
    return _plan_market_uninstall(host, scope)


# --- execution ----------------------------------------------------------------


def _apply(argv: list[str]) -> str | None:
    """Run one mutating command; return the failure reason, or None on success."""
    try:
        proc = updater._run(argv, updater.APPLY_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return f"{argv[0]} timed out"
    except OSError:
        return f"cannot run {argv[0]}"
    if proc.returncode == 0:
        return None
    detail = next(iter(reversed(proc.stderr.strip().splitlines())), "")
    suffix = f": {detail[:200]}" if detail else ""
    return f"{shlex.join(argv)} exited {proc.returncode}{suffix}"


def _report_failure(
    host: str, reason: str, applied: list[_Step | _FileStep], out: Callable[[str], None]
) -> None:
    out(f"{host}: failed: {reason}")
    for step in applied:
        text = _file_step_text(step) if isinstance(step, _FileStep) else shlex.join(step.argv)
        out(f"{host}: applied: {text}")
    for step in reversed(applied):
        if isinstance(step, _Step) and step.undo:
            out(f"{host}: undo: {shlex.join(step.undo)}")


def _clear_readonly_and_retry(func: Callable[..., Any], path: str, exc: BaseException) -> None:
    """``rmtree`` error handler: make the entry and its parent writable, then retry once."""
    if not isinstance(exc, PermissionError):
        raise exc
    for target in (Path(path).parent, Path(path)):
        if not _is_link(target):
            target.chmod(target.lstat().st_mode | stat.S_IRWXU)
    func(path)


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, onexc=_clear_readonly_and_retry)


def _remove_owned(dst: Path) -> str | None:
    """Rename ``dst`` aside, which either fully happens or changes nothing, then delete it."""
    if _is_link(dst):
        return f"{dst} is a link; not removing it"
    if not _agy_ide_owned(dst):
        return f"{dst} has no Refract install marker for this location; not removing it"
    aside = dst.parent / f".refract-removing-{uuid.uuid4().hex}"
    try:
        dst.rename(aside)
    except OSError as exc:
        return f"cannot remove {dst}: {exc}"
    try:
        _rmtree(aside)
    except OSError as exc:
        return f"removed {dst} from the plugin path but cannot delete {aside}: {exc}"
    return None


def _copy_owned(src: Path, dst: Path) -> str | None:
    """Copy ``src`` to a sibling staging directory, mark it, and rename it to ``dst``."""
    if dst.exists() or _is_link(dst):
        return f"{dst} already exists; not replacing it"
    staging: Path | None = None
    renamed = False
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".refract-staging-", dir=dst.parent))
        shutil.copytree(src, staging, dirs_exist_ok=True)
        # copystat mirrors a read-only source root onto staging; the marker write needs it writable.
        staging.chmod(staging.stat().st_mode | stat.S_IRWXU)
        marker = {"owner": "refract", "path": str(dst.resolve())}
        (staging / _AGY_IDE_MARKER).write_text(json.dumps(marker), encoding="utf-8")
        staging.rename(dst)
        renamed = True
    except OSError as exc:
        return f"cannot copy {src} to {dst}: {exc}"
    finally:
        if staging is not None and not renamed:
            try:
                _rmtree(staging)
            except OSError:
                pass
    return None


def _apply_file(step: _FileStep) -> str | None:
    """Run one file step; return the failure reason, or None on success."""
    if step.kind == "remove":
        return _remove_owned(step.dst)
    if step.src is None:
        return "copy has no source"
    return _copy_owned(step.src, step.dst)


def _file_step_text(step: _FileStep) -> str:
    return f"copy {step.src} -> {step.dst}" if step.kind == "copy" else f"remove {step.dst}"


def _execute(host: str, plan: _Plan, dry_run: bool, out: Callable[[str], None]) -> bool:
    for note in plan.notes:
        out(f"{host}: note: {note}")
    if plan.error:
        out(f"{host}: failed: {plan.error}")
        return False
    if not plan.steps:
        out(f"{host}: {plan.noop}")
        return True
    if dry_run:
        for step in plan.steps:
            if isinstance(step, _FileStep):
                out(f"{host}: would {_file_step_text(step)}")
            else:
                out(f"{host}: would run: {shlex.join(step.argv)}")
        out(f"{host}: skipped (dry run)")
        return True
    applied: list[_Step | _FileStep] = []
    for step in plan.steps:
        reason = _apply_file(step) if isinstance(step, _FileStep) else _apply(step.argv)
        if reason:
            _report_failure(host, reason, applied, out)
            return False
        applied.append(step)
    out(f"{host}: {plan.done}")
    return True


def _run_hosts(
    action: str,
    hosts: Sequence[str],
    source: str,
    scope: str,
    dry_run: bool,
    out: Callable[[str], None],
    *,
    ide_via_all: bool = False,
) -> int:
    out(f"hosts: {', '.join(hosts)}")
    if scope != "user":
        out(f"directory: {Path.cwd()}")
    # Under `-p all`, a remote source cannot feed agy-ide; skip it rather than fail the run.
    ide_skipped = ide_via_all and action == "install" and _is_remote(source)
    failed = False
    for host in hosts:
        if not _host_present(host):
            out(
                f"{host}: failed: Antigravity IDE not found"
                if host == "agy-ide"
                else f"{host}: failed: not on PATH"
            )
            failed = True
            continue
        if host == "agy-ide" and ide_skipped:
            out("agy-ide: skipped: needs --source <local path>")
            continue
        failed |= not _execute(host, _plan(host, action, source, scope), dry_run, out)
    return 1 if failed else 0


def run(
    action: str,
    host_args: Sequence[str],
    *,
    scope: str = "user",
    source: str | None = None,
    dry_run: bool = False,
    out: Callable[[str], None] = print,
) -> int:
    """Install or uninstall the plugin on each requested host. Returns 0, 1, or 2."""
    hosts = _expand_hosts(host_args)
    if hosts is None:
        return _usage(f"-p takes {', '.join(HOSTS)}, or all")
    if (error := _scope_error(hosts, scope)) is not None:
        return _usage(error)
    if not hosts:
        out("No host CLI found on PATH.")
        return 1
    lock_path = refract_home() / "update.lock"
    with ExitStack() as stack:
        try:
            held = stack.enter_context(updater._file_lock(lock_path))
        except OSError:
            out(f"Failed: cannot open {lock_path}. Nothing was changed.")
            return 1
        if not held:
            out("Another refract update or install is running.")
            return 1
        named = {part.strip() for value in host_args for part in value.split(",")}
        return _run_hosts(
            action,
            hosts,
            resolve_source(source),
            scope,
            dry_run,
            out,
            ide_via_all="agy-ide" not in named,
        )
