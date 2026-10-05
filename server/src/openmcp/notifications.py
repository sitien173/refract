"""Desktop notification delivery for terminal jobs."""

from __future__ import annotations

from notifypy import Notify

from openmcp.models import JobView


def send_job_notification(job: JobView, project_alias: str) -> bool:
    """Send a desktop notification when a job completes."""
    notification = Notify()
    notification.application_name = "OpenMCP"
    notification.title = f"OpenMCP job {job.state}"
    target = job.target_id or "-"
    notification.message = f"{project_alias} / {job.context_key} / {job.workflow} / {target}"
    return bool(notification.send(block=True))


__all__ = ["send_job_notification"]
