"""Install and remove the Refract plugin by driving each host's own CLI.

Each host is probed read-only, turned into an ordered list of argv lists, and then
executed or, with ``--dry-run``, printed. Refract never writes host files itself.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from refract import updater
from refract.config import refract_home

DEFAULT_SOURCE = "https://github.com/sitien173/refract"
MARKETPLACE_REPO = "sitien173/refract"
MARKETPLACE = "refract"
PLUGIN_ID = "refract@refract"
HOSTS = ("claude", "codex", "agy", "pi")
SCOPES = ("user", "project", "local")
_SCOPES_BY_HOST = {
    "claude": SCOPES,
    "pi": ("user", "project"),
    "codex": ("user",),
    "agy": ("user",),
}
_SOURCE_KEYS = ("repo", *updater._MARKETPLACE_KEYS)
# Verbs for `<host> plugin <verb>` on the hosts that use a marketplace.
_VERBS = {"claude": ("install", "uninstall"), "codex": ("add", "remove")}


@dataclass(frozen=True, slots=True)
class _Step:
    argv: list[str]
    undo: list[str] | None = None


@dataclass(frozen=True, slots=True)
class _Plan:
    steps: list[_Step]
    noop: str = ""
    done: str = ""
    error: str | None = None
    notes: tuple[str, ...] = ()


def resolve_source(value: str | None) -> str:
    """The default URL, a URL or git address as given, or a local path made absolute."""
    if value is None:
        return DEFAULT_SOURCE
    if "://" in value or value.startswith("git@"):
        return value
    return str(Path(value).expanduser().resolve())


def marketplace_arg(source: str) -> str:
    """The Claude and Codex marketplace argument: the short repo name for the default source."""
    return MARKETPLACE_REPO if source == DEFAULT_SOURCE else source


# --- host selection -----------------------------------------------------------


def _usage(message: str) -> int:
    sys.stderr.write(f"{message}\n")
    return 2


def _expand_hosts(values: Sequence[str]) -> list[str] | None:
    """Split comma lists, expand ``all`` to the hosts on PATH, dedupe in first-seen order."""
    hosts: list[str] = []
    for token in (part.strip() for value in values for part in value.split(",")):
        if token == "all":
            names = [host for host in HOSTS if shutil.which(host)]
        elif token in HOSTS:
            names = [token]
        else:
            return None
        hosts.extend(name for name in names if name not in hosts)
    return hosts


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
        return _Plan([], noop="already installed")
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
        return _Plan([], noop="not installed")
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
            return _Plan([], noop="already installed")
        return _Plan([_Step(["agy", "plugin", "install", source])], done="installed")
    if not installed:
        return _Plan([], noop="not installed")
    return _Plan([_Step(["agy", "plugin", "uninstall", "refract"])], done="removed")


def _plan_pi(action: str, source: str, scope: str) -> _Plan:
    installed, failure = _installed("pi", scope)
    if failure:
        return _Plan([], error=failure)
    flag = ["-l"] if scope == "project" else []
    if action == "install":
        if installed:
            return _Plan([], noop="already installed")
        return _Plan([_Step(["pi", "install", source, *flag])], done="installed")
    # The stored string is passed back unchanged; Pi matches packages on it.
    refs = list(dict.fromkeys(item.ref for item in installed if item.ref))
    if not refs:
        return _Plan([], noop="not installed")
    return _Plan([_Step(["pi", "remove", ref, *flag]) for ref in refs], done="removed")


def _plan(host: str, action: str, source: str, scope: str) -> _Plan:
    if host == "agy":
        return _plan_agy(action, source, scope)
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
    host: str, reason: str, applied: list[_Step], out: Callable[[str], None]
) -> None:
    out(f"{host}: failed: {reason}")
    for step in applied:
        out(f"{host}: applied: {shlex.join(step.argv)}")
    for step in reversed(applied):
        if step.undo:
            out(f"{host}: undo: {shlex.join(step.undo)}")


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
            out(f"{host}: would run: {shlex.join(step.argv)}")
        out(f"{host}: skipped (dry run)")
        return True
    applied: list[_Step] = []
    for step in plan.steps:
        reason = _apply(step.argv)
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
) -> int:
    out(f"hosts: {', '.join(hosts)}")
    if scope != "user":
        out(f"directory: {Path.cwd()}")
    failed = False
    for host in hosts:
        if shutil.which(host) is None:
            out(f"{host}: failed: not on PATH")
            failed = True
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
        return _run_hosts(action, hosts, resolve_source(source), scope, dry_run, out)
