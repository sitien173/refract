"""Claude Code-oriented MCP v2 tools for durable Refract jobs."""

from __future__ import annotations

import asyncio
import json
import logging
import inspect
import secrets
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

from refract.config import DaemonConfig, load_config, load_task_guide
from refract.dashboard import DashboardState, register_dashboard_routes
from refract.logging_setup import configure as configure_logging, get_logger, log_context
from refract.models import JobSummary, JobView, TERMINAL_STATES
from refract.observability import record_tool_observation
from refract.result_metadata import JobResultMetadata
from refract.workers import run_sync
from refract.runtime import OrchestrationError, Runtime
from refract.workflows import BUILTIN_WORKFLOWS


log = get_logger("server")
_MCP_WAIT_TIMEOUT_S = 3600
_MCP_HEARTBEAT_INTERVAL_S: float = 30.0
_MAX_RESPONSE_CHARS = 30_000
_MAX_RESPONSE_BYTES = 9_000
_MAX_RESULT_PAGE = 24_000
_FORBIDDEN_OUTPUT_KEYS = frozenset(
    {"target_id", "backend", "model", "resource_uri", "config_revision"}
)
_ERROR_FIELDS = frozenset({"code", "message", "next_action", "retryable"})
_ERROR_CODES = frozenset(
    {
        "unknown_project",
        "invalid_path",
        "alias_taken",
        "unknown_job",
        "unknown_profile",
        "invalid_state",
        "config_invalid",
        "daemon_stopping",
        "invalid_request",
        "response_too_large",
        "internal_error",
        "targets_unavailable",
    }
)
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
        retryable: bool = False,
        retry_after_s: int | None = None,
    ) -> None:
        self.code = code if code in _ERROR_CODES else "internal_error"
        self.message = message
        self.next_action = next_action
        self.retryable = bool(retryable)
        self.retry_after_s = retry_after_s if self.code == "targets_unavailable" else None
        super().__init__(self.to_json())

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
            "next_action": self.next_action,
            "retryable": self.retryable,
        }
        if self.code == "targets_unavailable" and self.retry_after_s is not None:
            payload["retry_after_s"] = self.retry_after_s
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), ensure_ascii=False, separators=(",", ":"))


