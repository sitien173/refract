"""MCP tools for durable Refract jobs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import tempfile
import time
from importlib.metadata import version as package_version
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path
from typing import Annotated, Any, AsyncIterator, Literal, ParamSpec, TypeVar, cast

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import Field, ValidationError
from starlette.applications import Starlette
from starlette.routing import Mount

from refract.database import CardError
from refract.config import DaemonConfig, load_config, load_guidance, refract_home
from refract.dashboard import DashboardState, register_dashboard_routes
from refract.logging_setup import configure as configure_logging, get_logger, log_context
from refract.models import JobSummary, JobView, TERMINAL_STATES
from refract.workers import run_sync
from refract.runtime import OrchestrationError, Runtime
from refract.workflows import BUILTIN_WORKFLOWS


log = get_logger("server")
_MCP_WAIT_TIMEOUT_S = 3600
_MCP_HEARTBEAT_INTERVAL_S: float = 30.0
_MAX_RESPONSE_CHARS = 30_000
_MAX_RESPONSE_BYTES = 9_000
_ERROR_FIELDS = frozenset({"code", "message", "next_action"})
_ERROR_CODES = frozenset(
    {
        "unknown_project",
        "invalid_path",
        "unknown_job",
        "unknown_profile",
        "invalid_state",
        "config_invalid",
        "daemon_stopping",
        "invalid_request",
        "response_too_large",
        "internal_error",
        "targets_unavailable",
        "unknown_card",
    }
)
_CARD_NEXT_ACTIONS = {
    "unknown_card": "Call card_list to find the card ID.",
    "invalid_state": "Call card_list to read the current state before retrying.",
    "unknown_job": "Check each job ID with list before retrying.",
    "invalid_request": "Correct the card input and retry.",
}
_TOOL_DEFINITIONS: list[tuple[Callable[..., Any], dict[str, Any]]] = []


def _tool(**options: Any):
    def register(function):
        _TOOL_DEFINITIONS.append((function, options))
        return function
    return register


class RefractError(ToolError):
    """A safe application error represented by one compact JSON object."""

    def __init__(
        self,
        code: str,
        message: str,
        next_action: str,
        retry_after_s: int | None = None,
    ) -> None:
        self.code = code if code in _ERROR_CODES else "internal_error"
        self.message = message
        self.next_action = next_action
        self.retry_after_s = retry_after_s if self.code == "targets_unavailable" else None
        super().__init__(self.to_json())

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
            "next_action": self.next_action,
        }
        if self.code == "targets_unavailable" and self.retry_after_s is not None:
            payload["retry_after_s"] = self.retry_after_s
        return payload

    def to_json(self) -> str:
        return _json(self.to_payload())


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _result_envelope_json(text: str, *, is_error: bool = False) -> str:
    result = CallToolResult(
        content=[TextContent(type="text", text=text)],
        is_error=is_error,
    )
    return json.dumps(
        result.model_dump(by_alias=True, mode="json", exclude_none=True),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _fits_response(text: str, *, is_error: bool = False) -> bool:
    envelope = _result_envelope_json(text, is_error=is_error)
    return len(envelope) < _MAX_RESPONSE_CHARS and len(envelope.encode("utf-8")) < _MAX_RESPONSE_BYTES


def _refract_error_result(error: RefractError) -> CallToolResult:
    text = error.to_json()
    if not _fits_response(text, is_error=True):
        text = RefractError(
            "response_too_large",
            "The error response exceeded the supported size limit.",
            "Use the dashboard to inspect or reduce the oversized data before retrying.",
        ).to_json()
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


def _render_payload(
    payload: Any,
    *,
    applied: tuple[str, str, str] | None = None,
) -> str:
    text = _json(payload)
    if _fits_response(text):
        return text
    if applied is None:
        raise RefractError(
            "response_too_large",
            "The response metadata exceeds the supported size limit.",
            "Use the dashboard to inspect or reduce the oversized data, then retry.",
        )
    operation, root_id, next_action = applied
    raise RefractError(
        "response_too_large",
        f"{operation} was applied; its response was too large. ID: {root_id}.",
        next_action.format(id=root_id),
    )


def _valid_refract_error(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    expected = _ERROR_FIELDS | ({"retry_after_s"} if value.get("code") == "targets_unavailable" else set())
    if set(value) != expected:
        return None
    if "retry_after_s" in value and (type(value["retry_after_s"]) is not int or value["retry_after_s"] < 1):
        return None
    if (
        not isinstance(value["code"], str)
        or value["code"] not in _ERROR_CODES
        or not isinstance(value["message"], str)
        or not isinstance(value["next_action"], str)
    ):
        return None
    return value


def _recognized_sdk_error(tool_name: str, text: str) -> dict[str, Any] | None:
    """Accept only the SDK's exact tool-error prefix and a valid Refract JSON suffix."""
    prefix = f"Error executing tool {tool_name}: "
    if not text.startswith(prefix):
        return None
    try:
        return _valid_refract_error(json.loads(text[len(prefix) :]))
    except (TypeError, json.JSONDecodeError):
        return None


