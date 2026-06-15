"""Retry orchestration for openmcp backends."""

from __future__ import annotations

import asyncio
import random
from typing import Any

from openmcp.backends import BackendResult
from openmcp.logging_setup import get_logger
from openmcp.notify import emit_attempt_failed

log = get_logger("retry")


async def run_with_retry(execute_fn, params, max_retries: int, retry_base_ms: int) -> dict[str, Any]:
    """Run backend execute with retry behavior based on BackendResult classification.

    Failure payloads (FATAL / exhausted RETRYABLE) include the last
    observed SESSION_ID and agent_messages so the coordinator can cache
    the session and inspect partial output.
    """
    attempt = 1
    last_result: BackendResult | None = None
    backend_name = getattr(execute_fn, "__module__", "backend").rsplit(".", 1)[-1]
    while True:
        log.info("retry: attempt %d backend=%s max_retries=%d", attempt, backend_name, max_retries)
        try:
            result: BackendResult = await execute_fn(params)
        except Exception:
            log.exception("retry: execute_fn raised on attempt %d", attempt)
            raise

        last_result = result
        log.info(
            "retry: attempt %d outcome=%s error_class=%s",
            attempt, result.outcome, result.error_class,
        )

        if result.outcome == "OK":
            payload: dict[str, Any] = {
                "success": True,
                "SESSION_ID": result.SESSION_ID,
                "agent_messages": result.agent_messages,
                "attempts": attempt,
            }
            if result.error_class == "warning" and result.error:
                payload["warning"] = result.error
            return payload

        if result.outcome == "FATAL":
            log.error("retry: FATAL on attempt %d: %s", attempt, result.error)
            return {
                "success": False,
                "SESSION_ID": result.SESSION_ID or "",
                "agent_messages": result.agent_messages or "",
                "error": result.error,
                "attempts": attempt,
            }

        if attempt > max_retries:
            log.error(
                "retry: exhausted after %d attempts (max_retries=%d): %s",
                attempt, max_retries, result.error,
            )
            return {
                "success": False,
                "SESSION_ID": result.SESSION_ID or "",
                "agent_messages": result.agent_messages or "",
                "error": result.error,
                "attempts": attempt,
            }

        if result.SESSION_ID:
            params.SESSION_ID = result.SESSION_ID
            log.info("retry: preserving SESSION_ID=%s for next attempt", result.SESSION_ID)

        await emit_attempt_failed(
            backend=backend_name,
            session_id=result.SESSION_ID or getattr(params, "SESSION_ID", ""),
            model=getattr(params, "model", ""),
            attempts=attempt,
            error=result.error,
        )
        delay_ms = min(retry_base_ms * (2 ** (attempt - 1)), 8000)
        jitter_factor = random.uniform(0.8, 1.2)
        sleep_s = (delay_ms * jitter_factor) / 1000.0
        log.info("retry: sleeping %.2fs before attempt %d", sleep_s, attempt + 1)
        try:
            await asyncio.sleep(sleep_s)
        except asyncio.CancelledError:
            log.warning("retry: CANCELLED during backoff sleep before attempt %d", attempt + 1)
            raise
        attempt += 1


__all__ = ["run_with_retry"]
