"""Backend interfaces for openmcp."""

from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True)
class BackendResult:
    outcome: Literal["OK", "RETRYABLE", "FATAL"]
    SESSION_ID: str
    agent_messages: str
    error: str
    error_class: str


__all__ = ["BackendResult"]