def _validation_error_text(text: str) -> bool:
    first_line = text.splitlines()[0] if text else ""
    if first_line.startswith("1 validation error for ") or first_line.startswith("ValidationError:"):
        return True
    count = first_line.split(" ", 1)[0]
    return count.isdigit() and " validation errors for " in first_line


def _request_id(ctx: Any) -> str:
    value = getattr(ctx, "request_id", None)
    if value is None:
        value = getattr(getattr(ctx, "request_context", None), "request_id", None)
    return str(value) if value is not None else ""


def _internal_error(request_id: str) -> RefractError:
    request_suffix = f" Request ID: {request_id[:128]}." if request_id else ""
    return RefractError(
        "internal_error",
        f"An unexpected internal error occurred.{request_suffix}",
        "Retry once, then report the request ID.",
    )


def _tool_name(ctx: Any) -> str:
    params = getattr(ctx, "params", None)
    if isinstance(params, Mapping) and isinstance(params.get("name"), str):
        return str(params["name"])
    return ""


def _raw_arguments(ctx: Any) -> Mapping[str, Any] | None:
    params = getattr(ctx, "params", None)
    if isinstance(params, Mapping):
        arguments = params.get("arguments", {})
        return arguments if isinstance(arguments, Mapping) else None
    arguments = getattr(params, "arguments", None)
    return arguments if isinstance(arguments, Mapping) else None


def _raw_argument_error(schema: Mapping[str, Any], arguments: Mapping[str, Any] | None) -> bool:
    if arguments is None:
        return False
    allowed = schema.get("properties", {})
    if any(name not in allowed for name in arguments):
        return True
    kinds = {"string": str, "integer": int, "boolean": bool}
    if any(
        type(value) is not kinds[allowed[name]["type"]]
        for name, value in arguments.items()
        if allowed[name].get("type") in kinds
    ):
        return True
    for name, value in arguments.items():
        spec = allowed[name]
        if spec.get("type") != "array":
            continue
        if not isinstance(value, list) or len(value) > spec.get("maxItems", len(value)):
            return True
        item = spec.get("items", {})
        if item.get("type") in kinds and any(type(entry) is not kinds[item["type"]] for entry in value):
            return True
        if item.get("type") == "string" and any(
            not item.get("minLength", 0) <= len(entry) <= item.get("maxLength", len(entry)) for entry in value
        ):
            return True
    return False


