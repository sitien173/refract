"""Desktop notification delivery for terminal jobs."""

from __future__ import annotations

from notifypy import Notify

from refract.models import JobView


def send_job_notification(job: JobView, project_name: str) -> bool:
    """Send a desktop notification when a job completes."""
    notification = Notify()
    notification.application_name = "Refract"
    notification.title = f"Refract job {job.state}"
    target = job.target_id or "-"
    notification.message = f"{project_name} / {job.session} / {job.workflow} / {target}"
    return bool(notification.send(block=True))


__all__ = ["send_job_notification"]
