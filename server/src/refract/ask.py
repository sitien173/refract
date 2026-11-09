"""In-memory coordinator ask registry for worker questions."""

from __future__ import annotations

import asyncio
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any


NO_ANSWER_TEXT = "No answer from coordinator; use your best judgment or end with BLOCKED."


class AskError(Exception):
    """Base exception for ask registry operations."""


class AskAuthError(AskError):
    """Raised when a token is unknown, revoked, or bound to a different job."""


class AskConflictError(AskError):
    """Raised when a question is already pending for a job."""


@dataclass(slots=True)
class PendingQuestion:
    question_id: str
    text: str
    future: asyncio.Future[str]
    deadline: float = 0.0
    created_at: float = field(default_factory=time.monotonic)


@dataclass(slots=True)
class _Token:
    value: str
    deadline: float | None


def _resolve_future(future: asyncio.Future[str], result: str, loop: asyncio.AbstractEventLoop) -> None:
    if future.done():
        return
    try:
        same_loop = asyncio.get_running_loop() is loop
    except RuntimeError:
        same_loop = False
    if same_loop:
        future.set_result(result)
    elif loop.is_running():
        loop.call_soon_threadsafe(lambda: not future.done() and future.set_result(result))
    else:
        future.set_result(result)


class AskRegistry:
    """Thread-safe in-memory registry holding per-job tokens and pending questions."""

    def __init__(self) -> None:
        self._tokens: dict[str, _Token] = {}
        self._pending: dict[str, PendingQuestion] = {}
        self._question_waiters: dict[str, list[asyncio.Future[PendingQuestion | None]]] = {}
        self._lock = threading.Lock()

    def issue_token(
        self, job_id: str, *, workflow_timeout_s: float = 0, started_at: float | None = None
    ) -> str:
        """Issue a fresh token bound to job_id and its optional workflow deadline."""
        token = secrets.token_urlsafe(32)
        deadline = None
        if workflow_timeout_s > 0:
            deadline = (started_at if started_at is not None else time.monotonic()) + workflow_timeout_s
        with self._lock:
            self._tokens[job_id] = _Token(token, deadline)
        return token

    def revoke_token(self, job_id: str) -> None:
        """Revoke any active token for job_id and release any pending ask."""
        pending: PendingQuestion | None = None
        with self._lock:
            self._tokens.pop(job_id, None)
            pending = self._pending.pop(job_id, None)

        if pending is not None:
            loop = pending.future.get_loop()
            _resolve_future(pending.future, NO_ANSWER_TEXT, loop)

    def _validate_token_locked(self, token: str, job_id: str | None = None) -> str:
        if not token:
            raise AskAuthError("Token is empty")

        try:
            token_bytes = token.encode("utf-8")
        except UnicodeEncodeError:
            raise AskAuthError("Token is unknown")

        matched_job_id: str | None = None
        for j_id, bound_token in self._tokens.items():
            if secrets.compare_digest(bound_token.value.encode("utf-8"), token_bytes):
                matched_job_id = j_id
                break

        if matched_job_id is None:
            raise AskAuthError("Token is unknown")

        if job_id is not None:
            try:
                job_id_bytes = job_id.encode("utf-8")
            except UnicodeEncodeError:
                raise AskAuthError(f"Token belongs to job {matched_job_id}, not {job_id}")
            if not secrets.compare_digest(
                matched_job_id.encode("utf-8"), job_id_bytes
            ):
                raise AskAuthError(f"Token belongs to job {matched_job_id}, not {job_id}")

        return matched_job_id

    def validate_token(self, token: str, job_id: str | None = None) -> str:
        """Validate token against active tokens and optional job_id.

        Returns the matching job_id on success. Raises AskAuthError if unknown
        or bound to a different job.
        """
        with self._lock:
            return self._validate_token_locked(token, job_id)

    def has_pending(self, job_id: str) -> bool:
        """Check whether a question is currently pending for job_id."""
        with self._lock:
            return job_id in self._pending

    def get_pending(self, job_id: str) -> PendingQuestion | None:
        """Return the current pending question for job_id, if any."""
        with self._lock:
            return self._pending.get(job_id)

    async def ask(
        self,
        token: str,
        question: str,
        timeout_s: float,
        job_id: str | None = None,
    ) -> str:
        """Post a question, wait for an answer, timeout, or cancellation.

        The wait yields control to the asyncio event loop and never blocks it.
        """
        cleaned_question = question.strip() if question else ""
        if not cleaned_question:
            raise ValueError("question must be a non-empty string")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[str] = loop.create_future()
        pending = PendingQuestion(
            question_id=f"q_{secrets.token_hex(8)}",
            text=cleaned_question,
            future=future,
        )

        with self._lock:
            resolved_job_id = self._validate_token_locked(token, job_id)
            if resolved_job_id in self._pending:
                raise AskConflictError(f"A question is already pending for job {resolved_job_id}")
            now = time.monotonic()
            deadline = now + timeout_s
            workflow_deadline = self._tokens[resolved_job_id].deadline
            if workflow_deadline is not None:
                deadline = min(deadline, workflow_deadline)
            remaining = deadline - now
            if remaining <= 0:
                return NO_ANSWER_TEXT
            pending.deadline = deadline
            self._pending[resolved_job_id] = pending
            waiters = self._question_waiters.pop(resolved_job_id, [])

        for w in waiters:
            if not w.done():
                loop = w.get_loop()
                if loop.is_running():
                    loop.call_soon_threadsafe(lambda f=w, p=pending: not f.done() and f.set_result(p))
                else:
                    w.set_result(pending)

        try:
            return await asyncio.wait_for(future, timeout=remaining)
        except asyncio.TimeoutError:
            with self._lock:
                if self._pending.get(resolved_job_id) is pending:
                    self._pending.pop(resolved_job_id, None)
            return NO_ANSWER_TEXT
        except asyncio.CancelledError:
            with self._lock:
                if self._pending.get(resolved_job_id) is pending:
                    self._pending.pop(resolved_job_id, None)
            raise

    def deliver_answer(
        self, job_id: str, answer: str, expected_question_id: str | None = None
    ) -> bool:
        """Deliver an answer to the pending question for job_id.

        Returns False when no question is pending or the question expired.
        """
        with self._lock:
            pending = self._pending.get(job_id)
            if pending is None:
                return False
            if pending.future.done() or time.monotonic() >= pending.deadline:
                return False
            if expected_question_id is not None and pending.question_id != expected_question_id:
                return False
            del self._pending[job_id]
            _resolve_future(pending.future, answer, pending.future.get_loop())
        return True

    def cancel(self, job_id: str) -> bool:
        """Release any pending question for job_id with the no-answer message."""
        with self._lock:
            pending = self._pending.pop(job_id, None)

        if pending is None:
            return False

        loop = pending.future.get_loop()
        _resolve_future(pending.future, NO_ANSWER_TEXT, loop)
        return True

    async def wait_question(
        self, job_id: str, timeout_s: float | None = None
    ) -> PendingQuestion | None:
        """Wait until a question is pending for job_id, or timeout expires."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[PendingQuestion | None] = loop.create_future()
        with self._lock:
            pending = self._pending.get(job_id)
            if pending is not None:
                return pending
            self._question_waiters.setdefault(job_id, []).append(future)

        try:
            if timeout_s is not None and timeout_s > 0:
                return await asyncio.wait_for(future, timeout=timeout_s)
            return await future
        except asyncio.TimeoutError:
            return None
        finally:
            with self._lock:
                waiters = self._question_waiters.get(job_id)
                if waiters:
                    if future in waiters:
                        waiters.remove(future)
                    if not waiters:
                        self._question_waiters.pop(job_id, None)


__all__ = [
    "NO_ANSWER_TEXT",
    "AskAuthError",
    "AskConflictError",
    "AskError",
    "AskRegistry",
    "PendingQuestion",
]