def _normalize_tool_error(wire_result: Mapping[str, Any], tool_name: str, request_id: str) -> CallToolResult:
    content = wire_result.get("content", [])
    error_text = next(
        (
            str(item.get("text", ""))
            for item in content
            if isinstance(item, Mapping) and item.get("type") == "text"
        ),
        "",
    )
    payload = _recognized_sdk_error(tool_name, error_text)
    if payload is not None:
        return _refract_error_result(RefractError(**payload))
    prefix = f"Error executing tool {tool_name}: " if tool_name else ""
    if prefix and error_text.startswith(prefix) and _validation_error_text(error_text[len(prefix) :]):
        return _refract_error_result(
            RefractError(
                "invalid_request",
                "Tool arguments are invalid.",
                "Correct the arguments using the tool schema and call the tool again.",
            )
        )
    if prefix and error_text.startswith(prefix) and error_text[len(prefix) :].startswith("Unknown tool"):
        return _refract_error_result(
            RefractError(
                "invalid_request",
                "The requested tool is not available.",
                "Use one of the tools returned by tools/list.",
            )
        )
    log.warning(
        "MCP tool returned an unrecognized error",
        extra={"event": "mcp.tool_error_sanitized", "request_id": request_id, "tool": tool_name},
    )
    return _refract_error_result(_internal_error(request_id))


def _normalize_tool_result(result: Any, tool_name: str, request_id: str) -> Any:
    if isinstance(result, CallToolResult):
        wire_result: Mapping[str, Any] = result.model_dump(by_alias=True, mode="json", exclude_none=True)
    elif isinstance(result, Mapping):
        wire_result = result
    else:
        return result
    if wire_result.get("isError", wire_result.get("is_error", False)) is True:
        return _normalize_tool_error(wire_result, tool_name, request_id)

    serialized = json.dumps(wire_result, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) >= _MAX_RESPONSE_CHARS or len(serialized.encode("utf-8")) >= _MAX_RESPONSE_BYTES:
        return _refract_error_result(
            RefractError(
                "response_too_large",
                "The response exceeds the supported size limit.",
                "Use the dashboard to inspect or reduce the oversized data before retrying.",
            )
        )
    return result



async def _dispatch_tool_request(
    ctx: Any, call_next: Callable[[Any], Awaitable[Any]], schemas: Mapping[str, Any],
) -> Any:
    if getattr(ctx, "method", "") != "tools/call":
        return await call_next(ctx)
    request_id = _request_id(ctx)
    tool_name = _tool_name(ctx)
    if tool_name in schemas and _raw_argument_error(schemas[tool_name], _raw_arguments(ctx)):
        return _refract_error_result(
            RefractError(
                "invalid_request",
                "Tool arguments are invalid.",
                "Correct the arguments using the tool schema and call the tool again.",
            )
        )
    try:
        result = await call_next(ctx)
    except asyncio.CancelledError:
        raise
    except ValidationError:
        return _refract_error_result(
            RefractError(
                "invalid_request",
                "Tool arguments are invalid.",
                "Correct the arguments using the tool schema and call the tool again.",
            )
        )
    except MCPError:
        raise
    except Exception as exc:
        log.warning(
            "MCP request failed before tool dispatch",
            extra={"event": "mcp.request_failed", "request_id": request_id, "error_type": type(exc).__name__},
        )
        return _refract_error_result(_internal_error(request_id))

    return _normalize_tool_result(result, tool_name, request_id)


def _error_boundary(ctx: Any, call_next: Callable[[Any], Awaitable[Any]], schemas: Mapping[str, Any]) -> Any:
    """Normalize SDK validation and ToolError results into compact JSON isError results."""
    return _dispatch_tool_request(ctx, call_next, schemas)

