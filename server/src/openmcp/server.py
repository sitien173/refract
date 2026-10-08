"""Claude Code-oriented MCP v2 tools for durable OpenMCP jobs."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
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

from openmcp.config import load_config, load_project_config, load_task_guide
from openmcp.dashboard import DashboardState, register_dashboard_routes
from openmcp.logging_setup import configure as configure_logging, get_logger, log_context
from openmcp.models import ActionResult, JobSummary, JobView, ProjectView, SubmissionResult, TERMINAL_STATES
from openmcp.runtime import OrchestrationError, Runtime
from openmcp.workflows import BUILTIN_WORKFLOWS


log = get_logger("server")
_DAEMON_CONFIG = None
_ACTIVE_RUNTIME: Runtime | None = None
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
        "invalid_dependency",
        "dependency_failed",
        "invalid_state",
        "config_invalid",
        "daemon_stopping",
        "invalid_request",
        "response_too_large",
        "internal_error",
    }
)
_DASHBOARD_STATE = DashboardState()


class OpenMCPError(ToolError):
    """A safe application error represented by one compact JSON object."""

    def __init__(
        self,
        code: str,
        message: str,
        next_action: str,
        retryable: bool = False,
    ) -> None:
        self.code = code if code in _ERROR_CODES else "internal_error"
        self.message = message
        self.next_action = next_action
        self.retryable = bool(retryable)
        super().__init__(self.to_json())

    def to_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "next_action": self.next_action,
            "retryable": self.retryable,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_payload(), ensure_ascii=False, separators=(",", ":"))


def _public_data(value: Any) -> Any:
    """Remove daemon/provider identity fields recursively from MCP payloads."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {
            str(key): _public_data(item)
            for key, item in value.items()
            if str(key).casefold() not in _FORBIDDEN_OUTPUT_KEYS
        }
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


