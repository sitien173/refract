"""Wait for jobs: subscribe to the hub before the first DB read, then re-read on every signal."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from refract.models import LIST_JOB_ID_ACTION, TERMINAL_STATES, UNKNOWN_JOB_MESSAGE, JobView, OrchestrationError
from refract.scheduling.hub import Hub
from refract.store.database import Database
from refract.store.pool import run_db

MAX_WAIT_JOBS = 16


def validate_job_ids(job_ids: Sequence[str]) -> list[str]:
    """The IDs as a list; `invalid_request` unless there are 1 to `MAX_WAIT_JOBS` distinct ones."""
    ids = list(job_ids)
    if not ids or len(ids) > MAX_WAIT_JOBS or len(set(ids)) != len(ids):
        raise OrchestrationError(
            f"wait takes between 1 and {MAX_WAIT_JOBS} distinct job IDs.",
            code="invalid_request",
            next_action=f"Pass 1 to {MAX_WAIT_JOBS} distinct job IDs.",
        )
    return ids


@dataclass(frozen=True, slots=True)
class WaitResult:
    """`ready` is true when `job` is terminal or has an open question, false when the wait timed out."""

    job: JobView
    ready: bool


async def wait_jobs(
    database: Database, hub: Hub, is_closing: Callable[[], bool], job_ids: Sequence[str], timeout_s: float = 0
) -> WaitResult:
    """Return the first listed job that is terminal or has an open question, else the first job on timeout.

    A job that finished earlier, or was interrupted by a restart, is reported at once. `timeout_s` of 0
    waits without a limit.
    """
    ids = validate_job_ids(job_ids)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s if timeout_s > 0 else None
    with hub.subscribe(ids) as subscription:
        while True:
            subscription.clear()
            snapshot = await run_db(database.wait_snapshot, ids)
            if any(job is None for job, _ in snapshot):
                raise OrchestrationError(UNKNOWN_JOB_MESSAGE, code="unknown_job", next_action=LIST_JOB_ID_ACTION)
            for job, has_question in snapshot:
                if job.state in TERMINAL_STATES or has_question:
                    return WaitResult(job, True)
            remaining = None if deadline is None else deadline - loop.time()
            if is_closing() or (remaining is not None and remaining <= 0):
                return WaitResult(snapshot[0][0], False)
            await subscription.wait(remaining)