_SUBMIT_DESCRIPTION = "Queue a durable coding job in the Git repository that contains path. prompt must be self-contained. Returns {job}. Errors: invalid_path, invalid_request, unknown_profile, config_invalid, targets_unavailable, daemon_stopping, response_too_large."
_WAIT_DESCRIPTION = "Wait for a job to finish or to ask a question. Nonterminal timeouts are normal; repeat with the same job_id. When a running worker asks a question, wait returns early with result.pending_question. Terminal results carry text, truncated, result_path, failure_kind, next_target, model, duration_ms, and tokens. Returns {job,result}. Errors: unknown_job, invalid_request."
_LIST_DESCRIPTION = "List active and recent jobs for the Git repository that contains path, with its workflows, profiles, and guidance. Returns {active,recent,workflows,profiles,guidance}. Errors: invalid_path, config_invalid, response_too_large."
_CANCEL_DESCRIPTION = "Cancel a queued or running job; terminal jobs are returned unchanged. Returns {job}. Errors: unknown_job, response_too_large."
_RETRY_DESCRIPTION = "Create a new job from a succeeded, failed, cancelled, or interrupted job. Without target, the new job uses the next target after the source job's target in profile order; with target, that target is pinned. The source job is not changed. Returns {job} with retry_of set. Errors: unknown_job, invalid_state, invalid_request, targets_unavailable, response_too_large."
_ANSWER_DESCRIPTION = "Deliver a coordinator answer (up to 8192 characters) to a running job's pending question. Returns {job}. Errors: unknown_job, invalid_state, invalid_request, response_too_large."
_CARD_CREATE_DESCRIPTION = "Create a card in the todo state for the Git repository that contains path. Optional job_ids link existing jobs. Returns {card}. Errors: invalid_path, unknown_job, invalid_request, response_too_large."
_CARD_MOVE_DESCRIPTION = "Move a card to a state: todo, in_progress, in_review, done, or cancelled. Allowed moves: todo to in_progress or cancelled; in_progress to in_review or cancelled; in_review to done, in_progress, or cancelled. The same state is a no-op that still links new job_ids. Returns {card,moved}. Errors: unknown_card, invalid_state, unknown_job, invalid_request, response_too_large."
_CARD_LIST_DESCRIPTION = "List the cards of the Git repository that contains path, open cards first. Returns {cards,truncated,omitted}; when truncated is true, omitted counts the cards left out. Errors: invalid_path."

_INSTRUCTIONS = """

Standard cycle: list(path) -> active and recent jobs, workflows, profiles, guidance; submit(path, workflow, prompt) -> job.id; wait(job_id) -> result. Prompts are self-contained. wait blocks up to 3600 s. Read result.text; when result.truncated is true, read the full text at result.result_path.

Rules:
- A nonterminal wait and dropped connections are normal; wait again on the same job.
- Use session to resume a worker session; fresh=true starts a new one. After failure_kind context_overflow, submit again with fresh=true.
- On session resume, call list(path) and reconcile active jobs before submitting.
- When wait returns result.pending_question, call answer(job_id, answer).
- cancel(job_id) stops queued or running work.
- Record orchestrated work as cards: card_create(path, title) -> card; card_move(card_id, state, job_ids) moves it through todo, in_progress, in_review, done, cancelled and links jobs; card_list(path) -> cards.
- retry(job_id) creates a new job on result.next_target of a succeeded, failed, cancelled, or interrupted job. retry(job_id, target=X) pins a target.
- On targets_unavailable, wait retry_after_s seconds before retrying. Follow each error next_action."""


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _runtime(ctx: Context) -> Runtime:
    return cast(Runtime, ctx.request_context.lifespan_context)


def _summary(job: JobView, project_root: str) -> dict[str, Any]:
    return JobSummary(
        id=job.id,
        project=project_root,
        workflow=job.workflow,
        profile=job.profile,
        target=job.target_id,
        session=job.session,
        state=job.state,
        retry_of=job.retry_of,
        created_at=job.created_at,
        updated_at=job.updated_at,
    ).model_dump(mode="json")


async def _job_payload(runtime: Runtime, job: JobView) -> dict[str, Any]:
    project = await run_sync(runtime.database.project, job.project_id)
    return _summary(job, project.root if project is not None else "")


def _tokens(job: JobView) -> dict[str, int | None]:
    return job.result.tokens or dict.fromkeys(("context_used", "context_window", "input", "output", "cache_read", "cache_write"))


