"""Transcript and result files. A transcript line counts only once `jobs.events_committed` covers it."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from refract.store.pool import tx


class Transcripts:
    """Append JSON lines to `streams/<job_id>.jsonl`, then commit the count; readers stop at the count."""

    def __init__(self, streams_dir: Path, results_dir: Path) -> None:
        self.streams_dir = streams_dir
        self.results_dir = results_dir
        self._offsets: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def stream_path(self, job_id: str) -> Path:
        return self.streams_dir / f"{job_id}.jsonl"

    def result_path(self, job_id: str) -> Path:
        return self.results_dir / f"{job_id}.md"

    def append(self, conn: sqlite3.Connection, job_id: str, events: Sequence[dict[str, Any]]) -> None:
        """Write the events as lines after the committed ones, then raise `events_committed` in a transaction.

        Lines left by a crash between the write and the commit are overwritten.
        """
        if not events:
            return
        payload = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events).encode("utf-8")
        self.streams_dir.mkdir(mode=0o700, exist_ok=True)
        path = self.stream_path(job_id)
        with self._lock:
            row = conn.execute("SELECT events_committed FROM jobs WHERE id=?", (job_id,)).fetchone()
            committed = row["events_committed"] if row else 0
            cached = self._offsets.get(job_id)
            offset = cached[1] if cached and cached[0] == committed else self._committed_offset(path, committed)
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            with os.fdopen(descriptor, "r+b") as handle:
                handle.seek(offset)
                handle.truncate()
                handle.write(payload)
            with tx(conn):
                conn.execute("UPDATE jobs SET events_committed=events_committed+? WHERE id=?", (len(events), job_id))
            self._offsets[job_id] = (committed + len(events), offset + len(payload))

    @staticmethod
    def _committed_offset(path: Path, committed: int) -> int:
        offset = 0
        try:
            with path.open("rb") as handle:
                for _ in range(committed):
                    if not handle.readline():
                        break
                offset = handle.tell()
        except FileNotFoundError:
            pass
        return offset

    def read(self, conn: sqlite3.Connection, job_id: str, after: int, limit: int) -> tuple[list[dict[str, Any]], int, bool]:
        """Return up to `limit` events after line `after`, the last seq returned, and whether more are committed."""
        row = conn.execute("SELECT events_committed FROM jobs WHERE id=?", (job_id,)).fetchone()
        committed = row["events_committed"] if row else 0
        events: list[dict[str, Any]] = []
        last = after
        try:
            handle = self.stream_path(job_id).open("r", encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return events, last, False
        with handle:
            for seq, line in enumerate(handle, start=1):
                if seq > committed:
                    break
                if seq <= after:
                    continue
                if len(events) >= limit:
                    return events, last, True
                try:
                    payload = json.loads(line)
                except ValueError:
                    payload = None
                events.append({**(payload if isinstance(payload, dict) else {"kind": "invalid", "data": {}}), "seq": seq})
                last = seq
        return events, last, False

    def write_result(self, job_id: str, text: str) -> None:
        self.results_dir.mkdir(mode=0o700, exist_ok=True)
        descriptor = os.open(self.result_path(job_id), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)

    def remove(self, job_id: str) -> None:
        self.stream_path(job_id).unlink(missing_ok=True)
        self.result_path(job_id).unlink(missing_ok=True)
        with self._lock:
            self._offsets.pop(job_id, None)
