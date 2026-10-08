"""Durable transcript stream recording and quota management."""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
from typing import Any, Callable

from openmcp.database import Database
from openmcp.logging_setup import get_logger
from openmcp.models import JobStreamEvent


log = get_logger("streaming")

MAX_BATCH_EVENTS = 50
MAX_BATCH_BYTES = 64 * 1024
FLUSH_INTERVAL_SECONDS = 0.1
MAX_TEXT_EVENT_BYTES = 8 * 1024
MAX_JOB_BYTES = 8 * 1024 * 1024
MAX_JOB_EVENTS = 20000
TRUNCATION_KIND = "stream.truncated"
DEFAULT_RETENTION_DAYS = 7


def _split_text(text: str, max_bytes: int) -> list[str]:
    if not text:
        return []
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return [text]
    chunks: list[str] = []
    current_chars: list[str] = []
    current_bytes = 0
    for char in text:
        char_bytes = len(char.encode("utf-8"))
        if current_bytes + char_bytes > max_bytes:
            if current_chars:
                chunks.append("".join(current_chars))
                current_chars = [char]
                current_bytes = char_bytes
            else:
                chunks.append(char)
                current_chars = []
                current_bytes = 0
        else:
            current_chars.append(char)
            current_bytes += char_bytes
    if current_chars:
        chunks.append("".join(current_chars))
    return chunks


class StreamRecorder:
    def __init__(
        self,
        database: Database,
        job_id: str,
        attempt: int,
        target_id: str,
        backend: str,
        *,
        on_commit: Callable[[int], Any] | None = None,
        max_batch_events: int = MAX_BATCH_EVENTS,
        max_batch_bytes: int = MAX_BATCH_BYTES,
        flush_interval_s: float = FLUSH_INTERVAL_SECONDS,
        max_text_event_bytes: int = MAX_TEXT_EVENT_BYTES,
        max_job_events: int = MAX_JOB_EVENTS,
        max_job_bytes: int = MAX_JOB_BYTES,
    ) -> None:
        self.database = database
        self.job_id = job_id
        self.attempt = attempt
        self.target_id = target_id
        self.backend = backend
        self._on_commit = on_commit
        self.max_batch_events = max_batch_events
        self.max_batch_bytes = max_batch_bytes
        self.flush_interval_s = flush_interval_s
        self.max_text_event_bytes = max_text_event_bytes
        self.max_job_events = max_job_events
        self.max_job_bytes = max_job_bytes

        self._buffer: list[dict[str, Any]] = []
        self._buffer_bytes: int = 0
        self._timer_handle: asyncio.TimerHandle | None = None
        self._closed: bool = False
        self._failed: bool = False

        totals = self.database.stream_totals(job_id)
        self._total_events: int = totals.events
        self._total_bytes: int = totals.bytes
        self._truncated: bool = False

        if (
            self._total_events >= self.max_job_events
            or self._total_bytes >= self.max_job_bytes
            or self.database.stream_is_truncated(job_id)
        ):
            self._truncated = True

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def truncated(self) -> bool:
        return self._truncated

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def status(self) -> str:
        if self._failed:
            return "failed"
        if self._truncated:
            return "truncated"
        if self._closed:
            return "closed"
        return "active"

    async def record(
        self,
        event_or_kind: dict[str, Any] | JobStreamEvent | str,
        data: dict[str, Any] | None = None,
        *,
        entity_id: str = "",
        parent_entity_id: str = "",
    ) -> None:
        if self._closed or self._truncated:
            return

        if isinstance(event_or_kind, JobStreamEvent):
            kind = event_or_kind.kind
            evt_data = dict(event_or_kind.data)
            entity_id = event_or_kind.entity_id or entity_id
            parent_entity_id = event_or_kind.parent_entity_id or parent_entity_id
        elif isinstance(event_or_kind, dict):
            kind = str(event_or_kind.get("kind", ""))
            evt_data = dict(event_or_kind.get("data", {}))
            entity_id = str(event_or_kind.get("entity_id", entity_id))
            parent_entity_id = str(event_or_kind.get("parent_entity_id", parent_entity_id))
        elif isinstance(event_or_kind, str):
            kind = event_or_kind
            evt_data = dict(data or {})
        else:
            raise TypeError(f"Unsupported event type: {type(event_or_kind)}")

        if kind in {"assistant.text.delta", "assistant.reasoning_summary.delta"}:
            text = str(evt_data.get("text", ""))
            chunks = _split_text(text, self.max_text_event_bytes)
            if not chunks:
                return
            for chunk in chunks:
                if self._truncated:
                    return
                if self._buffer:
                    last = self._buffer[-1]
                    if (
                        last["kind"] == kind
                        and last["entity_id"] == entity_id
                        and last["parent_entity_id"] == parent_entity_id
                    ):
                        last_text = str(last["data"].get("text", ""))
                        merged = last_text + chunk
                        if len(merged.encode("utf-8")) <= self.max_text_event_bytes:
                            old_bytes = len(json.dumps(last["data"], ensure_ascii=False).encode("utf-8"))
                            new_data = {"text": merged}
                            new_bytes = len(json.dumps(new_data, ensure_ascii=False).encode("utf-8"))
                            diff = new_bytes - old_bytes
                            if self._total_bytes + diff > self.max_job_bytes:
                                await self._mark_truncated(entity_id, parent_entity_id)
                                return
                            last["data"] = new_data
                            self._buffer_bytes += diff
                            self._total_bytes += diff
                            if (
                                len(self._buffer) >= self.max_batch_events
                                or self._buffer_bytes >= self.max_batch_bytes
                            ):
                                await self.flush()
                            else:
                                self._schedule_timer()
                            continue
                await self._push_event({
                    "attempt": self.attempt,
                    "target_id": self.target_id,
                    "backend": self.backend,
                    "kind": kind,
                    "entity_id": entity_id,
                    "parent_entity_id": parent_entity_id,
                    "data": {"text": chunk},
                })
        else:
            await self._push_event({
                "attempt": self.attempt,
                "target_id": self.target_id,
                "backend": self.backend,
                "kind": kind,
                "entity_id": entity_id,
                "parent_entity_id": parent_entity_id,
                "data": evt_data,
            })

    async def _mark_truncated(self, entity_id: str, parent_entity_id: str) -> None:
        self._truncated = True
        await self.flush()
        if not self.database.stream_is_truncated(self.job_id):
            trunc_evt = {
                "attempt": self.attempt,
                "target_id": self.target_id,
                "backend": self.backend,
                "kind": TRUNCATION_KIND,
                "entity_id": entity_id or "stream",
                "parent_entity_id": parent_entity_id,
                "data": {"reason": "limit_exceeded"},
            }
            trunc_bytes = len(json.dumps(trunc_evt["data"], ensure_ascii=False).encode("utf-8"))
            self._buffer.append(trunc_evt)
            self._buffer_bytes += trunc_bytes
            self._total_events += 1
            self._total_bytes += trunc_bytes
            await self.flush()

    async def _push_event(self, evt: dict[str, Any]) -> None:
        if self._truncated:
            return
        evt_bytes = len(json.dumps(evt["data"], ensure_ascii=False).encode("utf-8"))
        if evt.get("kind") != "attempt.finished":
            if self._total_events + 1 > self.max_job_events or self._total_bytes + evt_bytes > self.max_job_bytes:
                await self._mark_truncated(
                    str(evt.get("entity_id", "")),
                    str(evt.get("parent_entity_id", "")),
                )
                return

        self._buffer.append(evt)
        self._buffer_bytes += evt_bytes
        self._total_events += 1
        self._total_bytes += evt_bytes

        if len(self._buffer) >= self.max_batch_events or self._buffer_bytes >= self.max_batch_bytes:
            await self.flush()
        else:
            self._schedule_timer()

    def _schedule_timer(self) -> None:
        if self._timer_handle is None and not self._closed and self._buffer:
            try:
                loop = asyncio.get_running_loop()
                self._timer_handle = loop.call_later(
                    self.flush_interval_s,
                    self._on_timer,
                )
            except RuntimeError:
                pass

    def _on_timer(self) -> None:
        self._timer_handle = None
        if self._buffer and not self._closed:
            asyncio.create_task(self.flush())

    async def flush(self) -> None:
        if self._timer_handle:
            self._timer_handle.cancel()
            self._timer_handle = None
        if not self._buffer:
            return
        to_persist = list(self._buffer)
        self._buffer.clear()
        self._buffer_bytes = 0

        try:
            persisted = self.database.append_stream_events(self.job_id, to_persist)
        except Exception as exc:
            log.error(
                "Stream persistence failed",
                exc_info=True,
                extra={"event": "stream.persistence_failed", "job_id": self.job_id, "error": str(exc)},
            )
            self._failed = True
            try:
                self.database.event(self.job_id, "stream.persistence_failed", {"error": str(exc)})
            except Exception:
                pass
            return

        if persisted and self._on_commit:
            high_water = persisted[-1].id
            try:
                res = self._on_commit(high_water)
                if inspect.isawaitable(res):
                    await res
            except Exception:
                log.warning(
                    "Stream on_commit callback failed",
                    exc_info=True,
                    extra={"event": "stream.commit_callback_failed", "job_id": self.job_id},
                )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._timer_handle:
            self._timer_handle.cancel()
            self._timer_handle = None
        await self.flush()


