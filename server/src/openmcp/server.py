"""FastMCP daemon surface and direct-run compatibility facade."""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from functools import wraps
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Literal, ParamSpec, TypeVar, cast

from mcp.server.fastmcp import Context, FastMCP

from openmcp.backend_runner import run as _run_backend
from openmcp.backends.agy import execute as agy_execute
from openmcp.backends.codex import execute as codex_execute
from openmcp.backends.pi import execute as pi_execute
from openmcp.config import load_config, load_task_routes
from openmcp.logging_setup import (
    configure as configure_logging,
    get_logger,
    log_context,
)
from openmcp.models import (
    ActionResult,
    JobView,
    ProjectInitResult,
    ProjectView,
    SubmissionResult,
    TaskRouteResult,
)
from openmcp.runtime import Runtime

log = get_logger("server")

_DAEMON_CONFIG = load_config()
configure_logging(_DAEMON_CONFIG.logging)
_ACTIVE_RUNTIME: Runtime | None = None


@asynccontextmanager
async def _lifespan(_: FastMCP) -> AsyncIterator[Runtime]:
    global _ACTIVE_RUNTIME
    runtime = Runtime(_DAEMON_CONFIG)
    log.info(
        "Starting OpenMCP daemon",
        extra={
            "event": "daemon.starting",
            "host": _DAEMON_CONFIG.host,
            "port": _DAEMON_CONFIG.port,
            "max_jobs": _DAEMON_CONFIG.max_jobs,
        },
    )
    await runtime.start()
    _ACTIVE_RUNTIME = runtime
    log.info("OpenMCP daemon ready", extra={"event": "daemon.ready"})
    try:
        yield runtime
    finally:
        log.info("Stopping OpenMCP daemon", extra={"event": "daemon.stopping"})
        _ACTIVE_RUNTIME = None
        await runtime.close()
        log.info("OpenMCP daemon stopped", extra={"event": "daemon.stopped"})


mcp = FastMCP(
    "openmcp",
    host=_DAEMON_CONFIG.host,
    port=_DAEMON_CONFIG.port,
    streamable_http_path="/mcp",
    json_response=True,
    lifespan=_lifespan,
)


async def run(
    backend: Literal["agy", "codex", "pi"],
    PROMPT: str,
    cd: str,
    SESSION_ID: str = "",
    timeout_s: int = 0,
) -> dict[str, Any]:
    """Run one backend through the legacy direct-invocation compatibility API.

    New orchestration should use the durable MCP job tools. This facade keeps
    existing Python callers stable while delegating execution to
    :mod:`openmcp.backend_runner`.
    """
    return await _run_backend(
        backend,
        PROMPT,
        cd,
        SESSION_ID,
        timeout_s,
        agy_executor=agy_execute,
        codex_executor=codex_execute,
        pi_executor=pi_execute,
    )


def _runtime(ctx: Context) -> Runtime:
    return cast(Runtime, ctx.request_context.lifespan_context)


def _active_runtime() -> Runtime:
    if _ACTIVE_RUNTIME is None:
        raise RuntimeError("OpenMCP runtime is not active")
    return _ACTIVE_RUNTIME


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _logged_request(
    operation: str,
) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    """Log MCP tool boundaries without recording request payloads."""

    def decorate(
        function: Callable[_P, Awaitable[_R]],
    ) -> Callable[_P, Awaitable[_R]]:
        @wraps(function)
        async def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            context = next(
                (
                    value
                    for value in (*args, *kwargs.values())
                    if isinstance(value, Context)
                ),
                None,
            )
            request_id = context.request_id if context is not None else ""
            started_at = time.monotonic()
            with log_context(request_id=request_id):
                log.info(
                    "MCP tool request started",
                    extra={"event": "mcp.request_started", "operation": operation},
                )
                try:
                    result = await function(*args, **kwargs)
                except asyncio.CancelledError:
                    log.warning(
                        "MCP tool request cancelled",
                        extra={
                            "event": "mcp.request_finished",
                            "operation": operation,
                            "outcome": "cancelled",
                            "duration_ms": round(
                                (time.monotonic() - started_at) * 1000,
                                2,
                            ),
                        },
                    )
                    raise
                except Exception as exc:
                    log.warning(
                        "MCP tool request failed",
                        extra={
                            "event": "mcp.request_finished",
                            "operation": operation,
                            "outcome": "failed",
                            "error_type": type(exc).__name__,
                            "duration_ms": round(
                                (time.monotonic() - started_at) * 1000,
                                2,
                            ),
                        },
                    )
                    raise
                log.info(
                    "MCP tool request completed",
                    extra={
                        "event": "mcp.request_finished",
                        "operation": operation,
                        "outcome": "success",
                        "duration_ms": round(
                            (time.monotonic() - started_at) * 1000,
                            2,
                        ),
                    },
                )
                return result

        return wrapped

    return decorate


