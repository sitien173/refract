"""One driver invocation: stream events feed telemetry and the stream log."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

from refract.config import TargetConfig
from refract.logging_setup import get_logger, log_context
from refract.runner.drivers import DriverResult
from refract.runner.tokens import CONSUMPTION_KEYS, TokenCounters, counters_from
from refract.scheduling.cancel import CancelEvent
from refract.store.pool import run_db

log = get_logger("execution")
_CANCELLED = DriverResult("CANCELLED", "", "", "cancelled", "cancelled")


class Invocation:
    """Mixin for `TargetExecutor`: needs `self.database` and `self.drivers`."""

    async def _record_stream_event(self, job_id: str, attempt: int, target: TargetConfig, event: dict[str, Any]) -> None:
        try:
            await run_db(self.database.append_stream, job_id, [{
                "attempt": attempt, "target_id": target.id, "backend": target.backend,
                "kind": str(event.get("kind", "")), "entity_id": str(event.get("entity_id", "")),
                "parent_entity_id": str(event.get("parent_entity_id", "")), "data": dict(event.get("data", {})),
            }])
        except Exception as exc:
            log.exception("Stream persistence failed",
                          extra={"event": "stream.persistence_failed", "job_id": job_id, "error": str(exc)})

    async def _run_target_invocation(
        self, *, job_id: str, attempt: int, attempt_tokens: list[TokenCounters], target: TargetConfig, prompt: str,
        session_id: str, cwd: Path, timeout_s: float, cancel_event: threading.Event, supports_streaming: bool,
        env: dict[str, str] | None = None,
    ) -> tuple[DriverResult, bool]:
        attempt_tokens.append(TokenCounters())
        consumed_tool_activity = False
        streamed_consumption = False

        async def consume(event: dict[str, Any]) -> None:
            """Apply one stream event to telemetry and the stream log."""
            nonlocal consumed_tool_activity, streamed_consumption
            consumed_tool_activity = consumed_tool_activity or self._is_event_kind(event, "tool.started")
            if self._is_event_kind(event, "telemetry.updated"):
                streamed_consumption = self._apply_telemetry(attempt_tokens, event) or streamed_consumption
            if supports_streaming:
                await self._record_stream_event(job_id, attempt, target, event)

        attempt_result: DriverResult | None = None
        driver_exc: BaseException | None = None
        try:
            with log_context(target_id=target.id):
                attempt_result = await self.drivers.execute(
                    target=target, prompt=prompt, cwd=cwd, session_id=session_id, timeout_s=timeout_s,
                    cancel_event=cancel_event, on_event=consume if supports_streaming else None, env=env,
                    on_spawn=lambda pid: self._record_process_group(job_id, pid),
                )
        except BaseException as exc:
            driver_exc = exc
            raise
        finally:
            if cancel_event.is_set() or isinstance(driver_exc, asyncio.CancelledError):
                attempt_result = _CANCELLED
            # Returned counts apply only when stream events did not already report consumption.
            if attempt_result is not None and not streamed_consumption:
                self._merge_returned_tokens(attempt_tokens, attempt_result)

        if attempt_result is None:
            attempt_result = DriverResult(
                "REQUEST_FATAL", "", "", str(driver_exc) if driver_exc else "execution_failed", "execution_error",
            )
        return attempt_result, consumed_tool_activity

    @staticmethod
    def _is_event_kind(event: Any, kind: str) -> bool:
        return isinstance(event, dict) and event.get("kind") == kind

    @staticmethod
    def _apply_telemetry(attempt_tokens: list[TokenCounters], event: dict[str, Any]) -> bool:
        """Record one telemetry event; return whether it reported consumption."""
        try:
            data = event.get("data")
            if not isinstance(data, dict):
                return False
            attempt_tokens[-1] = counters_from(data)
            return any(key in data for key in CONSUMPTION_KEYS)
        except Exception:
            log.warning("Telemetry update failed", exc_info=True)
            return False

    async def _record_process_group(self, job_id: str, pgid: int) -> None:
        try:
            await run_db(self.database.set_pgid, job_id, pgid)
        except Exception:
            log.warning("Worker process group not recorded", exc_info=True)

    @staticmethod
    def _merge_returned_tokens(attempt_tokens: list[TokenCounters], attempt_result: DriverResult) -> None:
        try:
            current = attempt_tokens[-1].as_dict()
            reported = counters_from(attempt_result.tokens or {}).as_dict()
            attempt_tokens[-1] = counters_from({**current, **{k: v for k, v in reported.items() if v is not None}})
        except Exception:
            log.warning("Ignoring malformed backend telemetry", exc_info=True)
