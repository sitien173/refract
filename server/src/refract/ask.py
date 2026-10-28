"""In-memory coordinator ask registry for worker questions."""

from __future__ import annotations

import asyncio
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from refract.observability import Tracer, job_event

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
    created_at: float = field(default_factory=time.monotonic)


def _resolve_future(future: asyncio.Future[str], result: str, loop: asyncio.AbstractEventLoop) -> None:
    if future.done():
        return
    if loop.is_running():
        loop.call_soon_threadsafe(lambda: not future.done() and future.set_result(result))
    else:
        future.set_result(result)


class AskRegistry:
    """Thread-safe in-memory registry holding per-job tokens and pending questions."""

    def __init__(self, tracer: Tracer | None = None) -> None:
        self.tracer = tracer or Tracer()
        self._tokens: dict[str, str] = {}
        self._revoked_tokens: set[str] = set()
        self._pending: dict[str, PendingQuestion] = {}
        self._deadlines: dict[str, float] = {}
        self._question_waiters: dict[str, list[asyncio.Future[PendingQuestion | None]]] = {}
        self._lock = threading.Lock()

    def issue_token(
        self, job_id: str, *, workflow_timeout_s: float = 0, started_at: float | None = None
    ) -> str:
        """Issue a fresh token bound to job_id and its optional workflow deadline."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            old_token = self._tokens.pop(job_id, None)
            if old_token is not None:
                self._revoked_tokens.add(old_token)
            self._tokens[job_id] = token
            if workflow_timeout_s > 0:
                self._deadlines[job_id] = (started_at if started_at is not None else time.monotonic()) + workflow_timeout_s
            else:
                self._deadlines.pop(job_id, None)
        return token

    def revoke_token(self, job_id: str) -> None:
        """Revoke any active token for job_id and release any pending ask."""
        pending: PendingQuestion | None = None
        with self._lock:
            old_token = self._tokens.pop(job_id, None)
            if old_token is not None:
                self._revoked_tokens.add(old_token)
            self._deadlines.pop(job_id, None)
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
            if secrets.compare_digest(bound_token.encode("utf-8"), token_bytes):
                matched_job_id = j_id
                break

        if matched_job_id is None:
            for rev_token in self._revoked_tokens:
                if secrets.compare_digest(rev_token.encode("utf-8"), token_bytes):
                    raise AskAuthError("Token has been revoked")
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

        Returns the matching job_id on success. Raises AskAuthError if unknown,
        revoked, or bound to a different job.
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
            deadline = self._deadlines.get(resolved_job_id)
            remaining = timeout_s if deadline is None else min(timeout_s, deadline - time.monotonic())
            if remaining <= 0:
                return NO_ANSWER_TEXT
            self._pending[resolved_job_id] = pending
            waiters = self._question_waiters.pop(resolved_job_id, [])

        job_event(self.tracer, resolved_job_id, "question", cleaned_question)
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

    def deliver_answer(self, job_id: str, answer: str) -> bool:
        """Deliver an answer to the pending question for job_id."""
        with self._lock:
            pending = self._pending.pop(job_id, None)

        if pending is None:
            return False

        loop = pending.future.get_loop()
        _resolve_future(pending.future, answer, loop)
        job_event(self.tracer, job_id, "answer", answer)
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