@mcp.tool(description="Register a clean Git project.", structured_output=True)
@_logged_request("project_register")
async def project_register(
    path: str,
    ctx: Context,
    alias: str = "",
) -> ProjectView:
    return _runtime(ctx).register_project(path, alias)


@mcp.tool(description="Initialize project-level OpenMCP files.", structured_output=True)
@_logged_request("project_init")
async def project_init(path: str, ctx: Context) -> ProjectInitResult:
    return _runtime(ctx).initialize_project(path)


@mcp.tool(
    description=(
        "Load task-route definitions. The coordinator breaks down the task "
        "and chooses agent names from the returned template."
    ),
    structured_output=True,
)
@_logged_request("task_route")
async def task_route(
    task: str,
    ctx: Context,
    project_id: str = "",
) -> TaskRouteResult:
    value = task.strip()
    if not value:
        raise ValueError("Task must contain text")
    runtime = _runtime(ctx)
    project_root = None
    resolved_project_id = project_id.strip()
    if resolved_project_id:
        project = runtime.database.project(resolved_project_id)
        if project is None:
            raise ValueError(f"Unknown project: {resolved_project_id}")
        project_root = Path(project.root)
    return TaskRouteResult(
        task=value,
        template=load_task_routes(runtime.config.home, project_root),
    )


@mcp.tool(description="Queue a durable project workflow.", structured_output=True)
@_logged_request("job_submit")
async def job_submit(
    project_id: str,
    workflow: str,
    inputs: dict[str, Any],
    ctx: Context,
    context_key: str = "",
    parent_job_id: str = "",
    routing_profile: str = "",
) -> SubmissionResult:
    return await _runtime(ctx).submit(
        project_id,
        workflow,
        inputs,
        context_key,
        parent_job_id,
        routing_profile,
    )


@mcp.tool(description="Wait for job completion or timeout.", structured_output=True)
@_logged_request("job_wait")
async def job_wait(
    job_id: str,
    ctx: Context,
    timeout_s: int = 0,
    include_stage_outputs: bool = False,
) -> JobView:
    runtime = _runtime(ctx)
    deadline = time.monotonic() + timeout_s if timeout_s > 0 else None
    while True:
        job = runtime.database.job(
            job_id,
            include_stage_outputs=include_stage_outputs,
        )
        if job is None:
            raise ValueError(f"Unknown job: {job_id}")
        completed = sum(
            stage.state
            in {"succeeded", "failed", "cancelled", "interrupted", "skipped"}
            for stage in job.stages
        )
        await ctx.report_progress(
            progress=float(completed),
            total=float(len(job.stages) or 1),
            message=job.state,
        )
        if job.state in {
            "succeeded",
            "failed",
            "cancelled",
            "interrupted",
            "integrated",
            "integration_conflict",
        }:
            return job
        if deadline is not None and time.monotonic() >= deadline:
            return job
        await asyncio.sleep(0.5)


@mcp.tool(description="Cancel a queued or running job.", structured_output=True)
@_logged_request("job_cancel")
async def job_cancel(job_id: str, ctx: Context) -> ActionResult:
    return _runtime(ctx).cancel(job_id)


