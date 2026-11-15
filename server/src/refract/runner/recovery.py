"""Startup recovery: interrupt jobs a previous daemon left running and kill their stale worker groups."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from refract.logging_setup import get_logger
from refract.runner.processes import kill_stale_group
from refract.scheduling.hub import Hub
from refract.store.database import Database
from refract.store.pool import run_db, run_sync

log = get_logger("runtime")


async def recover_interrupted(database: Database, hub: Hub, notify: Callable[[str], Awaitable[None]]) -> int:
    """Mark `running` jobs `interrupted`, kill their worker groups, notify, and publish `terminal`.

    Returns the number of interrupted jobs. `queued` jobs are left for the caller to resume.
    """
    await run_db(database.reset_orphaned_target_probes)
    interrupted = await run_db(database.interrupt_active_jobs)
    for job in interrupted:
        if job["pgid"]:
            killed = await run_sync(kill_stale_group, int(job["pgid"]), str(job["id"]))
            log.info("Stale worker group checked", extra={"event": "job.worker_group", "job_id": job["id"], "pgid": job["pgid"], "killed": killed})
    for job in interrupted:
        await notify(str(job["id"]))
        hub.publish(str(job["id"]), "terminal")
    return len(interrupted)
