"""The 9 MCP tools: submit, get, wait, cancel, answer, list, card_create, card_move, card_list."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, cast

from mcp.server.mcpserver import Context
from mcp.shared.exceptions import MCPError
from mcp.types import ToolAnnotations
from pydantic import Field

from refract.api.mcp.responses import (
    RefractError,
    _internal_error,
    _fits_response,
    _json,
    _render_payload,
    _request_id,
    render_result,
)
from refract.config import load_guidance
from refract.store.cards import CardError
from refract.logging_setup import get_logger, log_context
from refract.models import TERMINAL_STATES, JobSummary, JobView
from refract.models import UNKNOWN_JOB_MESSAGE, OrchestrationError
from refract.runtime import Runtime
from refract.scheduling.waiting import validate_job_ids
from refract.store.pool import run_db, run_sync
from refract.workflows import BUILTIN_WORKFLOWS

log = get_logger("server")
_MCP_WAIT_TIMEOUT_S = 3600
_MCP_HEARTBEAT_INTERVAL_S: float = 30.0
_LIST_JOB_ID_ACTION = "Call list with the project path and use a listed job ID."
_CARD_NEXT_ACTIONS = {
    "unknown_card": "Call card_list to find the card ID.",
    "invalid_state": "Call card_list to read the current state before retrying.",
    "unknown_job": "Check each job ID with list before retrying.",
    "invalid_request": "Correct the card input and retry.",
}
_FROM_JOB_CONFLICTS = ("prompt", "workflow", "profile", "session")
_TOKEN_KEYS = ("context_used", "context_window", "input", "output", "cache_read", "cache_write")
_TOOL_DEFINITIONS: list[tuple[Callable[..., Any], dict[str, Any]]] = []

_SUBMIT_DESCRIPTION = "Queue a durable coding job in the Git repository that contains path. Pass workflow and a self-contained prompt, or pass from_job to copy a succeeded, failed, cancelled, or interrupted job. from_job excludes prompt, workflow, profile, and session; with it only target and fresh may be set. Without target, the new job uses the target after the source job's last attempt. Returns {job}. Errors: invalid_path, invalid_request, invalid_state, unknown_job, unknown_profile, config_invalid, targets_unavailable, daemon_stopping, response_too_large."
_GET_DESCRIPTION = "Read a job without waiting. Returns {job,result,truncated,result_path,pending_question,failure_kind,next_target,model,duration_ms,tokens,attempts}. Errors: unknown_job, response_too_large."
_WAIT_DESCRIPTION = "Wait for any listed job (1 to 16 distinct IDs) to finish or to ask a question. Nonterminal timeouts are normal; repeat with the same job_ids. Returns the first ready job as {job,result,truncated,result_path,pending_question,failure_kind,next_target,model,duration_ms,tokens}. result is text; when truncated is true the full text is at result_path. Errors: unknown_job, invalid_request, response_too_large."
_LIST_DESCRIPTION = "List active and recent jobs for the Git repository that contains path, with its workflows, profiles, and guidance. Returns {active,recent,workflows,profiles,guidance}. Errors: invalid_path, config_invalid, response_too_large."
_CANCEL_DESCRIPTION = "Cancel a queued or running job. cancel_status is terminated for a queued job, requested for a running job, and already_terminal for a finished job, which is never changed. Returns {job,cancel_status}. Errors: unknown_job, response_too_large."
_ANSWER_DESCRIPTION = "Deliver a coordinator answer (up to 8192 characters) to a running job's pending question. Returns {job}. Errors: unknown_job, invalid_state, invalid_request, response_too_large."
_CARD_CREATE_DESCRIPTION = "Create a card in the todo state for the Git repository that contains path. Optional job_ids link existing jobs. Returns {card}. Errors: invalid_path, unknown_job, invalid_request, response_too_large."
_CARD_MOVE_DESCRIPTION = "Move a card to a state: todo, in_progress, in_review, done, or cancelled. Allowed moves: todo to in_progress or cancelled; in_progress to in_review or cancelled; in_review to done, in_progress, or cancelled. The same state is a no-op that still links new job_ids. Returns {card,moved}. Errors: unknown_card, invalid_state, unknown_job, invalid_request, response_too_large."
_CARD_LIST_DESCRIPTION = "List the cards of the Git repository that contains path, open cards first. Returns {cards,truncated,omitted}; when truncated is true, omitted counts the cards left out. Errors: invalid_path."


def _tool(**options: Any):
    def register(function):
        _TOOL_DEFINITIONS.append((function, options))
        return function
    return register


def tool_definitions() -> list[tuple[Callable[..., Any], dict[str, Any]]]:
    return list(_TOOL_DEFINITIONS)


def _annotations(
    title: str, *, read_only: bool, destructive: bool, idempotent: bool, open_world: bool
) -> ToolAnnotations:
    return ToolAnnotations(
        title=title, read_only_hint=read_only, destructive_hint=destructive,
        idempotent_hint=idempotent, open_world_hint=open_world,
    )


def _runtime(ctx: Context) -> Runtime:
    return cast(Runtime, ctx.request_context.lifespan_context)


def _progress_token_present(context: Any) -> bool:
    if context is None:
        return False
    try:
        request_context = getattr(context, "request_context", None)
        params = getattr(request_context, "params", None) if request_context is not None else None
        meta = params.get("_meta") if isinstance(params, Mapping) else None
        if not isinstance(meta, Mapping):
            return False
        return type(meta.get("progressToken")) in (str, int)
    except Exception:
        return False


def _logged_request[**P, R](operation: str) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    def decorate(function: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(function)
        async def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            context = next(
                (value for value in (*args, *kwargs.values()) if isinstance(value, Context) or hasattr(value, "request_context")),
                None,
            )
            request_id = _request_id(context)
            started_at = time.monotonic()
            extra: dict[str, Any] = {"operation": operation}
            if operation == "wait":
                extra["progress_token_present"] = _progress_token_present(context)
            outcome = "failed"
            error_type = ""
            with log_context(request_id=request_id):
                log.info("MCP tool request started", extra={**extra, "event": "mcp.request_started"})
                try:
                    result = await function(*args, **kwargs)
                    outcome = "success"
                    return result
                except asyncio.CancelledError:
                    outcome = "cancelled"
                    raise
                except (RefractError, MCPError) as exc:
                    error_type = type(exc).__name__
                    raise
                except OrchestrationError as exc:
                    error_type = type(exc).__name__
                    raise RefractError(exc.code, str(exc), exc.next_action, exc.retry_after_s) from exc
                except CardError as exc:
                    error_type = type(exc).__name__
                    raise RefractError(
                        exc.code, exc.message, _CARD_NEXT_ACTIONS.get(exc.code, _CARD_NEXT_ACTIONS["invalid_request"])
                    ) from exc
                except Exception as exc:
                    error_type = type(exc).__name__
                    raise _internal_error(request_id) from exc
                finally:
                    extra.update(event="mcp.request_finished", outcome=outcome,
                                 duration_ms=round((time.monotonic() - started_at) * 1000, 2))
                    if error_type:
                        extra["error_type"] = error_type
                    log.log(logging.INFO if outcome == "success" else logging.WARNING,
                            "MCP tool request finished", extra=extra)
        return wrapped
    return decorate


def _unknown_job() -> OrchestrationError:
    return OrchestrationError(UNKNOWN_JOB_MESSAGE, code="unknown_job", next_action=_LIST_JOB_ID_ACTION)


def _summary(job: JobView, project_root: str) -> dict[str, Any]:
    return JobSummary(
        id=job.id, project=project_root, workflow=job.workflow, profile=job.profile, target_id=job.target_id,
        session=job.session, state=job.state, from_job=job.from_job, created_at=job.created_at, updated_at=job.updated_at,
    ).model_dump(mode="json")


async def _job_payload(runtime: Runtime, job: JobView) -> dict[str, Any]:
    project = await run_db(runtime.database.project, job.project_id)
    return _summary(job, project.root if project is not None else "")


def _attempt(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("seq", "reason", "target", "backend", "model", "state", "failure_kind", "started_at", "finished_at", "duration_ms")
    return {
        **{key: row[key] for key in keys},
        "replay_safe": bool(row["replay_safe"]),
        "tokens": {key: row[f"tok_{key}"] for key in _TOKEN_KEYS},
    }


async def _job_response(runtime: Runtime, job: JobView, *, attempts: bool = False) -> str:
    """The flat `wait` and `get` payload, truncated to the byte limit with the full text in `result_path`."""
    full = job.result.text if job.state in TERMINAL_STATES else ""
    pending = await runtime.ask_registry.pending(job.id)
    payload: dict[str, Any] = {
        "job": await _job_payload(runtime, job),
        "result": full,
        "truncated": False,
        "result_path": None,
        "pending_question": {"question_id": pending.question_id, "text": pending.text} if pending is not None else None,
        "failure_kind": job.result.failure_kind,
        "next_target": job.result.next_target,
        "model": job.result.model,
        "duration_ms": job.result.duration_ms,
        "tokens": job.result.tokens or dict.fromkeys(_TOKEN_KEYS),
    }
    if attempts:
        payload["attempts"] = [_attempt(row) for row in await run_db(runtime.database.job_attempts, job.id)]
    return render_result(payload, full, runtime.database.results_dir, job.id)


@_tool(
    title="Submit Job",
    description=_SUBMIT_DESCRIPTION,
    annotations=_annotations("Submit Job", read_only=False, destructive=True, idempotent=False, open_world=True),
    structured_output=False,
)
@_logged_request("submit")
async def submit(
    path: Annotated[str, Field(description="Absolute or home-relative directory inside the Git repository.", min_length=1)],
    ctx: Context,
    workflow: Annotated[str, Field(description=f"Workflow name: {', '.join(sorted(BUILTIN_WORKFLOWS))}. Required without from_job.")] = "",
    prompt: Annotated[str, Field(description="Self-contained instructions visible to the worker. Required without from_job.")] = "",
    profile: Annotated[str, Field(description="Profile name; empty uses the project's default.")] = "",
    session: Annotated[str, Field(description="Session scope; empty uses the workflow name.")] = "",
    fresh: Annotated[bool | None, Field(description="Start a new worker session instead of reusing the session. With from_job, empty copies the source job.")] = None,
    from_job: Annotated[str, Field(description="Terminal job ID to copy; excludes prompt, workflow, profile, and session.")] = "",
    target: Annotated[str, Field(description="With from_job, the target to pin; empty uses the target after the source job's last attempt.")] = "",
) -> str:
    runtime = _runtime(ctx)
    if from_job:
        given = [name for name, value in zip(_FROM_JOB_CONFLICTS, (prompt, workflow, profile, session)) if value]
        if given:
            raise OrchestrationError(
                f"from_job cannot be combined with {', '.join(given)}.",
                code="invalid_request",
                next_action="Pass either from_job, with optional target and fresh, or workflow and prompt.",
            )
    elif target:
        raise OrchestrationError(
            "target requires from_job.", code="invalid_request",
            next_action="Pass from_job with target, or remove target.",
        )
    project = await run_sync(runtime.resolve_project, path)
    if from_job:
        submission = await runtime.submit_from_job(from_job, project_id=project.id, target=target, fresh=fresh)
    else:
        submission = await runtime.submit(project.id, workflow, prompt, profile=profile, session=session, fresh=bool(fresh))
    job = await run_db(runtime.database.job, submission.job_id)
    if job is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": _summary(job, project.root)},
        applied=("Job submission", job.id, f"Use job ID {job.id} with wait or list; do not submit the same work again."),
    )


@_tool(
    title="Get Job",
    description=_GET_DESCRIPTION,
    annotations=_annotations("Get Job", read_only=True, destructive=False, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("get")
async def get(
    job_id: Annotated[str, Field(description="Job ID returned by submit.", min_length=1)],
    ctx: Context,
) -> str:
    runtime = _runtime(ctx)
    job = await run_db(runtime.database.job, job_id)
    if job is None:
        raise _unknown_job()
    return await _job_response(runtime, job, attempts=True)


async def _report_progress(ctx: Context, job: JobView, progress: float) -> None:
    await ctx.report_progress(
        progress=progress, total=None, message=json.dumps({"state": job.state}, separators=(",", ":")),
    )


async def _wait_with_progress(runtime: Runtime, ctx: Context, job_ids: list[str], timeout_s: int) -> JobView:
    """Wait for the first ready job, reporting a heartbeat for the first ID; return the job to render."""
    interval = float(_MCP_HEARTBEAT_INTERVAL_S) if _MCP_HEARTBEAT_INTERVAL_S > 0 else 30.0
    wait_task = asyncio.create_task(runtime.wait_jobs(job_ids, timeout_s))
    progress = 0.0
    try:
        while not wait_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(wait_task), timeout=interval)
            except TimeoutError:
                # A coarse clock (Windows) can fire the heartbeat timer in the same tick the wait finishes.
                if wait_task.done():
                    break
                refreshed = await run_db(runtime.database.job, job_ids[0])
                if refreshed is None:
                    raise _unknown_job() from None
                if refreshed.state in TERMINAL_STATES:
                    return refreshed
                progress += 1.0
                await _report_progress(ctx, refreshed, progress)
        return wait_task.result().job
    finally:
        if not wait_task.done():
            wait_task.cancel()
            result, = await asyncio.gather(wait_task, return_exceptions=True)
            if isinstance(result, Exception):
                log.warning("Job wait cleanup failed", exc_info=result,
                            extra={"event": "job.wait_cleanup_failed", "job_ids": job_ids})


@_tool(
    title="Wait for Job",
    description=_WAIT_DESCRIPTION,
    annotations=_annotations("Wait for Job", read_only=True, destructive=False, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("wait")
async def wait(
    job_ids: Annotated[list[str], Field(description="1 to 16 distinct job IDs returned by submit.")],
    ctx: Context,
    timeout_s: Annotated[int, Field(description="Wait duration in seconds; zero reads immediately.", ge=0, le=3600)] = _MCP_WAIT_TIMEOUT_S,
) -> str:
    runtime = _runtime(ctx)
    ids = validate_job_ids(job_ids)
    jobs = [await run_db(runtime.database.job, job_id) for job_id in ids]
    if any(candidate is None for candidate in jobs):
        raise _unknown_job()
    job = next((candidate for candidate in jobs if candidate.state in TERMINAL_STATES), jobs[0])
    await _report_progress(ctx, jobs[0], 0.0)
    if job.state not in TERMINAL_STATES and timeout_s > 0:
        job = await _wait_with_progress(runtime, ctx, ids, timeout_s)
    current = await run_db(runtime.database.job, job.id)
    if current is None:
        raise _unknown_job()
    return await _job_response(runtime, current)


@_tool(
    title="Cancel Job",
    description=_CANCEL_DESCRIPTION,
    annotations=_annotations("Cancel Job", read_only=False, destructive=True, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("cancel")
async def cancel(
    job_id: Annotated[str, Field(description="Job ID returned by submit.", min_length=1)],
    ctx: Context,
) -> str:
    runtime = _runtime(ctx)
    status = await runtime.cancel_job(job_id)
    current = await run_db(runtime.database.job, job_id)
    if current is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": await _job_payload(runtime, current), "cancel_status": status},
        applied=("Job cancellation", job_id, f"Inspect job {job_id} with get; cancellation was applied and must not be repeated blindly."),
    )


@_tool(
    title="Answer Job Question",
    description=_ANSWER_DESCRIPTION,
    annotations=_annotations("Answer Job Question", read_only=False, destructive=False, idempotent=False, open_world=False),
    structured_output=False,
)
@_logged_request("answer")
async def answer(
    job_id: Annotated[str, Field(description="Job ID returned by submit.", min_length=1)],
    answer: Annotated[str, Field(description="Answer to deliver to the running worker.", min_length=1, max_length=8192)],
    ctx: Context,
) -> str:
    runtime = _runtime(ctx)
    await runtime.job_answer(job_id, answer)
    current = await run_db(runtime.database.job, job_id)
    if current is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": await _job_payload(runtime, current)},
        applied=("Job answer", job_id, f"Use job ID {job_id} with wait; do not repeat the answer blindly."),
    )


@_tool(
    title="List Jobs",
    description=_LIST_DESCRIPTION,
    annotations=_annotations("List Jobs", read_only=True, destructive=False, idempotent=True, open_world=False),
    structured_output=False,
    name="list",
)
@_logged_request("list")
async def list_jobs(
    path: Annotated[str, Field(description="Absolute or home-relative directory inside the Git repository.", min_length=1)],
    ctx: Context,
) -> str:
    runtime = _runtime(ctx)
    project = await run_sync(runtime.resolve_project, path)
    active, recent, _more_recent = await run_db(runtime.database.job_overview, project.id)
    try:
        catalog = await run_sync(runtime.catalog_for_project_cached, project.id)
        guide = await run_sync(load_guidance, runtime.config.home, Path(project.root))
    except ValueError as exc:
        raise OrchestrationError(
            "Project task guidance or configuration is unavailable.", code="config_invalid",
            next_action="Fix the project guidance or configuration in .refract/config.toml.",
        ) from exc
    return _render_payload({
        "active": [_summary(runtime.database.job_view(record), project.root) for record in active],
        "recent": [_summary(runtime.database.job_view(record), project.root) for record in recent],
        "workflows": sorted(BUILTIN_WORKFLOWS),
        "profiles": {"default": catalog.default_profile, "available": sorted(catalog.profiles)},
        "guidance": guide,
    })


def _card_payload(card: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": card["id"], "project": card["project_root"], "title": card["title"], "state": card["state"],
        "job_ids": card["job_ids"], "created_at": card["created_at"], "updated_at": card["updated_at"],
    }


_JOB_IDS = Annotated[
    tuple[Annotated[str, Field(min_length=1, max_length=64)], ...],
    Field(description="Existing job IDs to link; at most 16 per call.", max_length=16),
]


@_tool(
    title="Create Card",
    description=_CARD_CREATE_DESCRIPTION,
    annotations=_annotations("Create Card", read_only=False, destructive=False, idempotent=False, open_world=False),
    structured_output=False,
)
@_logged_request("card_create")
async def card_create(
    path: Annotated[str, Field(description="Absolute or home-relative directory inside the Git repository.", min_length=1)],
    title: Annotated[str, Field(description="Card title, 1 to 200 characters.", min_length=1, max_length=200)],
    ctx: Context,
    body: Annotated[str, Field(description="Card details, at most 4000 characters.")] = "",
    job_ids: _JOB_IDS = (),
) -> str:
    runtime = _runtime(ctx)
    card = _card_payload(await run_sync(runtime.card_create, path, title, body, job_ids))
    return _render_payload(
        {"card": card},
        applied=("Card creation", card["id"], "Inspect the card with card_list before retrying. The card was created."),
    )


@_tool(
    title="Move Card",
    description=_CARD_MOVE_DESCRIPTION,
    annotations=_annotations("Move Card", read_only=False, destructive=False, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("card_move")
async def card_move(
    card_id: Annotated[str, Field(description="Card ID returned by card_create or card_list.", min_length=1)],
    state: Annotated[str, Field(description="Target state: todo, in_progress, in_review, done, or cancelled.", min_length=1)],
    ctx: Context,
    job_ids: _JOB_IDS = (),
    note: Annotated[str, Field(description="Reason for the move, at most 1000 characters.")] = "",
) -> str:
    runtime = _runtime(ctx)
    result = await run_sync(runtime.card_move, card_id, state, job_ids, note)
    card = _card_payload(result["card"])
    return _render_payload(
        {"card": card, "moved": result["moved"]},
        applied=("Card move", card["id"], "Inspect the card with card_list before retrying. The move was applied."),
    )


@_tool(
    title="List Cards",
    description=_CARD_LIST_DESCRIPTION,
    annotations=_annotations("List Cards", read_only=True, destructive=False, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("card_list")
async def card_list(
    path: Annotated[str, Field(description="Absolute or home-relative directory inside the Git repository.", min_length=1)],
    ctx: Context,
) -> str:
    runtime = _runtime(ctx)
    listing = await run_sync(runtime.card_list, path)
    cards = [
        {key: card[key] for key in ("id", "title", "state", "job_ids", "updated_at")}
        for card in listing["cards"]
    ]
    low, high = 0, len(cards)
    while low < high:
        middle = (low + high + 1) // 2
        if _fits_response(_json({"cards": cards[:middle], "truncated": middle < len(cards), "omitted": len(cards) - middle})):
            low = middle
        else:
            high = middle - 1
    return _render_payload({"cards": cards[:low], "truncated": low < len(cards), "omitted": len(cards) - low})
