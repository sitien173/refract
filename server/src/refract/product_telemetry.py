"""Opt-in product telemetry and its durable delivery queue."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any, Callable

from refract.config import DaemonConfig
from refract.logging_setup import get_logger, redact_text
from refract.workers import run_sync

log = get_logger("product_telemetry")
MAX_OUTBOX_ROWS = 10_000
MAX_OUTBOX_AGE_DAYS = 30
BATCH_SIZE = 100
TIMEOUT_S = 10
MAX_BACKOFF_S = 24 * 60 * 60
FEATURE_FLUSH_INTERVAL_S = 60 * 60
COLLECTOR_URL = "https://cf-api-gateway.sitienbmt.workers.dev/refract-collector"


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Returning None makes urllib raise HTTPError for every 3xx, so the body is never resent.
        return None


TELEMETRY_OPENER = urllib.request.build_opener(_RefuseRedirects())


@dataclass(slots=True)
class SendStatus:
    """Last send outcome, kept in memory for the status report."""

    last_send_at: str | None = None
    last_error: str | None = None


def telemetry_decision(config: DaemonConfig, environ: dict[str, str] | None = None) -> tuple[bool, str]:
    env = os.environ if environ is None else environ
    if env.get("DO_NOT_TRACK") == "1":
        return False, "DO_NOT_TRACK"
    if env.get("REFRACT_TELEMETRY") in {"0", "1"}:
        return env["REFRACT_TELEMETRY"] == "1", "REFRACT_TELEMETRY"
    if config.telemetry.enabled is not None:
        return config.telemetry.enabled, "config"
    return False, "default"


def install_id(home: Path) -> str:
    path = home / "telemetry_id"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    value = str(uuid.uuid4())
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_text(encoding="utf-8").strip()
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(value)
    return value


def _redact(
    value: str, secrets: tuple[str, ...], project: str, home: Path,
    *, windows: bool | None = None,
) -> str:
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        value = value.replace(secret, "[REDACTED]")
    windows = os.name == "nt" if windows is None else windows
    paths = {project, str(Path.home()), str(home)}
    for path in sorted((item for item in paths if item), key=len, reverse=True):
        for candidate in {path, path.replace("/", "\\"), path.replace("\\", "/")}:
            if candidate:
                value = re.sub(re.escape(candidate), "[PATH]", value,
                               flags=re.IGNORECASE if windows else 0)
    value = redact_text(value)
    if len(value) > 500:
        value = redact_text(value[:500])
    return value[:500]


def build_job_event(metrics: dict[str, Any], job: dict[str, Any], *, secrets: tuple[str, ...], project: str, home: Path) -> dict[str, Any]:
    tokens = {name: source.get(column) for name, source, column in (
        ("input", metrics, "tok_input"), ("output", metrics, "tok_output"),
        ("cache_read", metrics, "tok_cache_read"), ("cache_write", metrics, "tok_cache_write"),
        ("context_used", job, "tok_context_used"), ("context_window", job, "tok_context_window"),
    )}
    return {
        "event": "job", "job_id": metrics["job_id"], "retry_of": job["retry_of"],
        "finished_at": metrics["finished_at"], "workflow": metrics["workflow"],
        "profile": job["profile"], "session": job["session"], "target": metrics["target"],
        "backend": metrics["backend"], "model": metrics["model"], "state": metrics["state"],
        "failure_kind": metrics["failure_kind"], "duration_ms": metrics["duration_ms"],
        "tokens": tokens, "attempts": metrics["attempts"],
        "skipped_targets": metrics["skipped_targets"],
        "error": _redact(job.get("error", ""), secrets, project, home),
    }


def build_features_event(period_start: str, period_end: str, counts: dict[str, int]) -> dict[str, Any]:
    return {"event": "features", "period_start": period_start, "period_end": period_end,
            "counts": dict(counts)}


def build_heartbeat_event(config: DaemonConfig) -> dict[str, Any]:
    backends: dict[str, int] = {}
    for target in config.targets:
        backends[target.backend] = backends.get(target.backend, 0) + 1
    return {"event": "heartbeat", "os": platform.system(), "arch": platform.machine(),
            "python_version": platform.python_version(),
            "notifications_enabled": config.notifications.enabled, "backends": backends}


def build_batch_body(install: str, events: list[dict[str, Any]], sent_at: str | None) -> dict[str, Any]:
    """Build the POST body; the status preview passes ``sent_at=None`` because it is set on send."""
    return {"schema": 1, "install_id": install, "refract_version": version("refract"),
            "sent_at": sent_at, "events": events}


def send_batch(install: str, events: list[dict[str, Any]], *, opener: Callable[..., Any] | None = None) -> int:
    body = json.dumps(build_batch_body(install, events, datetime.now(timezone.utc).isoformat())).encode()
    request = urllib.request.Request(COLLECTOR_URL, data=body, headers={"Content-Type": "application/json"})
    response = (opener or TELEMETRY_OPENER.open)(request, timeout=TIMEOUT_S)
    return int(response.status)


def telemetry_status(database: Any, config: DaemonConfig, enabled: bool, source: str, status: SendStatus) -> dict[str, Any]:
    """Report the decision and the batch the sender would post next; never creates the install ID while off."""
    install = install_id(config.home) if enabled else None
    rows = database.telemetry_batch(BATCH_SIZE) if enabled else []
    next_batch = (build_batch_body(str(install), [json.loads(row["payload"]) for row in rows], None)
                  if rows else None)
    queued = database.telemetry_queue_count()
    return {"enabled": enabled, "source": source, "endpoint": COLLECTOR_URL,
            "install_id": install, "queued": queued, "last_send_at": status.last_send_at,
            "last_error": status.last_error, "next_batch": next_batch}


def next_backoff(attempts: int) -> int:
    return min(60 * (2 ** max(0, attempts)), MAX_BACKOFF_S)


def read_heartbeat_date(home: Path) -> str:
    try:
        return (home / "telemetry_heartbeat").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def write_heartbeat_date(home: Path, date: str) -> None:
    """Persist the last heartbeat UTC date so a restart on the same day sends no second one."""
    path = home / "telemetry_heartbeat"
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(date, encoding="utf-8")
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def purge(database: Any, home: Path) -> None:
    database.clear_telemetry_outbox()
    (home / "telemetry_id").unlink(missing_ok=True)
    (home / "telemetry_heartbeat").unlink(missing_ok=True)
    (home / "telemetry_heartbeat.tmp").unlink(missing_ok=True)


async def send_outbox_once(
    database: Any,
    config_check: Callable[[], DaemonConfig],
    home: Path,
    opener: Callable[..., Any] | None = None,
    send_status: SendStatus | None = None,
    purge_lock: Any | None = None,
    consent: Callable[[DaemonConfig], bool] | None = None,
) -> None:
    """Publish the config, then decide consent, purge or post, and settle the rows under the purge lock.

    The decision, install ID, POST and row settlement run in one worker thread that run_sync joins on
    cancellation, so the lock is never released while the thread is still working.
    """
    try:
        try:
            config: DaemonConfig | None = await run_sync(config_check)
        except ValueError:
            config = None
        await run_sync(_send_outbox_locked, database, config, consent or _config_consent, home, opener,
                       send_status, purge_lock)
    except Exception:
        log.warning("Telemetry sender failed", extra={"event": "telemetry.sender_failed"}, exc_info=True)


def _config_consent(config: DaemonConfig) -> bool:
    return telemetry_decision(config)[0]


def _send_outbox_locked(
    database: Any,
    config: DaemonConfig | None,
    consent: Callable[[DaemonConfig], bool],
    home: Path,
    opener: Callable[..., Any] | None,
    send_status: SendStatus | None,
    purge_lock: Any | None,
) -> None:
    with purge_lock or contextlib.nullcontext():
        rows = database.telemetry_batch(BATCH_SIZE)
        if config is None or not consent(config):
            purge(database, home)
            return
        if not rows:
            return
        events = [json.loads(row["payload"]) for row in rows]
        ids = [r["id"] for r in rows]
        try:
            install = install_id(home)
            status = send_batch(install, events, opener=opener)
        except urllib.error.HTTPError as exc:
            status = exc.code
        except Exception:
            log.warning("Telemetry send failed", extra={"event": "telemetry.send_failed"}, exc_info=True)
            if send_status is not None:
                send_status.last_error = "network error"
            database.defer_telemetry(ids, [next_backoff(r["send_attempts"]) for r in rows])
            return
        if send_status is not None:
            if 200 <= status < 300:
                send_status.last_send_at, send_status.last_error = datetime.now(timezone.utc).isoformat(), None
            else:
                send_status.last_error = f"HTTP {status}"
        if 200 <= status < 300:
            database.delete_telemetry(ids)
        elif status == 429 or status >= 500:
            database.defer_telemetry(ids, [next_backoff(r["send_attempts"]) for r in rows])
        elif 300 <= status < 500:
            database.delete_telemetry(ids)
            log.warning("Telemetry batch rejected", extra={"event": "telemetry.batch_rejected"})
        else:
            database.defer_telemetry(ids, [next_backoff(r["send_attempts"]) for r in rows])


async def sender(database: Any, config_check: Callable[[], DaemonConfig], home: Path,
                 opener: Callable[..., Any] | None = None,
                 send_status: SendStatus | None = None,
                 purge_lock: Any | None = None,
                 consent: Callable[[DaemonConfig], bool] | None = None) -> None:
    while True:
        await asyncio.sleep(60)
        await send_outbox_once(database, config_check, home, opener, send_status, purge_lock, consent)
