"""Per-target circuit-breaker state."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from refract.store.pool import writes
from refract.store.schema import utc_now


def get(conn: sqlite3.Connection, target_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM target_health WHERE target_id=?", (target_id,)).fetchone()
    return dict(row) if row else {
        "target_id": target_id, "consecutive_failures": 0, "circuit_open_until": "",
        "last_success_at": "", "cooldown_s": 0, "probe_job_id": "",
    }


@writes
def claim_probe(conn: sqlite3.Connection, target_id: str, job_id: str, now: str) -> bool:
    return conn.execute(
        "UPDATE target_health SET probe_job_id=:job WHERE target_id=:key AND circuit_open_until<>'' "
        "AND circuit_open_until<=:now AND probe_job_id=''",
        {"job": job_id, "key": target_id, "now": now},
    ).rowcount == 1


@writes
def release_probe(conn: sqlite3.Connection, target_id: str, job_id: str = "") -> None:
    if job_id:
        conn.execute("UPDATE target_health SET probe_job_id='' WHERE target_id=? AND probe_job_id=?", (target_id, job_id))
    else:
        conn.execute("UPDATE target_health SET probe_job_id='' WHERE target_id=?", (target_id,))


@writes
def release_job_probes(conn: sqlite3.Connection, job_id: str) -> None:
    conn.execute("UPDATE target_health SET probe_job_id='' WHERE probe_job_id=?", (job_id,))


@writes
def reset_orphaned_probes(conn: sqlite3.Connection, now: str | None = None) -> int:
    return conn.execute(
        "UPDATE target_health SET probe_job_id='', circuit_open_until=? WHERE probe_job_id<>''", (now or utc_now(),)
    ).rowcount


@writes
def record_success(
    conn: sqlite3.Connection, target_id: str, base_cooldown_s: int = 60, job_id: str | None = None,
) -> None:
    """`job_id` makes the probe clear ownership-aware: another job's probe is kept. None clears it always."""
    conn.execute(
        """INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, last_success_at, cooldown_s, probe_job_id)
           VALUES (:id, 0, '', :now, :cooldown, '')
           ON CONFLICT(target_id) DO UPDATE SET consecutive_failures=0, circuit_open_until='',
           last_success_at=excluded.last_success_at, cooldown_s=excluded.cooldown_s,
           probe_job_id=CASE WHEN :all OR target_health.probe_job_id IN ('', :job) THEN '' ELSE target_health.probe_job_id END""",
        {"id": target_id, "now": utc_now(), "cooldown": base_cooldown_s, "job": job_id or "", "all": job_id is None},
    )


@writes
def record_failure(
    conn: sqlite3.Connection, target_id: str, circuit_open_until: str = "", *, threshold: int = 3,
    base_cooldown_s: int = 60, max_cooldown_s: int = 900, failed_probe: bool = False, immediate: bool = False,
    job_id: str | None = None,
) -> int:
    """`job_id` makes the probe clear ownership-aware: another job's probe is kept. None clears it always."""
    row = conn.execute(
        "SELECT consecutive_failures, cooldown_s FROM target_health WHERE target_id=?", (target_id,)
    ).fetchone()
    failures = (int(row["consecutive_failures"]) if row else 0) + 1
    cooldown = int(row["cooldown_s"] or 0) if row else 0
    if cooldown == 0:
        cooldown = base_cooldown_s
    if failed_probe:
        cooldown = min(max_cooldown_s, cooldown * 2)
    opened = immediate or failed_probe or failures >= threshold
    until = circuit_open_until or (
        (datetime.now(timezone.utc) + timedelta(seconds=cooldown)).isoformat() if opened else ""
    )
    conn.execute(
        """INSERT INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id)
           VALUES (:id, :failures, :until, :cooldown, '')
           ON CONFLICT(target_id) DO UPDATE SET consecutive_failures=excluded.consecutive_failures,
           circuit_open_until=excluded.circuit_open_until, cooldown_s=excluded.cooldown_s,
           probe_job_id=CASE WHEN :all OR target_health.probe_job_id IN ('', :job) THEN '' ELSE target_health.probe_job_id END""",
        {"id": target_id, "failures": failures, "until": until, "cooldown": cooldown,
         "job": job_id or "", "all": job_id is None},
    )
    return failures
