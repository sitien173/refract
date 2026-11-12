#!/usr/bin/env python3
"""SessionStart hook for refract plugin."""

import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import time

plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Pi names skills without the Claude plugin namespace.
pi = sys.argv[1:2] == ["--pi"]
skill_prefix = "" if pi else "refract:"
disabled = os.environ.get("REFRACT_DISABLE", "").lower() in ("1", "true", "yes")

DISABLED_CONTEXT = f"""
Refract is disabled for this session (REFRACT_DISABLE is set).
Ignore the Refract plugin instructions: do not load Refract skills
such as {skill_prefix}using-refract, do not run Refract commands, and do not call
any tool of the `refract` MCP server. Work directly unless the user explicitly asks for Refract."""

COMPACT_CONTEXT = f"""
You are Coordinator. Follow the workflow described by the skills below.

Load {skill_prefix}using-refract skill, your introduction to using skills.
Read {skill_prefix}coordinating-multi-model-work skill before any Plan, Execute,
or Review action on coordinated work. Route external workers only when that
skill requires them. Prefer guidance returned by the `refract` `list` tool.
User instructions override the workflow.

Bundled worker contracts:
- {plugin_root}/shared/worker-contract.md
- {plugin_root}/shared/erp.md
- {plugin_root}/shared/notes-template.md
- {plugin_root}/shared/journal-template.md"""


def ensure_daemon():
    """Start a detached refract daemon when `refract status` reports none."""
    refract = shutil.which("refract")
    if refract is None:
        return
    try:
        if subprocess.run([refract, "status"], capture_output=True, timeout=5).returncode == 0:
            return
        subprocess.Popen(
            [refract, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


# Same patterns as server/src/refract/updater.py; the hook cannot import refract.
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
SHA_RE = re.compile(r"[0-9a-f]{7,40}\Z")
CACHE_MAX_BYTES = 64 * 1024
CACHE_MAX_AGE = 86400
CACHE_MAX_FUTURE = 300


def read_cache():
    """Return the update-check cache dict, or None when it is absent or unusable."""
    override = os.environ.get("REFRACT_HOME", "").strip()
    home = os.path.expanduser(override) if override else os.path.join(os.path.expanduser("~"), ".refract")
    try:
        fd = os.open(
            os.path.join(home, "update-check.json"),
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return None
            raw = os.read(fd, CACHE_MAX_BYTES + 1)
        finally:
            os.close(fd)
        if len(raw) > CACHE_MAX_BYTES:
            return None
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def is_stale(cache):
    if cache is None:
        return True
    checked_at = cache.get("checked_at")
    if isinstance(checked_at, bool) or not isinstance(checked_at, (int, float)) or not math.isfinite(checked_at):
        return True
    age = time.time() - checked_at
    return age > CACHE_MAX_AGE or age < -CACHE_MAX_FUTURE


def update_label(cache):
    """Return the notice label when the cache reports an update, else None."""
    schema = cache.get("schema")
    if isinstance(schema, bool) or schema != 1 or cache.get("update_available") is not True:
        return None
    version, commit = cache.get("latest_version"), cache.get("latest_commit")
    if isinstance(version, str) and VERSION_RE.match(version):
        return f"Refract {version}"
    if isinstance(commit, str) and SHA_RE.match(commit):
        return f"Refract commit {commit[:7]}"
    return "A Refract update"


def update_notice():
    """Return the cached update label, spawning a detached check when the cache is stale."""
    if (
        os.environ.get("REFRACT_NO_UPDATE_CHECK", "").lower() in ("1", "true", "yes")
        or os.environ.get("REFRACT_JOB_ID")
    ):
        return None
    cache = read_cache()
    try:
        stale = is_stale(cache)
        label = update_label(cache) if cache is not None else None
    except Exception:
        # Cache contents the checks cannot handle, such as an int too large for a float.
        stale, label = True, None
    if stale:
        refract = shutil.which("refract")
        if refract is not None:
            try:
                subprocess.Popen(
                    [refract, "update", "--check"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError:
                pass
    return label


def wrap(context):
    return f"<EXTREMELY_IMPORTANT>\n{context}\n</EXTREMELY_IMPORTANT>"


if disabled:
    context = wrap(DISABLED_CONTEXT)
    if sys.argv[1:2] == ["--antigravity"]:
        payload = {"injectSteps": [{"systemMessage": {"systemMessage": context}}]}
    else:
        payload = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    print(json.dumps(payload, indent=2))
    sys.exit()

ensure_daemon()
label = update_notice()
notice = f"{label} is available; run refract update. Tell the user once. Do not run refract update yourself."

if sys.argv[1:2] == ["--antigravity"]:
    plugin_repo_root = os.path.dirname(plugin_root)
    antigravity_context = (
        f"{COMPACT_CONTEXT}\n\n"
        f"When {plugin_root} is available in your workspace context, treat it as your own plugin directory "
        f"and reference {plugin_root} only to invoke plugin skills and read bundled contracts. "
        f"Do not treat {plugin_repo_root} or {plugin_root} as a project to work on."
    )
    if label:
        antigravity_context += f"\n\n{notice}"
    payload = {"injectSteps": [{"systemMessage": {"systemMessage": wrap(antigravity_context)}}]}
else:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": wrap(COMPACT_CONTEXT + (f"\n\n{notice}" if label else "")),
        }
    }
    if label and not pi:
        payload["systemMessage"] = f"{label} is available. Run: refract update"

print(json.dumps(payload, indent=2))
