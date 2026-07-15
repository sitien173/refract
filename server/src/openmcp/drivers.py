"""Backend driver registry and normalized execution results."""

from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from openmcp.backends import BackendResult
from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.backends.pi import PiParams, execute as pi_execute
from openmcp.config import TargetConfig


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


def _normalize(result: BackendResult) -> DriverResult:
    if result.outcome == "OK":
        outcome: DriverOutcome = "SUCCESS"
    elif result.error_class == "cancelled":
        outcome = "CANCELLED"
    elif result.error_class == "bad_cd":
        outcome = "REQUEST_FATAL"
    elif result.error_class in {"missing_cli", "fatal_backend"}:
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
        if target.backend == "agy":
            result = await agy_execute(
                AgyParams(
                    PROMPT=prompt,
                    cd=cwd,
                    SESSION_ID=session_id,
                    model=target.model,
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
                    model=target.model,
                    profile=target.profile,
                    reasoning_effort=target.reasoning,
                    timeout_s=timeout_s,
                    cancel_event=cancel_event,
                )
            )
        else:
            result = await pi_execute(
                PiParams(
                    PROMPT=prompt,
                    cd=cwd,
                    SESSION_ID=session_id,
                    model=target.model,
                    reasoning_effort=target.reasoning,
                    system_prompt=target.system_prompt,
                    isolated=target.isolated,
                    read_only=target.read_only,
                    timeout_s=timeout_s,
                    cancel_event=cancel_event,
                )
            )
        return _normalize(result)


__all__ = ["DriverOutcome", "DriverRegistry", "DriverResult"]
