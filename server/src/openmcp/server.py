"""MCPServer v2 daemon surface and direct-run compatibility facade."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Literal, ParamSpec, TypeVar, cast

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.subscriptions import InMemorySubscriptionBus
from mcp.shared.subscriptions import ResourceUpdated
from starlette.applications import Starlette
from starlette.routing import Mount

from openmcp.dashboard import DashboardState, register_dashboard_routes

from openmcp.backend_runner import run as _run_backend
from openmcp.backends.agy import execute as agy_execute
from openmcp.backends.claude import execute as claude_execute
from openmcp.backends.codex import execute as codex_execute
from openmcp.backends.pi import execute as pi_execute
from openmcp.config import load_config, load_task_guide
from openmcp.logging_setup import configure as configure_logging, get_logger, log_context
from openmcp.models import ActionResult, DaemonStatusResult, JobSummary, JobView, ProjectView, SubmissionResult, TERMINAL_STATES, TaskGuideResult
from openmcp.runtime import Runtime
from openmcp.workflows import BUILTIN_WORKFLOWS


log = get_logger("server")
_DAEMON_CONFIG = None
_MCP_WAIT_TIMEOUT_S = 300
subscription_bus = InMemorySubscriptionBus()
_DASHBOARD_STATE = DashboardState()
_ACTIVE_RUNTIME = None


async def publish_job_resource(resource_uri: str) -> None:
    await subscription_bus.publish(ResourceUpdated(uri=resource_uri))


@asynccontextmanager
async def _lifespan(_: MCPServer) -> AsyncIterator[Runtime]:
    global _DAEMON_CONFIG, _ACTIVE_RUNTIME
    _DASHBOARD_STATE.runtime = None
    _DASHBOARD_STATE.csrf_token = secrets.token_urlsafe(32)
    runtime: Runtime | None = None
    try:
        config = _DAEMON_CONFIG or load_config()
        configure_logging(config.logging)
        runtime = Runtime(config, notifier=publish_job_resource)
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


mcp = MCPServer("openmcp", lifespan=_lifespan, subscriptions=subscription_bus)


async def run(backend: Literal["agy", "codex", "pi", "claude"], PROMPT: str, cd: str, SESSION_ID: str = "", timeout_s: int = 0) -> dict[str, Any]:
    """Run one backend through the legacy direct-invocation API."""
    return await _run_backend(backend, PROMPT, cd, SESSION_ID, timeout_s, agy_executor=agy_execute, codex_executor=codex_execute, pi_executor=pi_execute, claude_executor=claude_execute)


def _runtime(ctx: Context) -> Runtime:
    return cast(Runtime, ctx.request_context.lifespan_context)


def create_application(host: str | None = None) -> Starlette:
    # Retain compatibility for embedders that publish a runtime before
    # constructing the application; normal daemon operation populates this in
    # the lifespan below.
    if _DASHBOARD_STATE.runtime is None and _ACTIVE_RUNTIME is not None:
        _DASHBOARD_STATE.runtime = _ACTIVE_RUNTIME
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
    # Keep the state owned by OpenMCP, rather than accepting runtime or token
    # values from request data or forwarded headers.
    application.state.openmcp_dashboard = _DASHBOARD_STATE
    return application


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _logged_request(operation: str) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    def decorate(function: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
        @wraps(function)
        async def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            context = next((value for value in (*args, *kwargs.values()) if isinstance(value, Context)), None)
            request_id = context.request_id if context is not None else ""
            started_at = time.monotonic()
            with log_context(request_id=request_id):
                log.info("MCP tool request started", extra={"event": "mcp.request_started", "operation": operation})
                try:
                    result = await function(*args, **kwargs)
                except asyncio.CancelledError:
                    log.warning("MCP tool request cancelled", extra={"event": "mcp.request_finished", "operation": operation, "outcome": "cancelled", "duration_ms": round((time.monotonic() - started_at) * 1000, 2)})
                    raise
                except Exception as exc:
                    log.warning("MCP tool request failed", extra={"event": "mcp.request_finished", "operation": operation, "outcome": "failed", "error_type": type(exc).__name__, "duration_ms": round((time.monotonic() - started_at) * 1000, 2)})
                    raise
                log.info("MCP tool request completed", extra={"event": "mcp.request_finished", "operation": operation, "outcome": "success", "duration_ms": round((time.monotonic() - started_at) * 1000, 2)})
                return result
        return wrapped
    return decorate


@mcp.tool(description="Register a project directory.", structured_output=True)
@_logged_request("project_register")
async def project_register(path: str, ctx: Context, alias: str = "") -> ProjectView:
    return _runtime(ctx).register_project(path, alias)


@mcp.tool(description="Return the daemon scheduler status.", structured_output=True)
@_logged_request("status")
async def status(ctx: Context) -> DaemonStatusResult:
    return _runtime(ctx).status()


@mcp.tool(description="Load task guidance for choosing a workflow and profile.", structured_output=True)
@_logged_request("task_guide")
async def task_guide(ctx: Context, project_id: str = "") -> TaskGuideResult:
    runtime = _runtime(ctx)
    project_root = None
    if project_id.strip():
        project = runtime.database.project(project_id)
        if project is None:
            raise ValueError(f"Unknown project: {project_id.strip()}")
        project_root = Path(project.root)
    return TaskGuideResult(guide=load_task_guide(runtime.config.home, project_root))


@mcp.tool(description="Queue a durable project workflow.", structured_output=True)
@_logged_request("job_submit")
async def job_submit(project_id: str, workflow: str, prompt: str, ctx: Context, context_key: str = "", profile: str = "", fresh_session: bool = False) -> SubmissionResult:
    return await _runtime(ctx).submit(project_id, workflow, prompt, context_key=context_key, profile=profile, fresh_session=fresh_session)


@mcp.tool(description="Wait for a job to complete in a background task, or until timeout.", structured_output=True)
@_logged_request("job_wait")
async def job_wait(job_id: str, ctx: Context, timeout_s: int = _MCP_WAIT_TIMEOUT_S) -> JobView:
    if timeout_s < 0:
        raise ValueError("timeout_s cannot be negative")
    timeout_s = min(timeout_s or _MCP_WAIT_TIMEOUT_S, _MCP_WAIT_TIMEOUT_S)
    runtime = _runtime(ctx)
    job = runtime.database.job(job_id)
    if job is None:
        raise ValueError(f"Unknown job: {job_id}")
    await ctx.report_progress(progress=1.0 if job.state in TERMINAL_STATES else 0.0, total=1.0, message=job.state)
    if job.state in TERMINAL_STATES:
        return job
    await runtime.wait(job_id, timeout_s)
    refreshed = runtime.database.job(job_id)
    if refreshed is None:
        raise ValueError(f"Unknown job: {job_id}")
    await ctx.report_progress(progress=1.0 if refreshed.state in TERMINAL_STATES else 0.0, total=1.0, message=refreshed.state)
    return refreshed


@mcp.tool(description="Cancel a queued or running job.", structured_output=True)
@_logged_request("job_cancel")
async def job_cancel(job_id: str, ctx: Context) -> ActionResult:
    return await _runtime(ctx).cancel(job_id)


@mcp.tool(description="Retry a failed or interrupted job.", structured_output=True)
@_logged_request("job_retry")
async def job_retry(job_id: str, ctx: Context) -> SubmissionResult:
    return await _runtime(ctx).retry(job_id)


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif isinstance(value, list):
        value = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in value]
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@mcp.resource("openmcp://projects{?scope}", mime_type="application/json")
async def projects_resource(ctx: Context, scope: str = "") -> str:
    return _json(_runtime(ctx).database.projects())


@mcp.resource("openmcp://projects/{project_id}/jobs", mime_type="application/json")
async def project_jobs_resource(project_id: str, ctx: Context) -> str:
    runtime = _runtime(ctx)
    if runtime.database.project(project_id) is None:
        raise ValueError(f"Unknown project: {project_id}")
    jobs = runtime.database.jobs(project_id)
    active = [job for job in jobs if job.state not in TERMINAL_STATES]
    terminal = [job for job in jobs if job.state in TERMINAL_STATES]
    recent = sorted(terminal, key=lambda job: job.updated_at, reverse=True)[:10]

    def summary(job: JobView) -> dict[str, Any]:
        return JobSummary(
            id=job.id,
            workflow=job.workflow,
            profile=job.profile,
            state=job.state,
            context_key=job.context_key,
            attempts=job.attempts,
            updated_at=job.updated_at,
        ).model_dump(mode="json")

    return _json({
        "active": [summary(job) for job in active],
        "recent": [summary(job) for job in recent],
        "truncated": len(terminal) - len(recent),
    })


@mcp.resource("openmcp://jobs/{job_id}", mime_type="application/json")
async def job_resource(job_id: str, ctx: Context) -> str:
    job = _runtime(ctx).database.job(job_id)
    if job is None:
        raise ValueError(f"Unknown job: {job_id}")
    return _json(job)


@mcp.resource("openmcp://projects/{project_id}/profiles", mime_type="application/json")
async def project_profiles_resource(project_id: str, ctx: Context) -> str:
    catalog = _runtime(ctx).catalog_for_project(project_id)
    return _json({"default": catalog.default_profile, "available": sorted(catalog.profiles)})


@mcp.resource("openmcp://workflows/{project_id}", mime_type="application/json")
async def workflows_resource(project_id: str, ctx: Context) -> str:
    if _runtime(ctx).database.project(project_id) is None:
        raise ValueError(f"Unknown project: {project_id}")
    return _json(BUILTIN_WORKFLOWS)


__all__ = ["create_application", "job_cancel", "job_retry", "job_submit", "job_wait", "mcp", "project_register", "publish_job_resource", "run", "status", "subscription_bus", "task_guide"]