@mcp.tool(description="Retry a failed or interrupted job.", structured_output=True)
@_logged_request("job_retry")
async def job_retry(
    job_id: str,
    ctx: Context,
    from_stage: str = "",
) -> SubmissionResult:
    return await _runtime(ctx).retry(job_id, from_stage)


@mcp.tool(description="Fast-forward a successful job into its project.", structured_output=True)
@_logged_request("job_integrate")
async def job_integrate(job_id: str, ctx: Context) -> ActionResult:
    return _runtime(ctx).integrate(job_id)


def _json(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    elif isinstance(value, list):
        value = [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in value
        ]
    return json.dumps(value, ensure_ascii=False, indent=2)


@mcp.resource("openmcp://projects", mime_type="application/json")
async def projects_resource() -> str:
    return _json(_active_runtime().database.projects())


@mcp.resource("openmcp://projects/{project_id}", mime_type="application/json")
async def project_resource(project_id: str, ctx: Context) -> str:
    project = _runtime(ctx).database.project(project_id)
    if project is None:
        raise ValueError(f"Unknown project: {project_id}")
    return _json(project)


@mcp.resource("openmcp://projects/{project_id}/jobs", mime_type="application/json")
async def project_jobs_resource(project_id: str, ctx: Context) -> str:
    if _runtime(ctx).database.project(project_id) is None:
        raise ValueError(f"Unknown project: {project_id}")
    return _json(
        _runtime(ctx).database.jobs(
            project_id,
            include_stage_outputs=False,
        )
    )


@mcp.resource("openmcp://jobs/{job_id}", mime_type="application/json")
async def job_resource(job_id: str, ctx: Context) -> str:
    job = _runtime(ctx).database.job(job_id, include_stage_outputs=True)
    if job is None:
        raise ValueError(f"Unknown job: {job_id}")
    return _json(job)


@mcp.resource("openmcp://jobs/{job_id}/events", mime_type="application/json")
async def job_events_resource(job_id: str, ctx: Context) -> str:
    if _runtime(ctx).database.job(job_id) is None:
        raise ValueError(f"Unknown job: {job_id}")
    return _json(_runtime(ctx).database.events(job_id))


@mcp.resource(
    "openmcp://contexts/{project_id}/{context_key}",
    mime_type="application/json",
)
async def context_resource(
    project_id: str,
    context_key: str,
    ctx: Context,
) -> str:
    return _json(_runtime(ctx).database.context(project_id, context_key))


@mcp.resource("openmcp://models", mime_type="application/json")
async def models_resource() -> str:
    return _json(_active_runtime().targets())


@mcp.resource("openmcp://routing-profiles", mime_type="application/json")
async def routing_profiles_resource() -> str:
    runtime = _active_runtime()
    return _json(
        {
            "default": runtime.catalog.default_routing_profile,
            "available": sorted(runtime.catalog.routing_profiles),
        }
    )


@mcp.resource(
    "openmcp://projects/{project_id}/routing-profiles",
    mime_type="application/json",
)
async def project_routing_profiles_resource(project_id: str, ctx: Context) -> str:
    catalog = _runtime(ctx).catalog_for_project(project_id)
    return _json(
        {
            "default": catalog.default_routing_profile,
            "available": sorted(catalog.routing_profiles),
        }
    )


@mcp.resource("openmcp://workflows/{project_id}", mime_type="application/json")
async def workflows_resource(project_id: str, ctx: Context) -> str:
    project = _runtime(ctx).database.project(project_id)
    if project is None:
        raise ValueError(f"Unknown project: {project_id}")
    path = Path(project.root) / ".openmcp" / "workflows"
    names = ["read", "write"]
    if path.exists():
        names.extend(file.stem for file in sorted(path.glob("*.yaml")))
    return _json(sorted(set(names)))


__all__ = [
    "job_cancel",
    "job_integrate",
    "job_retry",
    "job_submit",
    "job_wait",
    "mcp",
    "project_init",
    "project_register",
    "run",
    "task_route",
]