def _openmcp_error_result(error: OpenMCPError) -> CallToolResult:
    text = error.to_json()
    if not _fits_response(text, is_error=True):
        text = OpenMCPError(
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
        raise OpenMCPError(
            "response_too_large",
            "The response metadata exceeds the supported size limit.",
            "Use the dashboard to inspect or reduce the oversized data, then retry.",
        )
    operation, root_id, next_action = applied
    raise OpenMCPError(
        "response_too_large",
        f"{operation} was applied; its response was too large. ID: {root_id}.",
        next_action.format(id=root_id),
    )


def _public_terminal_error(runtime: Runtime, job: JobView) -> str:
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
        allowed_states = {"failed", "cancelled", "interrupted"}
        if job.state == "cancelled":
            for dependency_id in runtime.database.dependencies_for_job(job.id):
                dependency = runtime.database.job_record(dependency_id)
                if dependency is None or dependency.get("state") not in allowed_states:
                    continue
                safe_cause = f"Dependency {dependency_id} ended in state {dependency['state']}"
                if detail == safe_cause:
                    return safe_cause
    return "Job execution failed. Detailed diagnostics are available in the dashboard."


def _page_terminal_result(
    job: JobView,
    summary: dict[str, Any],
    offset: int,
    *,
    public_error: str = "",
) -> str:
    result_text = job.result.text
    start = min(offset, len(result_text))
    end = min(len(result_text), start + _MAX_RESULT_PAGE)
    while True:
        page_text = result_text[start:end]
        payload = {
            "job": summary,
            "result": {
                "text": page_text,
                "error": public_error,
                "next_offset": end if end < len(result_text) else None,
            },
        }
        serialized = json.dumps(_public_data(payload), ensure_ascii=False, separators=(",", ":"))
        if _fits_response(serialized):
            return serialized
        candidate_length = end - start
        if candidate_length <= 1:
            raise OpenMCPError(
                "response_too_large",
                f"Result metadata for job {job.id} exceeds the supported size limit.",
                f"Use the dashboard to inspect job {job.id}; do not resubmit it.",
            )
        reduced_end = start + candidate_length // 2
        if reduced_end >= end:
            raise OpenMCPError(
                "response_too_large",
                f"Result metadata for job {job.id} exceeds the supported size limit.",
                f"Use the dashboard to inspect job {job.id}; do not resubmit it.",
            )
        end = reduced_end


def _valid_openmcp_error(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or set(value) != _ERROR_FIELDS:
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
    """Accept only the SDK's exact tool-error prefix and a valid OpenMCP JSON suffix."""
    prefix = f"Error executing tool {tool_name}: "
    if not text.startswith(prefix):
        return None
    try:
        return _valid_openmcp_error(json.loads(text[len(prefix) :]))
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


def _internal_error(request_id: str) -> OpenMCPError:
    request_suffix = f" Request ID: {request_id[:128]}." if request_id else ""
    return OpenMCPError(
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


def _raw_argument_error(tool_name: str, arguments: Mapping[str, Any] | None) -> bool:
    if arguments is None:
        return False
    expected: dict[str, dict[str, type]] = {
        "project_resolve": {"path": str, "alias": str},
        "task_guide": {"project_id": str},
        "job_submit": {
            "project_id": str, "workflow": str, "prompt": str, "profile": str,
            "context_key": str, "fresh_session": bool, "depends_on": list,
        },
        "job_wait": {"job_id": str, "timeout_s": int, "result_offset": int},
        "job_list": {"project_id": str},
        "job_cancel": {"job_id": str},
        "job_retry": {"job_id": str},
    }
    for name, kind in expected.get(tool_name, {}).items():
        if name not in arguments:
            continue
        value = arguments[name]
        if kind is int:
            if type(value) is not int:
                return True
        elif kind is bool:
            if type(value) is not bool:
                return True
        elif not isinstance(value, kind):
            return True
        if name == "depends_on" and any(not isinstance(item, str) for item in value):
            return True
    return False


def _error_boundary(ctx: Any, call_next: Callable[[Any], Awaitable[Any]]) -> Any:
    """Normalize SDK validation and ToolError results into compact JSON isError results."""
    async def dispatch() -> Any:
        if getattr(ctx, "method", "") != "tools/call":
            return await call_next(ctx)
        request_id = _request_id(ctx)
        tool_name = _tool_name(ctx)
        if _raw_argument_error(tool_name, _raw_arguments(ctx)):
            return _openmcp_error_result(
                OpenMCPError(
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
            return _openmcp_error_result(
                OpenMCPError(
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
            return _openmcp_error_result(_internal_error(request_id))

        if isinstance(result, CallToolResult):
            wire_result: Mapping[str, Any] = result.model_dump(by_alias=True, mode="json", exclude_none=True)
        elif isinstance(result, Mapping):
            wire_result = result
        else:
            return result
        if wire_result.get("isError", wire_result.get("is_error", False)) is True:
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
                return _openmcp_error_result(OpenMCPError(**payload))
            prefix = f"Error executing tool {tool_name}: " if tool_name else ""
            if prefix and error_text.startswith(prefix) and _validation_error_text(error_text[len(prefix) :]):
                return _openmcp_error_result(
                    OpenMCPError(
                        "invalid_request",
                        "Tool arguments are invalid.",
                        "Correct the arguments using the tool schema and call the tool again.",
                    )
                )
            if prefix and error_text.startswith(prefix) and error_text[len(prefix) :].startswith("Unknown tool"):
                return _openmcp_error_result(
                    OpenMCPError(
                        "invalid_request",
                        "The requested tool is not available.",
                        "Use one of the seven tools returned by tools/list.",
                    )
                )
            log.warning(
                "MCP tool returned an unrecognized error",
                extra={"event": "mcp.tool_error_sanitized", "request_id": request_id, "tool": tool_name},
            )
            return _openmcp_error_result(_internal_error(request_id))

        serialized = json.dumps(wire_result, ensure_ascii=False, separators=(",", ":"))
        if len(serialized) >= _MAX_RESPONSE_CHARS or len(serialized.encode("utf-8")) >= _MAX_RESPONSE_BYTES:
            return _openmcp_error_result(
                OpenMCPError(
                    "response_too_large",
                    "The response exceeds the supported size limit.",
                    "Use the dashboard to inspect or reduce the oversized data before retrying.",
                )
            )
        return result

    return dispatch()


@asynccontextmanager
async def _lifespan(_: MCPServer) -> AsyncIterator[Runtime]:
    global _DAEMON_CONFIG, _ACTIVE_RUNTIME
    _DASHBOARD_STATE.runtime = None
    _DASHBOARD_STATE.csrf_token = secrets.token_urlsafe(32)
    runtime: Runtime | None = None
    try:
        config = _DAEMON_CONFIG or load_config()
        configure_logging(config.logging)
        runtime = Runtime(config)
        await runtime.start()
        _ACTIVE_RUNTIME = runtime
        _DASHBOARD_STATE.runtime = runtime
        yield runtime
    finally:
        _ACTIVE_RUNTIME = None
        _DASHBOARD_STATE.runtime = None
        _DASHBOARD_STATE.csrf_token = ""
        try:
            if runtime is not None:
                await runtime.close()
        finally:
            _DAEMON_CONFIG = None


_PROJECT_RESOLVE_DESCRIPTION = "Resolve an existing Git-root directory to a stable project ID. Use once per session. path must name an existing directory. Returns {project:{id,alias,path}}. Errors: invalid_path, alias_taken."
_TASK_GUIDE_DESCRIPTION = "Load workflow and profile choices and project guidance before submission. Returns {workflows,profiles:{default,available},guidance}. Errors: unknown_project, config_invalid, response_too_large."
_JOB_SUBMIT_DESCRIPTION = "Queue a durable coding job. prompt must be self-contained; depends_on lists existing same-project job IDs. Returns {job:summary}. Errors: unknown_project, invalid_request, unknown_profile, invalid_dependency, dependency_failed, config_invalid, daemon_stopping, response_too_large."
_JOB_WAIT_DESCRIPTION = "Wait for or page a job result. Nonterminal timeouts are normal; repeat with the same job_id. Terminal text uses Unicode character offsets. Returns {job:summary,result:{text,error,next_offset}}. Errors: unknown_job, invalid_request, response_too_large."
_JOB_LIST_DESCRIPTION = "List all active jobs and up to 10 most recently updated terminal jobs for a project. Returns {active,recent,more_recent}. Errors: unknown_project, response_too_large."
_JOB_CANCEL_DESCRIPTION = "Cancel a queued or running job; terminal jobs are returned unchanged. Returns {job:summary,cancelled_dependents:[id]}. Errors: unknown_job, response_too_large."
_JOB_RETRY_DESCRIPTION = "Retry a failed, cancelled, or interrupted job. Dependencies must not have failed. Returns {job:summary}. Errors: unknown_job, invalid_state, dependency_failed, response_too_large."


def _tool_error(code: str, message: str, next_action: str, retryable: bool = False) -> OpenMCPError:
    return OpenMCPError(code, message, next_action, retryable)


_INSTRUCTIONS = """OpenMCP runs durable coding jobs (consult, implement, review, other) on external agents for a local project. Jobs persist across client disconnects and daemon restarts.

Standard cycle, 4 calls:
1. project_resolve(path=<Git root>) -> project.id. Idempotent; once per session.
2. task_guide(project_id) -> choose workflow and profile from recommendations.
3. job_submit(project_id, workflow, prompt, ...) -> job.id. The prompt must be self-contained; workers do not see this conversation.
4. job_wait(job_id) -> blocks up to 3600 s with progress every 30 s. Read result.text. If result.next_offset is not null, call job_wait(job_id, timeout_s=0, result_offset=<next_offset>) for the next page.

Rules:
- job_wait returning a non-terminal state is not an error. Call job_wait again.
- A dropped connection may mean the daemon restarted. Jobs persist; call job_wait again.
- Use depends_on=[job ids] to chain jobs without waiting between submits. A failed dependency cancels its dependents.
- Reuse context_key to continue a worker session; fresh_session=true starts over.
- On session resume, call job_list(project_id) and reconcile active jobs before submitting new ones.
- Use job_cancel(job_id) to stop queued or running work. Use job_retry(job_id) only after checking its dependencies.
- Errors are JSON with code, message, next_action, retryable. Follow next_action."""


mcp = MCPServer(
    "openmcp",
    title="OpenMCP job queue",
    instructions=_INSTRUCTIONS,
    version="2.0.0",
    lifespan=_lifespan,
    middleware=[_error_boundary],
)


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _runtime(ctx: Context) -> Runtime:
    return cast(Runtime, ctx.request_context.lifespan_context)


def _summary(runtime: Runtime, job: JobView) -> dict[str, Any]:
    record = runtime.database.job_record(job.id) or {}
    waiting_on, waiting_reason = runtime.waiting_metadata(job.id)
    return JobSummary(
        id=job.id,
        project_id=job.project_id,
        workflow=job.workflow,
        profile=job.profile,
        state=job.state,
        context_key=job.context_key,
        attempts=job.attempts,
        access_mode=record.get("access_mode", "exclusive"),
        depends_on=runtime.database.dependencies_for_job(job.id),
        waiting_on=waiting_on,
        waiting_reason=waiting_reason,
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
            extra_started: dict[str, Any] = {"event": "mcp.request_started", "operation": operation}
            if operation == "job_wait":
                extra_started["progress_token_present"] = _progress_token_present(context)
            with log_context(request_id=request_id):
                log.info("MCP tool request started", extra=extra_started)
                try:
                    result = await function(*args, **kwargs)
                except asyncio.CancelledError:
                    log.warning(
                        "MCP tool request cancelled",
                        extra={
                            "event": "mcp.request_finished", "operation": operation,
                            "outcome": "cancelled", "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                            **({"progress_token_present": _progress_token_present(context)} if operation == "job_wait" else {}),
                        },
                    )
                    raise
                except OpenMCPError:
                    log.warning(
                        "MCP tool request failed",
                        extra={
                            "event": "mcp.request_finished", "operation": operation,
                            "outcome": "failed", "error_type": "OpenMCPError",
                            "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                            **({"progress_token_present": _progress_token_present(context)} if operation == "job_wait" else {}),
                        },
                    )
                    raise
                except OrchestrationError as exc:
                    log.warning(
                        "MCP tool request failed",
                        extra={
                            "event": "mcp.request_finished", "operation": operation,
                            "outcome": "failed", "error_type": "OrchestrationError",
                            "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                            **({"progress_token_present": _progress_token_present(context)} if operation == "job_wait" else {}),
                        },
                    )
                    raise OpenMCPError(
                        exc.code, str(exc), exc.next_action, exc.retryable
                    ) from exc
                except MCPError:
                    raise
                except Exception as exc:
                    log.warning(
                        "MCP tool request failed",
                        extra={
                            "event": "mcp.request_finished", "operation": operation,
                            "outcome": "failed", "error_type": type(exc).__name__,
                            "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                            **({"progress_token_present": _progress_token_present(context)} if operation == "job_wait" else {}),
                        },
                    )
                    raise _internal_error(request_id) from exc
                log.info(
                    "MCP tool request completed",
                    extra={
                        "event": "mcp.request_finished", "operation": operation,
                        "outcome": "success", "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                        **({"progress_token_present": _progress_token_present(context)} if operation == "job_wait" else {}),
                    },
                )
                return result
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


@mcp.tool(
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
    project = _runtime(ctx).resolve_project(path, alias)
    return _render_payload(
        {"project": {"id": project.id, "alias": project.alias, "path": project.root}},
        applied=(
            "Project resolution", project.id,
            f"Use project ID {project.id} in task_guide or job_submit; do not resolve again to recover the result.",
        ),
    )


@mcp.tool(
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
    project = runtime.database.project(project_id)
    if project is None:
        raise OrchestrationError(
            "Project is not registered.", code="unknown_project",
            next_action="Call project_resolve with the Git root.",
        )
    try:
        catalog = runtime.catalog_for_project_cached(project.id)
        guide = load_task_guide(runtime.config.home, Path(project.root))
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


@mcp.tool(
    title="Submit Job",
    description=_JOB_SUBMIT_DESCRIPTION,
    annotations=_annotations("Submit Job", read_only=False, destructive=True, idempotent=False, open_world=True),
    structured_output=False,
)
@_logged_request("job_submit")
async def job_submit(
    project_id: Annotated[str, Field(description="Registered project ID from project_resolve.", min_length=1)],
    workflow: Annotated[Literal["consult", "implement", "review", "other"], Field(description="Workflow selected from task_guide.")],
    prompt: Annotated[str, Field(description="Self-contained instructions visible to the worker.", min_length=1)],
    ctx: Context,
    profile: Annotated[str, Field(description="Available profile from task_guide; empty uses the project's default.")] = "",
    context_key: Annotated[str, Field(description="Session/history scope; empty uses the workflow name.")] = "",
    fresh_session: Annotated[bool, Field(description="Start a new worker session instead of reusing the context.")] = False,
    depends_on: Annotated[list[str], Field(description="Existing same-project job IDs that must succeed first.")] = Field(default_factory=list),
) -> str:
    runtime = _runtime(ctx)
    submission = await runtime.submit(
        project_id, workflow, prompt, profile=profile, context_key=context_key,
        fresh_session=fresh_session, depends_on=depends_on,
    )
    job = runtime.database.job(submission.job_id)
    if job is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": _summary(runtime, job)},
        applied=(
            "Job submission", job.id,
            f"Use job ID {job.id} with job_wait or job_list; do not submit the same work again.",
        ),
    )


async def _report_progress(ctx: Context, job: JobView, runtime: Runtime, progress: float) -> None:
    _waiting_on, waiting_reason = runtime.waiting_metadata(job.id)
    await ctx.report_progress(
        progress=progress,
        total=None,
        message=json.dumps({"state": job.state, "waiting_reason": waiting_reason}, separators=(",", ":")),
    )


@mcp.tool(
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
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, int) or not 0 <= timeout_s <= _MCP_WAIT_TIMEOUT_S:
        raise _tool_error("invalid_request", "timeout_s is outside the supported range.", "Use an integer from 0 through 3600.")
    if isinstance(result_offset, bool) or not isinstance(result_offset, int) or result_offset < 0:
        raise _tool_error("invalid_request", "result_offset must be a nonnegative integer.", "Use a nonnegative character offset.")
    runtime = _runtime(ctx)
    job = runtime.database.job(job_id)
    if job is None:
        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call job_list for the project and use a listed job ID.")
    await _report_progress(ctx, job, runtime, 0.0)
    if job.state not in TERMINAL_STATES and timeout_s > 0:
        interval = float(_MCP_HEARTBEAT_INTERVAL_S) if _MCP_HEARTBEAT_INTERVAL_S > 0 else 30.0
        wait_task = asyncio.create_task(runtime.wait(job_id, timeout_s))
        progress = 0.0
        try:
            while not wait_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(wait_task), timeout=interval)
                except TimeoutError:
                    refreshed = runtime.database.job(job_id)
                    if refreshed is None:
                        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call job_list for the project and use a listed job ID.")
                    if refreshed.state in TERMINAL_STATES:
                        break
                    progress += 1.0
                    await _report_progress(ctx, refreshed, runtime, progress)
        finally:
            if not wait_task.done():
                wait_task.cancel()
                try:
                    await wait_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
    current = runtime.database.job(job_id)
    if current is None:
        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call job_list for the project and use a listed job ID.")
    summary = _summary(runtime, current)
    if current.state not in TERMINAL_STATES:
        return _render_payload({
            "job": summary,
            "result": {"text": "", "error": "", "next_offset": None},
            "next_action": "Call job_wait again with the same job_id.",
        })
    return _page_terminal_result(
        current,
        summary,
        result_offset,
        public_error=_public_terminal_error(runtime, current),
    )


@mcp.tool(
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
    project = runtime.database.project(project_id)
    if project is None:
        raise OrchestrationError("Project is not registered.", code="unknown_project", next_action="Call project_resolve with the Git root.")
    jobs = runtime.database.jobs(project.id)
    active = [job for job in jobs if job.state not in TERMINAL_STATES]
    terminal = sorted((job for job in jobs if job.state in TERMINAL_STATES), key=lambda job: (job.updated_at, job.id), reverse=True)
    return _render_payload({
        "active": [_summary(runtime, job) for job in active],
        "recent": [_summary(runtime, job) for job in terminal[:10]],
        "more_recent": max(0, len(terminal) - 10),
    })


@mcp.tool(
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
    job = runtime.database.job(job_id)
    if job is None:
        raise OrchestrationError("Job does not exist.", code="unknown_job", next_action="Call job_list for the project and use a listed job ID.")
    if job.state in TERMINAL_STATES:
        return _render_payload({"job": _summary(runtime, job), "cancelled_dependents": []})
    result = await runtime.cancel(job_id)
    current = runtime.database.job(job_id)
    if current is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": _summary(runtime, current), "cancelled_dependents": result.cancelled_dependents},
        applied=("Job cancellation", job.id, f"Inspect job {job.id} with job_list; cancellation was applied and must not be repeated blindly."),
    )


@mcp.tool(
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
    job = runtime.database.job(submission.job_id)
    if job is None:
        raise _internal_error(_request_id(ctx))
    return _render_payload(
        {"job": _summary(runtime, job)},
        applied=("Job retry", job.id, f"Use job ID {job.id} with job_wait or job_list; do not retry it again blindly."),
    )


def create_application(host: str | None = None) -> Starlette:
    config_host = getattr(_DAEMON_CONFIG, "host", "127.0.0.1")
    mcp_application = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=False,
        stateless_http=False,
        host=host or config_host,
    )
    session_manager = mcp.session_manager

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    application = Starlette(
        routes=[*register_dashboard_routes(_DASHBOARD_STATE), Mount("/", app=mcp_application)],
        lifespan=lifespan,
    )
    application.state.openmcp_dashboard = _DASHBOARD_STATE
    return application


__all__ = [
    "OpenMCPError", "create_application", "job_cancel", "job_list", "job_retry",
    "job_submit", "job_wait", "mcp", "project_resolve", "task_guide",
]