async def _wait_response(runtime: Runtime, job: JobView) -> str:
    terminal = job.state in TERMINAL_STATES
    pending = runtime.ask_registry.get_pending(job.id)
    result: dict[str, Any] = {
        "text": job.result.text if terminal else "",
        "truncated": False,
        "result_path": str(runtime.database.result_path(job.id)) if terminal else None,
        "pending_question": {"question_id": pending.question_id, "text": pending.text} if pending is not None else None,
        "failure_kind": job.result.failure_kind,
        "next_target": await run_sync(runtime._next_target, job) if job.state in {"failed", "cancelled"} else None,
        "model": job.result.model,
        "duration_ms": job.result.duration_ms,
        "tokens": _tokens(job),
    }
    payload = {"job": await _job_payload(runtime, job), "result": result}
    if _fits_response(_json(payload)):
        return _json(payload)
    full = job.result.text
    low, high = 0, len(full)
    while low < high:
        middle = (low + high + 1) // 2
        result["text"], result["truncated"] = full[:middle], True
        if _fits_response(_json(payload)):
            low = middle
        else:
            high = middle - 1
    result["text"], result["truncated"] = full[:low], True
    return _render_payload(payload)


def _progress_token_present(context: Any) -> bool:
    if context is None:
        return False
    try:
        request_context = getattr(context, "request_context", None)
        params = getattr(request_context, "params", None) if request_context is not None else None
        meta = params.get("_meta") if isinstance(params, Mapping) else None
        if not isinstance(meta, Mapping):
            return False
        token = meta.get("progressToken")
        return type(token) in (str, int)
    except Exception:
        return False


def _logged_request(operation: str) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    def decorate(function: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
        @wraps(function)
        async def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
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
                    raise RefractError(
                        exc.code, str(exc), exc.next_action, exc.retry_after_s
                    ) from exc
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


def _annotations(
    title: str,
    *,
    read_only: bool,
    destructive: bool,
    idempotent: bool,
    open_world: bool,
) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        read_only_hint=read_only,
        destructive_hint=destructive,
        idempotent_hint=idempotent,
        open_world_hint=open_world,
    )


@_tool(
    title="Submit Job",
    description=_SUBMIT_DESCRIPTION,
    annotations=_annotations("Submit Job", read_only=False, destructive=True, idempotent=False, open_world=True),
    structured_output=False,
)
@_logged_request("submit")
async def submit(
    path: Annotated[str, Field(description="Absolute or home-relative directory inside the Git repository.", min_length=1)],
    workflow: Annotated[Literal[*BUILTIN_WORKFLOWS], Field(description="Workflow name.")],
    prompt: Annotated[str, Field(description="Self-contained instructions visible to the worker.", min_length=1)],
    ctx: Context,
    profile: Annotated[str, Field(description="Profile name; empty uses the project's default.")] = "",
    session: Annotated[str, Field(description="Session scope; empty uses the workflow name.")] = "",
    fresh: Annotated[bool, Field(description="Start a new worker session instead of reusing the session.")] = False,
) -> str:
    runtime = _runtime(ctx)
    project = await run_sync(runtime.resolve_project, path)
    submission = await runtime.submit(project.id, workflow, prompt, profile=profile, session=session, fresh=fresh)
    job = await run_sync(runtime.database.job, submission.job_id)
    if job is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": _summary(job, project.root)},
        applied=(
            "Job submission", job.id,
            f"Use job ID {job.id} with wait or list; do not submit the same work again.",
        ),
    )


async def _report_progress(ctx: Context, job: JobView, progress: float) -> None:
    await ctx.report_progress(
        progress=progress,
        total=None,
        message=json.dumps({"state": job.state}, separators=(",", ":")),
    )