class JobStreamHub:
    """Runtime-owned in-memory cursor invalidation hub. Retains no transcript payload."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[tuple[asyncio.Queue[int], asyncio.AbstractEventLoop]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, job_id: str) -> asyncio.Queue[int]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[int] = asyncio.Queue(maxsize=1)
        with self._lock:
            self._subscribers.setdefault(job_id, set()).add((queue, loop))
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[int]) -> None:
        with self._lock:
            subscribers = self._subscribers.get(job_id)
            if subscribers is not None:
                to_remove = [item for item in subscribers if item[0] is queue]
                for item in to_remove:
                    subscribers.discard(item)
                if not subscribers:
                    self._subscribers.pop(job_id, None)

    def publish(self, job_id: str, cursor: int) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(job_id, ()))
        for queue, loop in subscribers:
            def _put(q=queue, c=cursor) -> None:
                if q.full():
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    q.put_nowait(c)
                except asyncio.QueueFull:
                    pass

            if loop.is_closed():
                continue
            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None

            if running_loop is loop:
                _put()
            else:
                loop.call_soon_threadsafe(_put)


__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "FLUSH_INTERVAL_SECONDS",
    "JobStreamHub",
    "MAX_BATCH_BYTES",
    "MAX_BATCH_EVENTS",
    "MAX_JOB_BYTES",
    "MAX_JOB_EVENTS",
    "MAX_TEXT_EVENT_BYTES",
    "StreamRecorder",
    "TRUNCATION_KIND",
]
