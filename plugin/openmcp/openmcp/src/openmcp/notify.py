"""Best-effort worker lifecycle notifications."""

from __future__ import annotations

import asyncio
from typing import Any

from openmcp.logging_setup import get_logger

log = get_logger("notify")

_AVAILABLE: bool | None = None
_NOTIFY = None
_ENV_NOTIFY_ENABLED = "OPENMCP_NOTIFY_ENABLED"
_ENV_NOTIFY_TITLE = "OPENMCP_NOTIFY_TITLE"
_ENV_NOTIFY_DESKTOP = "OPENMCP_NOTIFY_DESKTOP"
_ENV_NOTIFY_WEBHOOK = "OPENMCP_NOTIFY_WEBHOOK"
_ENV_NOTIFY_SOUND = "OPENMCP_NOTIFY_SOUND"


def _load_notify() -> Any | None:
    global _AVAILABLE, _NOTIFY

    if _AVAILABLE is not None:
        return _NOTIFY
    try:
        from notify_system import notify
    except ImportError:
        _AVAILABLE = False
        _NOTIFY = None
        log.info("notify_system is unavailable; notifications disabled")
        return None
    _AVAILABLE = True
    _NOTIFY = notify
    return _NOTIFY


def _effective_env() -> dict[str, str]:
    from openmcp.server import _effective_env as server_effective_env

    return server_effective_env()


def _env_truthy(name: str, env: dict[str, str]) -> bool:
    from openmcp.server import _env_truthy as server_env_truthy

    return server_env_truthy(name, env)


def _notify_kwargs(env: dict[str, str], *, backend: str, session_id: str, model: str) -> dict[str, Any]:
    return {
        "title": env.get(_ENV_NOTIFY_TITLE, "openmcp") or "openmcp",
        "context": {
            "backend": backend,
            "session_id": session_id,
            "model": model,
        },
        "desktop": not env.get(_ENV_NOTIFY_DESKTOP, "").strip() or _env_truthy(_ENV_NOTIFY_DESKTOP, env),
        "webhook": _env_truthy(_ENV_NOTIFY_WEBHOOK, env),
        "sound": _env_truthy(_ENV_NOTIFY_SOUND, env),
    }


async def _emit(message: str, *, status: str, backend: str, session_id: str, model: str) -> None:
    env = _effective_env()
    if not _env_truthy(_ENV_NOTIFY_ENABLED, env):
        return
    notify_fn = _load_notify()
    if notify_fn is None:
        return
    kwargs = _notify_kwargs(env, backend=backend, session_id=session_id, model=model)
    kwargs["status"] = status
    try:
        await asyncio.to_thread(notify_fn, message, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        log.warning("Failed to emit notification status=%s backend=%s: %s", status, backend, exc)


async def emit_start(*, backend: str, session_id: str, model: str) -> None:
    await _emit(
        "Worker started",
        status="task_started",
        backend=backend,
        session_id=session_id,
        model=model,
    )


async def emit_finish(*, backend: str, session_id: str, model: str) -> None:
    await _emit(
        "Worker completed",
        status="task_complete",
        backend=backend,
        session_id=session_id,
        model=model,
    )


async def emit_error(*, backend: str, session_id: str, model: str, error: str) -> None:
    await _emit(
        f"Worker failed: {error}",
        status="task_error",
        backend=backend,
        session_id=session_id,
        model=model,
    )


__all__ = [
    "emit_error",
    "emit_finish",
    "emit_start",
]
