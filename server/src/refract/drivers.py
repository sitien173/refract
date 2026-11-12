"""Backend driver registry and normalized execution results."""

from __future__ import annotations

import asyncio
import json
import shutil
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import coding_agent_cli
from coding_agent_cli import Outcome, Request, Result, Usage, events

from refract.config import TargetConfig, validate_target_args
from refract.logging_setup import get_logger
from refract.telemetry import TOKEN_KEYS

log = get_logger("drivers")
_DRIVERS = frozenset(coding_agent_cli.DriverRegistry().names())
_CANCEL_POLL_S = 0.05
_TARGET_FATAL_REQUEST_CODES = frozenset({"invalid_args", "unsupported_option", "invalid_model"})
_REQUEST_FATAL_CODES = frozenset({"bad_cwd", "invalid_prompt"})
# Target fields a backend ignored before the library, which rejects them as unsupported_option.
_IGNORED_FIELDS = {"codex": ("system_prompt",), "agy": ("reasoning", "system_prompt")}

type EventHandler = Callable[[dict[str, Any]], Awaitable[None]]

DriverOutcome = Literal[
    "SUCCESS",
    "RETRYABLE",
    "TARGET_FATAL",
    "REQUEST_FATAL",
    "CANCELLED",
]


@dataclass(slots=True, frozen=True)
class DriverResult:
    outcome: DriverOutcome
    session_id: str
    text: str
    error: str
    error_code: str
    model: str | None = None
    tokens: dict[str, int | None] = field(default_factory=lambda: dict.fromkeys(TOKEN_KEYS))