async def _wait_with_progress(runtime: Runtime, ctx: Context, job_id: str, timeout_s: int) -> None:
    interval = float(_MCP_HEARTBEAT_INTERVAL_S) if _MCP_HEARTBEAT_INTERVAL_S > 0 else 30.0
    wait_task = asyncio.create_task(runtime.wait(job_id, timeout_s))
    progress = 0.0
    try:
        while not wait_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(wait_task), timeout=interval)
            except TimeoutError:
                if wait_task.done():
                    # A coarse clock (Windows) can fire the heartbeat timer in the same tick the wait finishes.
                    break
                refreshed = await run_sync(runtime.database.job, job_id)
                if refreshed is None:
                    raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call list with the project path and use a listed job ID.")
                if refreshed.state in TERMINAL_STATES:
                    break
                progress += 1.0
                await _report_progress(ctx, refreshed, progress)
    finally:
        if not wait_task.done():
            wait_task.cancel()
            result, = await asyncio.gather(wait_task, return_exceptions=True)
            if isinstance(result, Exception):
                log.warning("Job wait cleanup failed", exc_info=result,
                            extra={"event": "job.wait_cleanup_failed", "job_id": job_id})


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
    annotations=_annotations("Move Card", read_only=False, destructive=True, idempotent=True, open_world=False),
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


@_tool(
    title="Wait for Job",
    description=_WAIT_DESCRIPTION,
    annotations=_annotations("Wait for Job", read_only=True, destructive=False, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("wait")
async def wait(
    job_id: Annotated[str, Field(description="Job ID returned by submit.", min_length=1)],
    ctx: Context,
    timeout_s: Annotated[int, Field(description="Wait duration in seconds; zero reads immediately.", ge=0, le=3600)] = _MCP_WAIT_TIMEOUT_S,
) -> str:
    runtime = _runtime(ctx)
    job = await run_sync(runtime.database.job, job_id)
    if job is None:
        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call list with the project path and use a listed job ID.")
    await _report_progress(ctx, job, 0.0)
    if job.state not in TERMINAL_STATES and timeout_s > 0:
        await _wait_with_progress(runtime, ctx, job_id, timeout_s)
    current = await run_sync(runtime.database.job, job_id)
    if current is None:
        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call list with the project path and use a listed job ID.")
    return await _wait_response(runtime, current)


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
    active, recent, _more_recent = await run_sync(runtime.database.job_overview, project.id)
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
    job = await run_sync(runtime.database.job, job_id)
    if job is None:
        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call list with the project path and use a listed job ID.")
    if job.state in TERMINAL_STATES:
        return _render_payload({"job": await _job_payload(runtime, job)})
    await runtime.cancel(job_id)
    current = await run_sync(runtime.database.job, job_id)
    if current is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": await _job_payload(runtime, current)},
        applied=("Job cancellation", job.id, f"Inspect job {job.id} with wait; cancellation was applied and must not be repeated blindly."),
    )


@_tool(
    title="Retry Job",
    description=_RETRY_DESCRIPTION,
    annotations=_annotations("Retry Job", read_only=False, destructive=True, idempotent=False, open_world=True),
    structured_output=False,
)
@_logged_request("retry")
async def retry(
    job_id: Annotated[str, Field(description="Succeeded, failed, cancelled, or interrupted job ID.", min_length=1)],
    ctx: Context,
    target: Annotated[str, Field(description="Target to pin; empty uses the next target in profile order.")] = "",
) -> str:
    runtime = _runtime(ctx)
    submission = await runtime.retry(job_id, target)
    job = await run_sync(runtime.database.job, submission.job_id)
    if job is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": await _job_payload(runtime, job)},
        applied=("Job retry", job.id, f"Use job ID {job.id} with wait; do not retry it again blindly."),
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
    job = await run_sync(runtime.database.job, job_id)
    if job is None:
        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call list with the project path and use a listed job ID.")
    await runtime.job_answer(job_id, answer)
    current = await run_sync(runtime.database.job, job_id)
    if current is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": await _job_payload(runtime, current)},
        applied=("Job answer", job.id, f"Use job ID {job.id} with wait; do not repeat the answer blindly."),
    )


