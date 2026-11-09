"""Backend driver registry and normalized execution results."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from refract.backends import AsyncEventHandler, BackendParams, BackendResult, agy, claude, codex, pi
from refract.config import TargetConfig, validate_target_args
from refract.logging_setup import get_logger
from refract.processes import prepare_command
from refract.telemetry import TOKEN_KEYS

log = get_logger("drivers")
_BACKENDS = {"agy": agy, "claude": claude, "codex": codex, "pi": pi}
_CANCEL_POLL_S = 0.05

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


def _agy_args(target: TargetConfig, args: list[str]) -> None:
    if target.model:
        args.extend(["--model", target.model])


def _codex_args(target: TargetConfig, args: list[str]) -> None:
    if target.backend_profile:
        args.extend(["--profile", target.backend_profile])
    if target.model:
        args.extend(["--model", target.model])
        if target.backend_profile:
            escaped = target.model.replace("\\", "\\\\").replace('"', '\\"')
            args.extend(["-c", f'model="{escaped}"'])
    if target.reasoning:
        args.extend(["-c", f"model_reasoning_effort={target.reasoning}"])


def _pi_args(target: TargetConfig, args: list[str]) -> None:
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


def _claude_args(target: TargetConfig, args: list[str]) -> None:
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


_ARGS_BUILDERS = {"agy": _agy_args, "codex": _codex_args, "pi": _pi_args, "claude": _claude_args}


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
    build = _ARGS_BUILDERS.get(target.backend)
    if build is not None:
        build(target, args)
    return tuple(args)


def _normalize(result: BackendResult) -> DriverResult:
    if result.outcome == "OK":
        outcome: DriverOutcome = "SUCCESS"
    elif result.error_class == "cancelled":
        outcome = "CANCELLED"
    elif result.error_class in {"bad_cd", "request_fatal"}:
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
        model=result.model,
        tokens=result.tokens,
    )


async def _mirror_cancel(source: threading.Event, target: asyncio.Event) -> None:
    """Set ``target`` once the thread-safe ``source`` is set."""
    while not source.is_set():
        await asyncio.sleep(_CANCEL_POLL_S)
    target.set()


async def _run_async_backend(backend: Any, params: BackendParams, on_event: AsyncEventHandler | None) -> BackendResult:
    cancel = asyncio.Event()
    mirror = asyncio.create_task(_mirror_cancel(params.cancel_event, cancel))
    try:
        return await backend.execute(params, cancel=cancel, on_event=on_event)
    finally:
        mirror.cancel()


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
                prepare_command(help_cmd),
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
        on_event: AsyncEventHandler | None = None,
        env: dict[str, str] | None = None,
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
        backend = _BACKENDS.get(target.backend)
        if backend is None:
            return DriverResult(
                outcome="TARGET_FATAL",
                session_id=session_id,
                text="",
                error=f"Unsupported backend: {target.backend}",
                error_code="invalid_args",
            )
        params = BackendParams(
            PROMPT=prompt,
            cd=cwd,
            SESSION_ID=session_id,
            args=args,
            timeout_s=timeout_s,
            cancel_event=cancel_event,
            env=env,
        )
        return _normalize(await _run_async_backend(backend, params, on_event))


__all__ = ["DriverOutcome", "DriverRegistry", "DriverResult"]