def _public_data(value: Any) -> Any:
    """Remove daemon/provider identity fields recursively from MCP payloads."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        public: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if name.casefold() in _FORBIDDEN_OUTPUT_KEYS:
                continue
            if name == "metadata":
                try:
                    public[name] = JobResultMetadata.model_validate(item).model_dump(mode="json")
                except Exception:
                    public[name] = _public_data(item)
            else:
                public[name] = _public_data(item)
        return public
    if isinstance(value, (list, tuple)):
        return [_public_data(item) for item in value]
    return value


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
    text = json.dumps(_public_data(payload), ensure_ascii=False, separators=(",", ":"))
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


def _public_terminal_error(job: JobView) -> str:
    detail = job.result.error
    if not detail:
        return ""
    if job.state in {"cancelled", "interrupted"}:
        cancellation_causes = {
            "cancelled": "cancelled",
            "cancelled before execution": "cancelled before execution",
            "execution task cancelled": "execution task cancelled",
        }
        if detail in cancellation_causes:
            return cancellation_causes[detail]
    return "Job execution failed. Detailed diagnostics are available in the dashboard."


def _page_terminal_result(
    job: JobView,
    summary: dict[str, Any],
    offset: int,
    *,
    public_error: str = "",
    metadata: Mapping[str, Any] | None = None,
) -> str:
    result_text = job.result.text
    start = min(offset, len(result_text))
    end = min(len(result_text), start + _MAX_RESULT_PAGE)
    raw_meta = metadata if metadata is not None else job.result.metadata
    if hasattr(raw_meta, "model_dump"):
        raw_meta = raw_meta.model_dump(mode="json")
    meta_dict = JobResultMetadata.model_validate(raw_meta).model_dump(mode="json")
    while True:
        page_text = result_text[start:end]
        payload = {
            "job": summary,
            "result": {
                "text": page_text,
                "error": public_error,
                "next_offset": end if end < len(result_text) else None,
                "metadata": meta_dict,
            },
        }
        serialized = json.dumps(_public_data(payload), ensure_ascii=False, separators=(",", ":"))
        if _fits_response(serialized):
            return serialized
        candidate_length = end - start
        if candidate_length <= 1:
            raise RefractError(
                "response_too_large",
                f"Result metadata for job {job.id} exceeds the supported size limit.",
                f"Use the dashboard to inspect job {job.id}; do not resubmit it.",
            )
        reduced_end = start + candidate_length // 2
        if reduced_end >= end:
            raise RefractError(
                "response_too_large",
                f"Result metadata for job {job.id} exceeds the supported size limit.",
                f"Use the dashboard to inspect job {job.id}; do not resubmit it.",
            )
        end = reduced_end


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
        or type(value["retryable"]) is not bool
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
        retryable=True,
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
    return any(
        type(value) is not kinds[allowed[name]["type"]]
        for name, value in arguments.items()
        if allowed[name].get("type") in kinds
    )


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
                "Use one of the nine tools returned by tools/list.",
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

_PROJECT_RESOLVE_DESCRIPTION = "Resolve an existing Git-root directory to a stable project ID. Use once per session. path must name an existing directory. Returns {project:{id,alias,path}}. Errors: invalid_path, alias_taken."
_TASK_GUIDE_DESCRIPTION = "Load workflow and profile choices and project guidance before submission. Returns {workflows,profiles:{default,available},guidance}. Errors: unknown_project, config_invalid, response_too_large."
_JOB_SUBMIT_DESCRIPTION = "Queue a durable coding job. prompt must be self-contained; optionally pass next_target from a failed job's result.metadata.retry.next_target to pin to that candidate. Returns {job:summary}. Errors include targets_unavailable (retry_after_s), invalid_request, unknown_project, unknown_profile, config_invalid, daemon_stopping, response_too_large."
_JOB_WAIT_DESCRIPTION = "Wait for or page a job result. Nonterminal timeouts are normal; repeat with the same job_id. When a running worker asks a question, wait returns early with result.pending_question. Terminal text uses Unicode character offsets. Every terminal page returns result.metadata, including grouped metadata with a live opaque retry.next_target on eligible failed or cancelled jobs. Returns {job:summary,result:{text,error,next_offset,metadata}}. Errors: unknown_job, invalid_request, response_too_large."
_JOB_LIST_DESCRIPTION = "List all active jobs and up to 10 most recently updated terminal jobs for a project. Returns {active,recent,more_recent}. Errors: unknown_project, response_too_large."
_JOB_CANCEL_DESCRIPTION = "Cancel a queued or running job; terminal jobs are returned unchanged. Returns {job:summary}. Errors: unknown_job, response_too_large."
_JOB_RETRY_DESCRIPTION = "Retry a failed, cancelled, or interrupted job; all-open candidates return targets_unavailable with retry_after_s. Returns {job:summary}. Errors: unknown_job, invalid_state, targets_unavailable, response_too_large."
_JOB_ANSWER_DESCRIPTION = "Deliver a coordinator answer (up to 8192 characters) to a running job's pending question. Returns {job:summary}. Errors: unknown_job, invalid_state, invalid_request, response_too_large."
_JOB_REPORT_ERROR_DESCRIPTION = "Report an unexpected job protocol or output anomaly for offline investigation. Persists a durable diagnostic report event without altering execution state. Returns {report:{id,job_id,category,created_at},duplicate}. Errors: unknown_job, invalid_request, response_too_large."


_INSTRUCTIONS = """Refract runs durable coding jobs (consult, implement, review, other) on external agents for a local project. Jobs persist across client disconnects and daemon restarts.