def create_mcp(
    config: DaemonConfig | None = None,
    *,
    state: DashboardState | None = None,
    logging_overrides: Mapping[str, str] | None = None,
) -> MCPServer:
    state = state if state is not None else DashboardState()

    @asynccontextmanager
    async def lifespan(_: MCPServer) -> AsyncIterator[Runtime]:
        runtime: Runtime | None = None
        try:
            resolved = config if config is not None else await run_sync(load_config)
            if logging_overrides:
                await run_sync(configure_logging, resolved.logging, overrides=logging_overrides)
            else:
                await run_sync(configure_logging, resolved.logging)
            runtime = await run_sync(Runtime, resolved)
            await runtime.start()
            state.runtime = runtime
            yield runtime
        finally:
            state.runtime = None
            if runtime is not None:
                await runtime.close()

    schemas: dict[str, Any] = {}

    async def error_boundary(ctx: Any, call_next: Callable[[Any], Awaitable[Any]]) -> Any:
        if not schemas:
            schemas.update({tool.name: tool.input_schema for tool in await instance.list_tools()})
        return await _error_boundary(ctx, call_next, schemas)

    instance = MCPServer(
        "refract",
        title="Refract job queue",
        instructions=_INSTRUCTIONS,
        version=package_version("refract"),
        lifespan=lifespan,
        middleware=[error_boundary],
    )
    for function, options in _TOOL_DEFINITIONS:
        instance.tool(**options)(function)
    return instance


def _write_daemon_file(path: Path, host: str, port: int) -> str:
    """Atomically publish a fresh private runtime token; return it, or "" when the file cannot be written."""
    token = secrets.token_hex(32)
    content = json.dumps({"token": token, "host": host, "port": port, "version": package_version("refract")})
    temp = ""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp = tempfile.mkstemp(dir=path.parent, prefix=".daemon.", suffix=".tmp")
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            if os.name != "nt":
                os.fchmod(handle.fileno(), 0o600)
            handle.write(content)
        os.replace(temp, path)
    except OSError:
        log.warning("Runtime token file was not written", exc_info=True, extra={"event": "daemon.token_file_failed"})
        if temp:
            Path(temp).unlink(missing_ok=True)
        return ""
    return token


def _remove_daemon_file(path: Path, token: str) -> None:
    """Remove the runtime token file only when this process wrote its token."""
    try:
        if json.loads(path.read_text(encoding="utf-8")).get("token") == token:
            path.unlink()
    except (OSError, ValueError, AttributeError):
        pass


def create_application(
    config: DaemonConfig | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    logging_overrides: Mapping[str, str] | None = None,
) -> Starlette:
    state = DashboardState()
    instance = create_mcp(config, state=state, logging_overrides=logging_overrides)
    config_host = getattr(config, "host", "127.0.0.1")
    mcp_application = instance.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=False,
        stateless_http=False,
        host=host or config_host,
    )
    session_manager = instance.session_manager
    daemon_file = getattr(config, "home", None) or refract_home()
    daemon_file = daemon_file / "daemon.json"

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        token = ""
        try:
            token = await run_sync(
                _write_daemon_file, daemon_file, host or config_host, port if port is not None else getattr(config, "port", 8765),
            )
            state.shutdown_token = token
            async with session_manager.run():
                app.state.runtime = state.runtime
                yield
        finally:
            app.state.runtime = None
            state.shutdown_token = ""
            if token:
                await run_sync(_remove_daemon_file, daemon_file, token)

    application = Starlette(
        routes=[*register_dashboard_routes(state), Mount("/", app=mcp_application)],
        lifespan=lifespan,
    )
    application.state.refract_dashboard = state
    application.state.mcp = instance
    return application


mcp = create_mcp()


__all__ = [
    "RefractError", "answer", "cancel", "card_create", "card_list", "card_move", "create_application", "list_jobs", "mcp", "retry", "submit", "wait",
]
