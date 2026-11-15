"""Job notifications: the resource notifier and the optional desktop notification."""

from __future__ import annotations

from pathlib import Path

from refract.config.models import DaemonConfig
from refract.logging_setup import get_logger
from refract.models import TERMINAL_STATES, JobView
from refract.notifications import send_job_notification
from refract.runner.jobs import JobNotifier
from refract.store.database import Database
from refract.store.pool import run_db, run_sync

log = get_logger("runtime")
_DESKTOP_NOTIFICATION_FAILED = "Desktop notification failed"
_DESKTOP_NOTIFICATION_FAILED_EVENT = "job.desktop_notification_failed"


async def notify_job(database: Database, config: DaemonConfig, notifier: JobNotifier, job_id: str) -> None:
    """Call the resource notifier, then send a desktop notification for a terminal job when enabled."""
    job: JobView | None = None
    lookup_error: Exception | None = None
    if config.notifications.enabled:
        try:
            job = await run_db(database.job, job_id)
        except Exception as exc:
            lookup_error = exc
    try:
        await notifier(job_id)
    except Exception:
        log.warning(
            "Job resource notification failed",
            extra={"event": "job.resource_notification_failed", "job_id": job_id},
            exc_info=True,
        )
    if not config.notifications.enabled:
        return
    if lookup_error is not None:
        log.warning(
            _DESKTOP_NOTIFICATION_FAILED,
            extra={"event": _DESKTOP_NOTIFICATION_FAILED_EVENT, "job_id": job_id},
            exc_info=(type(lookup_error), lookup_error, lookup_error.__traceback__),
        )
        return
    if job is None or job.state not in TERMINAL_STATES:
        return
    try:
        project = await run_db(database.project, job.project_id)
        if project is None:
            return
        if not await run_sync(send_job_notification, job, Path(project.root).name):
            log.warning(
                _DESKTOP_NOTIFICATION_FAILED,
                extra={"event": _DESKTOP_NOTIFICATION_FAILED_EVENT, "job_id": job_id},
            )
    except Exception:
        log.warning(
            _DESKTOP_NOTIFICATION_FAILED,
            extra={"event": _DESKTOP_NOTIFICATION_FAILED_EVENT, "job_id": job_id},
            exc_info=True,
        )