Standard cycle, 4 calls:
1. project_resolve(path=<Git root>) -> project.id. Idempotent; once per session.
2. task_guide(project_id) -> choose workflow and profile from recommendations.
3. job_submit(project_id, workflow, prompt, ...) -> job.id. The prompt must be self-contained; workers do not see this conversation.
4. job_wait(job_id) -> blocks up to 3600 s with progress every 30 s. Read result.text. If result.next_offset is not null, call job_wait(job_id, timeout_s=0, result_offset=<next_offset>) for the next page.

Rules:
- job_wait returning a non-terminal state is not an error. Call job_wait again.
- A dropped connection may mean the daemon restarted. Jobs persist; call job_wait again.
- Reuse context_key to continue a worker session; fresh_session=true starts over.
- On session resume, call job_list(project_id) and reconcile active jobs before submitting new ones.
- Use job_cancel(job_id) to stop queued or running work. Use job_retry(job_id) for eligible terminal jobs.
- Use job_answer(job_id, answer) to answer a running worker question returned in result.pending_question.
- Use job_report_error(job_id, category, expected, observed, report_key) to record unexpected protocol or output anomalies.
- On failed/cancelled job_wait, use result.metadata.retry.next_target with job_submit(next_target=...) for a follow-up on the next healthy target; tokens are opaque and can expire after config changes. result.metadata.retry.retryable reflects a live next target for routing failures. Inspect result.metadata.failure.kind for failure classification.
- targets_unavailable errors include retry_after_s; wait at least that many seconds before retrying.
- Errors are JSON with code, message, next_action, retryable (and retry_after_s for targets_unavailable). Follow next_action."""


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _runtime(ctx: Context) -> Runtime:
    return cast(Runtime, ctx.request_context.lifespan_context)


def _summary(job: JobView) -> dict[str, Any]:
    return JobSummary(
        id=job.id,
        project_id=job.project_id,
        workflow=job.workflow,
        profile=job.profile,
        state=job.state,
        context_key=job.context_key,
        attempts=job.attempts,
        created_at=job.created_at,
        updated_at=job.updated_at,
    ).model_dump(mode="json")


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
            observation_started_ns = time.time_ns()
            extra: dict[str, Any] = {"operation": operation}
            bound = inspect.signature(function).bind_partial(*args, **kwargs)
            tool_input = {key: value for key, value in bound.arguments.items() if key != "ctx"}
            runtime = None
            if context is not None:
                try:
                    runtime = context.request_context.lifespan_context
                except Exception:
                    pass
            tool_tracer = getattr(runtime, "tracer", None)
            output: Any = None
            if operation == "job_wait":
                extra["progress_token_present"] = _progress_token_present(context)
            outcome = "failed"
            error_type = ""
            with log_context(request_id=request_id):
                log.info("MCP tool request started", extra={**extra, "event": "mcp.request_started"})
                try:
                    result = await function(*args, **kwargs)
                    output = result
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
                        exc.code, str(exc), exc.next_action, exc.retryable, exc.retry_after_s
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
                    job_id = tool_input.get("job_id")
                    if operation == "job_submit" and isinstance(output, str):
                        try:
                            job_id = json.loads(output)["job"]["id"]
                        except (KeyError, TypeError, json.JSONDecodeError):
                            job_id = None
                    project_id = tool_input.get("project_id")
                    if operation == "project_resolve" and isinstance(output, str):
                        try:
                            project_id = json.loads(output)["project"]["id"]
                        except (KeyError, TypeError, json.JSONDecodeError):
                            project_id = None
                    record_tool_observation(
                        tool_tracer, name=operation, input=tool_input, output=output,
                        metadata={"outcome": outcome, "error_type": error_type,
                                  "duration_ms": extra["duration_ms"]},
                        start_time_ns=observation_started_ns, end_time_ns=time.time_ns(),
                        job_id=job_id if isinstance(job_id, str) else None,
                        session_id=project_id if isinstance(project_id, str) else None,
                    )
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
    title="Resolve Project",
    description=_PROJECT_RESOLVE_DESCRIPTION,
    annotations=_annotations("Resolve Project", read_only=False, destructive=False, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("project_resolve")
async def project_resolve(
    path: Annotated[str, Field(description="Absolute or home-relative Git-root directory to register.", min_length=1)],
    ctx: Context,
    alias: Annotated[str, Field(description="Optional project alias; omit or pass an empty string for a unique default.")] = "",
) -> str:
    project = await run_sync(_runtime(ctx).resolve_project, path, alias)
    return _render_payload(
        {"project": {"id": project.id, "alias": project.alias, "path": project.root}},
        applied=(
            "Project resolution", project.id,
            f"Use project ID {project.id} in task_guide or job_submit; do not resolve again to recover the result.",
        ),
    )


@_tool(
    title="Task Guide",
    description=_TASK_GUIDE_DESCRIPTION,
    annotations=_annotations("Task Guide", read_only=True, destructive=False, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("task_guide")
async def task_guide(
    project_id: Annotated[str, Field(description="Registered project ID from project_resolve.", min_length=1)],
    ctx: Context,
) -> str:
    runtime = _runtime(ctx)
    project = await run_sync(runtime.database.project, project_id)
    if project is None:
        raise OrchestrationError(
            "Project is not registered.", code="unknown_project",
            next_action="Call project_resolve with the Git root.",
        )
    try:
        catalog = await run_sync(runtime.catalog_for_project_cached, project.id)
        guide = await run_sync(load_task_guide, runtime.config.home, Path(project.root))
    except ValueError as exc:
        raise OrchestrationError(
            "Project task guidance or configuration is unavailable.", code="config_invalid",
            next_action="Fix the project guidance or configuration in the dashboard.",
        ) from exc
    return _render_payload({
        "workflows": sorted(BUILTIN_WORKFLOWS),
        "profiles": {"default": catalog.default_profile, "available": sorted(catalog.profiles)},
        "guidance": guide,
    })


@_tool(
    title="Submit Job",
    description=_JOB_SUBMIT_DESCRIPTION,
    annotations=_annotations("Submit Job", read_only=False, destructive=True, idempotent=False, open_world=True),
    structured_output=False,
)
@_logged_request("job_submit")
async def job_submit(
    project_id: Annotated[str, Field(description="Registered project ID from project_resolve.", min_length=1)],
    workflow: Annotated[Literal[*BUILTIN_WORKFLOWS], Field(description="Workflow selected from task_guide.")],
    prompt: Annotated[str, Field(description="Self-contained instructions visible to the worker.", min_length=1)],
    ctx: Context,
    profile: Annotated[str, Field(description="Available profile from task_guide; empty uses the project's default.")] = "",
    context_key: Annotated[str, Field(description="Session/history scope; empty uses the workflow name.")] = "",
    fresh_session: Annotated[bool, Field(description="Start a new worker session instead of reusing the context.")] = False,
    next_target: Annotated[str, Field(description="Opaque routing token from result.metadata.retry.next_target; omit to use the profile's first available target.")] = "",
) -> str:
    runtime = _runtime(ctx)
    submission = await runtime.submit(
        project_id, workflow, prompt, profile=profile, context_key=context_key,
        fresh_session=fresh_session, next_target=next_target,
    )
    job = await run_sync(runtime.database.job, submission.job_id)
    if job is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": _summary(job)},
        applied=(
            "Job submission", job.id,
            f"Use job ID {job.id} with job_wait or job_list; do not submit the same work again.",
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
                refreshed = await run_sync(runtime.database.job, job_id)
                if refreshed is None:
                    raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call job_list for the project and use a listed job ID.")
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


@_tool(
    title="Wait for Job",
    description=_JOB_WAIT_DESCRIPTION,
    annotations=_annotations("Wait for Job", read_only=True, destructive=False, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("job_wait")
async def job_wait(
    job_id: Annotated[str, Field(description="Job ID returned by job_submit.", min_length=1)],
    ctx: Context,
    timeout_s: Annotated[int, Field(description="Wait duration in seconds; zero reads immediately.", ge=0, le=3600)] = _MCP_WAIT_TIMEOUT_S,
    result_offset: Annotated[int, Field(description="Unicode character offset into terminal result text.", ge=0)] = 0,
) -> str:
    runtime = _runtime(ctx)
    job = await run_sync(runtime.database.job, job_id)
    if job is None:
        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call job_list for the project and use a listed job ID.")
    await _report_progress(ctx, job, 0.0)
    if job.state not in TERMINAL_STATES and timeout_s > 0:
        await _wait_with_progress(runtime, ctx, job_id, timeout_s)
    current = await run_sync(runtime.database.job, job_id)
    if current is None:
        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call job_list for the project and use a listed job ID.")
    summary = _summary(current)
    if current.state not in TERMINAL_STATES:
        pending = runtime.ask_registry.get_pending(job_id) if hasattr(runtime, "ask_registry") else None
        live_meta = await run_sync(runtime.live_result_metadata, current)
        result: dict[str, Any] = {"text": "", "error": "", "next_offset": None}
        tel = live_meta.get("telemetry") if isinstance(live_meta, Mapping) else getattr(live_meta, "telemetry", None)
        completeness = tel.get("completeness") if isinstance(tel, Mapping) else getattr(tel, "completeness", None)
        if completeness in ("complete", "partial"):
            result["metadata"] = live_meta
        if pending is not None:
            result["pending_question"] = {
                "question_id": pending.question_id,
                "text": pending.text,
            }
            next_action = "Call job_answer to answer the pending question."
        else:
            next_action = "Call job_wait again with the same job_id."
        return _render_payload({
            "job": summary,
            "result": result,
            "next_action": next_action,
        })
    return _page_terminal_result(
        current,
        summary,
        result_offset,
        public_error=_public_terminal_error(current),
        metadata=await run_sync(runtime.live_result_metadata, current),
    )


@_tool(
    title="List Jobs",
    description=_JOB_LIST_DESCRIPTION,
    annotations=_annotations("List Jobs", read_only=True, destructive=False, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("job_list")
async def job_list(
    project_id: Annotated[str, Field(description="Registered project ID from project_resolve.", min_length=1)],
    ctx: Context,
) -> str:
    runtime = _runtime(ctx)
    project = await run_sync(runtime.database.project, project_id)
    if project is None:
        raise OrchestrationError("Project is not registered.", code="unknown_project", next_action="Call project_resolve with the Git root.")
    active, recent, more_recent = await run_sync(runtime.database.job_listing, project.id)
    return _render_payload({
        "active": [_summary(runtime.database.job_view(record)) for record in active],
        "recent": [_summary(runtime.database.job_view(record)) for record in recent],
        "more_recent": more_recent,
    })


@_tool(
    title="Cancel Job",
    description=_JOB_CANCEL_DESCRIPTION,
    annotations=_annotations("Cancel Job", read_only=False, destructive=True, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("job_cancel")
async def job_cancel(
    job_id: Annotated[str, Field(description="Job ID returned by job_submit.", min_length=1)],
    ctx: Context,
) -> str:
    runtime = _runtime(ctx)
    job = await run_sync(runtime.database.job, job_id)
    if job is None:
        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call job_list for the project and use a listed job ID.")
    if job.state in TERMINAL_STATES:
        return _render_payload({"job": _summary(job)})
    await runtime.cancel(job_id)
    current = await run_sync(runtime.database.job, job_id)
    if current is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": _summary(current)},
        applied=("Job cancellation", job.id, f"Inspect job {job.id} with job_list; cancellation was applied and must not be repeated blindly."),
    )


@_tool(
    title="Retry Job",
    description=_JOB_RETRY_DESCRIPTION,
    annotations=_annotations("Retry Job", read_only=False, destructive=True, idempotent=False, open_world=True),
    structured_output=False,
)
@_logged_request("job_retry")
async def job_retry(
    job_id: Annotated[str, Field(description="Failed, cancelled, or interrupted job ID.", min_length=1)],
    ctx: Context,
) -> str:
    runtime = _runtime(ctx)
    submission = await runtime.retry(job_id)
    job = await run_sync(runtime.database.job, submission.job_id)
    if job is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": _summary(job)},
        applied=("Job retry", job.id, f"Use job ID {job.id} with job_wait or job_list; do not retry it again blindly."),
    )


@_tool(
    title="Answer Job Question",
    description=_JOB_ANSWER_DESCRIPTION,
    annotations=_annotations("Answer Job Question", read_only=False, destructive=False, idempotent=False, open_world=False),
    structured_output=False,
)
@_logged_request("job_answer")
async def job_answer(
    job_id: Annotated[str, Field(description="Job ID returned by job_submit.", min_length=1)],
    answer: Annotated[str, Field(description="Answer to deliver to the running worker.", min_length=1, max_length=8192)],
    ctx: Context,
) -> str:
    runtime = _runtime(ctx)
    job = await run_sync(runtime.database.job, job_id)
    if job is None:
        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call job_list for the project and use a listed job ID.")
    await runtime.job_answer(job_id, answer)
    current = await run_sync(runtime.database.job, job_id)
    if current is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": _summary(current)},
        applied=("Job answer", job.id, f"Use job ID {job.id} with job_wait or job_list; do not repeat the answer blindly."),
    )


@_tool(
    title="Report Job Error",
    description=_JOB_REPORT_ERROR_DESCRIPTION,
    annotations=_annotations("Report Job Error", read_only=False, destructive=False, idempotent=True, open_world=False),
    structured_output=False,
)
@_logged_request("job_report_error")
async def job_report_error(
    job_id: Annotated[str, Field(description="Job ID returned by job_submit.", min_length=1)],
    category: Annotated[Literal["protocol", "output"], Field(description="Anomaly category: 'protocol' or 'output'.")],
    expected: Annotated[str, Field(description="Expected behavior summary (1-2048 characters).", min_length=1, max_length=2048)],
    observed: Annotated[str, Field(description="Observed behavior summary (1-2048 characters).", min_length=1, max_length=2048)],
    report_key: Annotated[str, Field(description="Client-generated unique opaque key for delivery retries (1-128 ASCII letters, digits, underscores, or hyphens).", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]{1,128}$")],
    ctx: Context,
) -> str:
    runtime = _runtime(ctx)
    result = await runtime.report_error(
        job_id=job_id,
        category=category,
        expected=expected,
        observed=observed,
        report_key=report_key,
    )
    report = result["report"]
    duplicate = bool(result["duplicate"])
    project_id = result.get("project_id", "")
    request_id = _request_id(ctx)

    if not duplicate:
        log.info(
            "Diagnostic error reported",
            extra={
                "event": "job.error_reported",
                "report_id": report["id"],
                "job_id": job_id,
                "project_id": project_id,
                "request_id": request_id,
                "category": category,
            },
        )

    return _render_payload(
        {"report": report, "duplicate": duplicate},
        applied=(
            "Job error report",
            report["id"],
            f"Use report ID {report['id']} to inspect diagnostics; do not submit the same report again.",
        ),
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
        state.csrf_token = secrets.token_urlsafe(32)
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
            state.csrf_token = ""
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


def create_application(
    config: DaemonConfig | None = None,
    *,
    host: str | None = None,
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

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        try:
            async with session_manager.run():
                app.state.runtime = state.runtime
                yield
        finally:
            app.state.runtime = None

    application = Starlette(
        routes=[*register_dashboard_routes(state), Mount("/", app=mcp_application)],
        lifespan=lifespan,
    )
    application.state.refract_dashboard = state
    application.state.mcp = instance
    return application


mcp = create_mcp()


__all__ = [
    "RefractError", "create_application", "job_answer", "job_cancel", "job_list", "job_report_error", "job_retry",
    "job_submit", "job_wait", "mcp", "project_resolve", "task_guide",
]
