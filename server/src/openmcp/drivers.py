"""Backend driver registry and normalized execution results."""

from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openmcp.backends import BackendResult
from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.claude import ClaudeParams, execute as claude_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.backends.pi import PiParams, execute as pi_execute
from openmcp.config import TargetConfig, validate_target_args


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
    @staticmethod
    def available(target: TargetConfig) -> bool:
        return shutil.which(target.backend) is not None

    async def execute(
        self,
        *,
        target: TargetConfig,
        prompt: str,
        cwd: Path,
        session_id: str,
        timeout_s: int,
        cancel_event: threading.Event,
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


__all__ = ["DriverOutcome", "DriverRegistry", "DriverResult"]
