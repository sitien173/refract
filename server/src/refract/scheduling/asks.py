"""Coordinator ask registry: per-job tokens in memory, question and answer state in the DB."""

from __future__ import annotations

import secrets
import asyncio
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass

from refract.store.database import Database
from refract.scheduling.hub import Hub
from refract.store.questions import JobNotRunning
from refract.models import (
    LIST_JOB_ID_ACTION,
    TERMINAL_STATES,
    UNKNOWN_JOB_MESSAGE,
    ActionResult,
    OrchestrationError,
)
from refract.store.pool import run_db, run_on


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


@dataclass(slots=True)
class _Token:
    value: str
    deadline: float | None


class AskRegistry:
    """Thread-safe registry of per-job tokens. Questions and answers live in the `questions` table."""

    def __init__(self, database: Database, hub: Hub, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._database = database
        self._hub = hub
        self._clock = clock
        self._tokens: dict[str, _Token] = {}
        # Guards only `_tokens`. Never held across DB work, so event-loop callers may take it.
        self._token_lock = threading.Lock()
        # Deadline and issuing token per open question id. Registration, answer acceptance and expiry
        # serialize on `_accept_lock`, which is held across DB work and therefore taken only off the event loop.
        self._deadlines: dict[int, tuple[float, _Token]] = {}
        self._accept_lock = threading.Lock()

    def issue_token(
        self, job_id: str, *, workflow_timeout_s: float = 0, started_at: float | None = None
    ) -> str:
        """Issue a fresh token bound to job_id and its optional workflow deadline."""
        token = secrets.token_urlsafe(32)
        deadline = None
        if workflow_timeout_s > 0:
            deadline = (started_at if started_at is not None else self._clock()) + workflow_timeout_s
        with self._token_lock:
            self._tokens[job_id] = _Token(token, deadline)
        return token

    def revoke_token(self, job_id: str) -> None:
        """Revoke any active token for job_id and wake its pending ask, which then expires its question."""
        with self._token_lock:
            self._tokens.pop(job_id, None)
        self._hub.wake(job_id)

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
        with self._token_lock:
            return self._validate_token_locked(token, job_id)

    def has_pending(self, job_id: str) -> bool:
        """Check whether the job has an open question."""
        return self._database.open_question(job_id) is not None

    def get_pending(self, job_id: str) -> PendingQuestion | None:
        """Return the job's open question, read from the DB."""
        row = self._database.open_question(job_id)
        return None if row is None else PendingQuestion(str(row["id"]), row["text"])

    async def pending(self, job_id: str) -> PendingQuestion | None:
        """`get_pending` on the store executor, for callers on the event loop."""
        return await run_on(self._database.executor, self.get_pending, job_id)

    async def ask(
        self,
        token: str,
        question: str,
        timeout_s: float,
        job_id: str | None = None,
    ) -> str:
        """Persist an open question, then wait for its answer, a timeout, or cancellation.

        The wait is a hub subscription that re-reads the question row on every wake-up.
        """
        cleaned_question = question.strip() if question else ""
        if not cleaned_question:
            raise ValueError("question must be a non-empty string")

        with self._token_lock:
            resolved_job_id = self._validate_token_locked(token, job_id)
            bound = self._tokens[resolved_job_id]
            now = self._clock()
            deadline = now + timeout_s
            if bound.deadline is not None:
                deadline = min(deadline, bound.deadline)
        if deadline <= now:
            return NO_ANSWER_TEXT

        with self._hub.subscribe({resolved_job_id}) as subscription:
            question_id = await self._register_question(resolved_job_id, bound, cleaned_question, deadline)
            if question_id is None:
                raise AskConflictError(f"A question is already pending for job {resolved_job_id}")
            self._hub.publish(resolved_job_id, "question")
            try:
                answer = await self._await_answer(subscription, question_id, resolved_job_id, bound, deadline)
            except BaseException:
                await self._expire_joined(question_id)
                raise
        return NO_ANSWER_TEXT if answer is None else answer

    def _token_is(self, job_id: str, bound: _Token) -> bool:
        with self._token_lock:
            return self._tokens.get(job_id) is bound

    def _register(self, job_id: str, bound: _Token, text: str, deadline: float) -> int | None:
        """Insert the open question while `bound` is still the job's token and the job is still running.

        Revocation only takes `_token_lock`, so the token is checked again after the insert. A revocation
        that lands in between expires the row here, before this call returns, so no question stays
        registered under a revoked token and `deliver_answer` cannot accept one in the gap.
        """
        with self._accept_lock:
            if not self._token_is(job_id, bound):
                raise AskAuthError("Token was revoked")
            try:
                question_id = self._database.ask_question(job_id, text)
            except JobNotRunning:
                raise AskAuthError(f"Job {job_id} is not running") from None
            if question_id is None:
                return None
            self._deadlines[question_id] = (deadline, bound)
            if not self._token_is(job_id, bound):
                self._expire_locked(question_id)
                raise AskAuthError("Token was revoked")
            return question_id

    async def _register_question(self, job_id: str, bound: _Token, text: str, deadline: float) -> int | None:
        """Register on the DB executor; a cancelled caller still joins the insert and expires the row it made."""
        task = asyncio.ensure_future(run_on(self._database.executor, self._register, job_id, bound, text, deadline))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            joined = asyncio.gather(task, return_exceptions=True)
            while not joined.done():
                with suppress(asyncio.CancelledError):
                    await asyncio.shield(joined)
            question_id = joined.result()[0]
            if isinstance(question_id, int):
                await self._expire_joined(question_id)
            raise

    def _expire_locked(self, question_id: int) -> bool:
        """Expire by compare-and-set, then drop the deadline. Caller holds `_accept_lock`."""
        expired = self._database.expire_question(question_id)
        self._deadlines.pop(question_id, None)
        return expired

    def _expire(self, question_id: int) -> bool:
        with self._accept_lock:
            return self._expire_locked(question_id)

    async def _expire_joined(self, question_id: int) -> None:
        """Expire off-loop; a repeated cancellation still waits for the expiry to finish."""
        task = asyncio.ensure_future(run_on(self._database.executor, self._expire, question_id))
        while not task.done():
            with suppress(asyncio.CancelledError):
                await asyncio.shield(task)
        task.result()

    async def _await_answer(self, subscription, question_id: int, job_id: str, bound: _Token, deadline: float) -> str | None:
        while True:
            subscription.clear()
            row = await run_db(self._database.question, question_id)
            if row is not None and row["state"] == "answered":
                return row["answer"]
            revoked = not self._token_is(job_id, bound)
            remaining = deadline - self._clock()
            if row is None or row["state"] == "expired":
                return None
            if revoked or remaining <= 0:
                if await run_on(self._database.executor, self._expire, question_id):
                    return None
                continue  # An answer won the race against the expiry; read it on the next pass.
            await subscription.wait(remaining)

    def deliver_answer(
        self, job_id: str, answer: str, expected_question_id: str | None = None
    ) -> bool:
        """Answer the job's open question by compare-and-set and publish `answer`.

        Returns False when no question is open, the id differs from `expected_question_id`,
        the question's token was revoked, its deadline has passed, or a concurrent answer won.
        The token is checked under `_accept_lock`, so a revocation that returns before this check
        always rejects the answer. That check is the linearization point: an answer whose check
        passed before `revoke_token` popped the token overlaps that revocation and may be ordered
        before it. `revoke_token` never waits for this lock or its DB write, and the question row
        compare-and-set prevents a second outcome.
        """
        with self._accept_lock:
            row = self._database.open_question(job_id)
            if row is None:
                return False
            if expected_question_id is not None and str(row["id"]) != expected_question_id:
                return False
            entry = self._deadlines.get(row["id"])
            if entry is not None and (not self._token_is(job_id, entry[1]) or self._clock() >= entry[0]):
                # The token was revoked or the deadline passed before this answer arrived; expire here so
                # the answer cannot win.
                self._expire_locked(row["id"])
                self._hub.wake(job_id)
                return False
            if not self._database.answer_question(row["id"], answer):
                return False
            self._deadlines.pop(row["id"], None)
        self._hub.publish(job_id, "answer")
        return True


__all__ = [
    "NO_ANSWER_TEXT",
    "AskAuthError",
    "AskConflictError",
    "AskError",
    "AskRegistry",
    "PendingQuestion",
]


MAX_ANSWER_LENGTH = 8192


async def answer_job(
    database: Database, asks: AskRegistry, job_id: str, answer: str, expected_question_id: str | None = None
) -> ActionResult:
    """Deliver a coordinator answer to the job's open question."""
    job = await run_db(database.job, job_id)
    if job is None:
        raise OrchestrationError(UNKNOWN_JOB_MESSAGE, code="unknown_job", next_action=LIST_JOB_ID_ACTION)
    if job.state in TERMINAL_STATES:
        raise OrchestrationError(
            f"Job {job_id} is in terminal state '{job.state}'.",
            code="invalid_state",
            next_action="Inspect using wait; use a new job if appropriate.",
        )
    cleaned = answer if isinstance(answer, str) else ""
    if not cleaned:
        raise OrchestrationError(
            "Answer must be a non-empty string.",
            code="invalid_request",
            next_action="Provide a non-empty answer string.",
        )
    if len(cleaned) > MAX_ANSWER_LENGTH:
        raise OrchestrationError(
            f"Answer exceeds maximum length of {MAX_ANSWER_LENGTH} characters.",
            code="invalid_request",
            next_action=f"Provide an answer up to {MAX_ANSWER_LENGTH} characters.",
        )
    delivered = await run_on(database.executor, asks.deliver_answer, job_id, cleaned, expected_question_id=expected_question_id)
    if not delivered:
        raise OrchestrationError(
            f"No question is pending for job {job_id}, or it expired.",
            code="invalid_state",
            next_action="Inspect using wait; use a new job if appropriate.",
        )
    return ActionResult(success=True, job_id=job_id, state=job.state)