def _owned_args(target: TargetConfig) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the Refract-owned flags placed before and after ``target.args``."""
    if target.backend == "claude":
        return ("--permission-mode", "bypassPermissions"), ()
    if target.backend == "agy":
        return ("--dangerously-skip-permissions",), ()
    if target.backend == "pi":
        # After user args so targets cannot disable the daemon's required non-interactive project approval.
        return (), ("--approve",)
    if target.backend == "codex":
        # The library rejects `-c` in args when Request.reasoning is set, so Refract carries the codex target
        # fields after target `args`, in the in-tree order, and they win over a conflicting `-c` entry.
        after = []
        if target.backend_profile:
            after += ["--profile", target.backend_profile]
        if target.model:
            after += ["--model", target.model]
            if target.backend_profile:
                after += ["-c", f"model={_toml_string(target.model)}"]
        if target.reasoning:
            after += ["-c", f"model_reasoning_effort={_toml_string(target.reasoning)}"]
        return ("--yolo",), tuple(after)
    return (), ()


def _toml_string(value: str) -> str:
    """Return ``value`` as a TOML basic string for a Codex ``-c`` override."""
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def _target_args(target: TargetConfig) -> tuple[str, ...]:
    """Compile target policy into the argv Refract owns; model, reasoning, and system prompt are Request fields."""
    validate_target_args(target.id, target.backend, target.args)
    before, after = _owned_args(target)
    return (*before, *target.args, *after)


def _policy(target: TargetConfig, field: str) -> str | None:
    """Return a target policy field, or ``None`` when it is unset or the backend ignores it."""
    return None if field in _IGNORED_FIELDS.get(target.backend, ()) else getattr(target, field) or None


def _tokens(usage: Usage) -> dict[str, int | None]:
    return {key: getattr(usage, key) for key in TOKEN_KEYS}


def _outcome(result: Result) -> DriverOutcome:
    code = result.error.code if result.error else ""
    match result.outcome:
        case Outcome.SUCCESS:
            return "SUCCESS"
        case Outcome.CANCELLED:
            return "CANCELLED"
        case Outcome.REQUEST_FATAL if code in _REQUEST_FATAL_CODES:
            return "REQUEST_FATAL"
        case Outcome.REQUEST_FATAL if code == "context_overflow":
            return "RETRYABLE"
        case Outcome.REQUEST_FATAL | Outcome.AGENT_FATAL:
            return "TARGET_FATAL"
        case _:
            return "RETRYABLE"


def _normalize(result: Result) -> DriverResult:
    failed = result.outcome != Outcome.SUCCESS
    return DriverResult(
        outcome=_outcome(result),
        session_id=result.session_id or "",
        text=result.text,
        error=result.error.message if failed and result.error else "",
        error_code=result.error.code if failed and result.error else "",
        model=result.model,
        tokens=_tokens(result.usage),
    )


def _event_dict(event: Any) -> dict[str, Any] | None:
    """Convert a library event to the stored stream row, or ``None`` for events Refract does not store."""
    match event:
        case events.TextDelta():
            kind, data = event.kind, {"text": event.text}
        case events.MessageStarted() | events.MessageCompleted():
            kind, data = event.kind, {}
        case events.ToolStarted():
            kind, data = event.kind, {"tool": event.tool, "activity": event.activity, "input": event.input}
        case events.ToolCompleted():
            kind, data = event.kind, {"status": event.status}
        case events.UsageUpdated():
            kind, data = "telemetry.updated", _tokens(event.usage)
        case _:
            return None
    row: dict[str, Any] = {"kind": kind}
    if event.entity_id is not None:
        row["entity_id"] = event.entity_id
    row["data"] = data
    return row


async def _mirror_cancel(source: threading.Event, target: asyncio.Event) -> None:
    """Set ``target`` once the thread-safe ``source`` is set."""
    while not source.is_set():
        await asyncio.sleep(_CANCEL_POLL_S)
    target.set()


class DriverRegistry:
    def __init__(self) -> None:
        self._capability_cache: dict[str, bool] = {}

    @staticmethod
    def available(target: TargetConfig) -> bool:
        return shutil.which(target.backend) is not None

    async def supports_structured_streaming(
        self, target: TargetConfig, cancel_event: threading.Event | None = None
    ) -> bool:
        """Pre-execution capability check for structured streaming, cached per executable path once known."""
        resolved = shutil.which(target.backend)
        if resolved is None:
            return False
        if resolved in self._capability_cache:
            return self._capability_cache[resolved]
        probe = asyncio.create_task(coding_agent_cli.check(Request(driver=target.backend, prompt="", cwd=Path.cwd())))
        watcher = asyncio.create_task(_mirror_cancel(cancel_event, asyncio.Event())) if cancel_event else None
        try:
            await asyncio.wait([probe, *([watcher] if watcher else [])], return_when=asyncio.FIRST_COMPLETED)
            if not probe.done():
                return False
            capabilities = probe.result()
        finally:
            if watcher:
                watcher.cancel()
            if not probe.done():
                probe.cancel()
                await asyncio.gather(probe, return_exceptions=True)
        if capabilities.structured_streaming is None:
            return False
        self._capability_cache[resolved] = capabilities.structured_streaming
        return capabilities.structured_streaming

    async def execute(
        self,
        *,
        target: TargetConfig,
        prompt: str,
        cwd: Path,
        session_id: str,
        timeout_s: int,
        cancel_event: threading.Event,
        on_event: EventHandler | None = None,
        env: dict[str, str] | None = None,
        on_spawn: Callable[[int], Awaitable[None]] | None = None,
    ) -> DriverResult:
        try:
            args = _target_args(target)
        except ValueError as exc:
            return DriverResult(
                outcome="TARGET_FATAL",
                session_id=session_id,
                text="",
                error=str(exc),
                error_code="invalid_args",
            )
        if target.backend not in _DRIVERS:
            return DriverResult(
                outcome="TARGET_FATAL",
                session_id=session_id,
                text="",
                error=f"Unsupported backend: {target.backend}",
                error_code="invalid_args",
            )
        request = Request(
            driver=target.backend,
            prompt=prompt,
            cwd=cwd,
            session_id=session_id or None,
            model=None if target.backend == "codex" else target.model or None,
            reasoning=None if target.backend == "codex" else _policy(target, "reasoning"),
            system_prompt=_policy(target, "system_prompt"),
            args=args,
            env=env or {},
            timeout_s=timeout_s or None,
        )

        async def forward(event: Any) -> None:
            row = _event_dict(event)
            if row is not None and on_event is not None:
                await on_event(row)

        cancel = asyncio.Event()
        mirror = asyncio.create_task(_mirror_cancel(cancel_event, cancel))
        try:
            result = await coding_agent_cli.run(request, on_event=forward, cancel=cancel, on_spawn=on_spawn)
        finally:
            mirror.cancel()
        return _normalize(result)


__all__ = ["DriverOutcome", "DriverRegistry", "DriverResult"]
