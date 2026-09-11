"""Backend driver registry and normalized execution results."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import threading
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openmcp.backends import BackendResult
from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.claude import ClaudeParams, execute as claude_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.backends.pi import PiParams, execute as pi_execute
from openmcp.config import TargetConfig, validate_target_args

_PRODUCER_SENTINEL = object()


class StreamBridge:
    """Bounded queue bridging provider worker threads to daemon asyncio event loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None, queue_capacity: int = 256) -> None:
        self.loop = loop or asyncio.get_running_loop()
        self.queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=queue_capacity)
        self._closed = False

    def emit(self, event: dict[str, Any]) -> None:
        """Synchronous emitter called on provider worker threads."""
        if self._closed:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self.queue.put(event), self.loop)
            future.result()
        except Exception:
            pass

    def close_producer(self) -> None:
        """Signal end of production from a provider thread."""
        if self._closed:
            return
        self._closed = True
        try:
            future = asyncio.run_coroutine_threadsafe(self.queue.put(_PRODUCER_SENTINEL), self.loop)
            future.result()
        except Exception:
            pass

    async def close(self) -> None:
        """Signal end of production from the event loop."""
        if self._closed:
            return
        self._closed = True
        await self.queue.put(_PRODUCER_SENTINEL)

    async def consumer(self) -> AsyncIterator[dict[str, Any]]:
        """Asynchronously iterate events until producer finishes."""
        while True:
            item = await self.queue.get()
            try:
                if item is _PRODUCER_SENTINEL:
                    break
                yield item
            finally:
                self.queue.task_done()


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


def _target_args(target: TargetConfig) -> tuple[str, ...]:
    """Translate target policy into backend argv.

    Backends only own transport arguments. Provider-specific execution policy
    remains in target configuration and is compiled here.
    """
    validate_target_args(
        target.id,
        target.backend,
        target.args,
        isolated=target.isolated,
    )
    args = list(target.args)
    if target.backend == "agy":
        if target.model:
            args.extend(["--model", target.model])
        return tuple(args)

    if target.backend == "codex":
        if target.backend_profile:
            args.extend(["--profile", target.backend_profile])
        if target.model:
            args.extend(["--model", target.model])
            if target.backend_profile:
                escaped = target.model.replace("\\", "\\\\").replace('"', '\\"')
                args.extend(["-c", f'model="{escaped}"'])
        if target.reasoning:
            args.extend(["-c", f"model_reasoning_effort={target.reasoning}"])
        return tuple(args)

    if target.backend == "pi":
        if target.isolated:
            args.extend(
                [
                    "--no-approve",
                    "--no-context-files",
                    "--no-extensions",
                    "--no-skills",
                    "--no-prompt-templates",
                ]
            )
        else:
            # Append after user args so normal targets cannot disable the
            # daemon's required non-interactive project approval.
            args.append("--approve")
        if target.system_prompt:
            args.extend(["--system-prompt", target.system_prompt])
        if target.read_only:
            args.extend(["--tools", "read,grep,find,ls"])
        if target.model:
            args.extend(["--model", target.model])
        if target.reasoning:
            args.extend(["--thinking", target.reasoning])
        return tuple(args)

    if target.backend == "claude":
        if target.isolated:
            args.extend(["--safe-mode", "--strict-mcp-config"])
        if target.system_prompt:
            args.extend(["--system-prompt", target.system_prompt])
        if target.read_only:
            args.extend(["--tools", "Read,Grep,Glob"])
        if target.model:
            args.extend(["--model", target.model])
        if target.reasoning:
            args.extend(["--effort", target.reasoning])
    return tuple(args)


def _normalize(result: BackendResult) -> DriverResult:
    if result.outcome == "OK":
        outcome: DriverOutcome = "SUCCESS"
    elif result.error_class == "cancelled":
        outcome = "CANCELLED"
    elif result.error_class == "bad_cd":
        outcome = "REQUEST_FATAL"
    elif result.error_class in {"missing_cli", "fatal_backend", "invalid_args"}:
        outcome = "TARGET_FATAL"
    else:
        outcome = "RETRYABLE"
    return DriverResult(
        outcome=outcome,
        session_id=result.SESSION_ID,
        text=result.agent_messages,
        error=result.error,
        error_code=result.error_class,
    )


class DriverRegistry:
    def __init__(self) -> None:
        self._capability_cache: dict[str, bool] = {}

    @staticmethod
    def available(target: TargetConfig) -> bool:
        return shutil.which(target.backend) is not None

    def supports_structured_streaming(
        self,
        target: TargetConfig,
        version_check: Callable[[str], bool] | None = None,
    ) -> bool:
        """Pre-execution capability check for structured streaming with caching per executable path."""
        resolved = shutil.which(target.backend)
        if resolved is None:
            return False
        if resolved in self._capability_cache:
            return self._capability_cache[resolved]

        if version_check is not None:
            supported = version_check(resolved)
        else:
            supported = self._detect_structured_mode(target.backend, resolved)

        self._capability_cache[resolved] = supported
        return supported

    @staticmethod
    def _detect_structured_mode(backend: str, executable_path: str) -> bool:
        """Check if resolved provider CLI supports the required structured output flags."""
        help_cmd = [executable_path, "exec", "--help"] if backend == "codex" else [executable_path, "--help"]
        try:
            completed = subprocess.run(
                help_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=5,
                check=False,
            )
            help_text = completed.stdout or ""
        except Exception:
            return False

        if backend == "claude":
            return "stream-json" in help_text and "--include-partial-messages" in help_text
        if backend == "agy":
            return "stream-json" in help_text
        if backend == "codex":
            return "--json" in help_text
        if backend == "pi":
            return "--mode" in help_text
        return False

    async def execute(
        self,
        *,
        target: TargetConfig,
        prompt: str,
        cwd: Path,
        session_id: str,
        timeout_s: int,
        cancel_event: threading.Event,
        emitter: Callable[[dict[str, Any]], None] | None = None,
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
        if target.backend == "agy":
            result = await agy_execute(
                AgyParams(
                    PROMPT=prompt,
                    cd=cwd,
                    SESSION_ID=session_id,
                    args=args,
                    timeout_s=timeout_s,
                    cancel_event=cancel_event,
                    emitter=emitter,
                )
            )
        elif target.backend == "codex":
            result = await codex_execute(
                CodexParams(
                    PROMPT=prompt,
                    cd=cwd,
                    SESSION_ID=session_id,
                    args=args,
                    timeout_s=timeout_s,
                    cancel_event=cancel_event,
                    emitter=emitter,
                )
            )
        elif target.backend == "pi":
            result = await pi_execute(
                PiParams(
                    PROMPT=prompt,
                    cd=cwd,
                    SESSION_ID=session_id,
                    args=args,
                    timeout_s=timeout_s,
                    cancel_event=cancel_event,
                    emitter=emitter,
                )
            )
        elif target.backend == "claude":
            result = await claude_execute(
                ClaudeParams(
                    PROMPT=prompt,
                    cd=cwd,
                    SESSION_ID=session_id,
                    args=args,
                    timeout_s=timeout_s,
                    cancel_event=cancel_event,
                    emitter=emitter,
                )
            )
        else:
            return DriverResult(
                outcome="TARGET_FATAL",
                session_id=session_id,
                text="",
                error=f"Unsupported backend: {target.backend}",
                error_code="invalid_args",
            )
        return _normalize(result)


__all__ = ["DriverOutcome", "DriverRegistry", "DriverResult", "StreamBridge"]
