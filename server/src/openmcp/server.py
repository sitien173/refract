"""Unified FastMCP server surface for agy, codex, and Pi backends."""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Literal, cast

from mcp.server.fastmcp import Context, FastMCP

from openmcp.backends.agy import AgyParams, execute as agy_execute
from openmcp.backends.codex import CodexParams, execute as codex_execute
from openmcp.backends.pi import PiParams, execute as pi_execute
from openmcp.logging_setup import configure as configure_logging, get_logger
from openmcp.config import load_config, load_task_routes
from openmcp.models import (
    ActionResult,
    JobView,
    ProjectInitResult,
    ProjectView,
    SubmissionResult,
    TaskRouteResult,
)
from openmcp.notify import emit_error, emit_finish, emit_start
from openmcp.runtime import Runtime

configure_logging()
log = get_logger("server")

_DAEMON_CONFIG = load_config()
_ACTIVE_RUNTIME: Runtime | None = None


@asynccontextmanager
async def _lifespan(_: FastMCP) -> AsyncIterator[Runtime]:
    global _ACTIVE_RUNTIME
    runtime = Runtime(_DAEMON_CONFIG)
    await runtime.start()
    _ACTIVE_RUNTIME = runtime
    try:
        yield runtime
    finally:
        _ACTIVE_RUNTIME = None
        await runtime.close()


mcp = FastMCP(
    "openmcp",
    host=_DAEMON_CONFIG.host,
    port=_DAEMON_CONFIG.port,
    streamable_http_path="/mcp",
    json_response=True,
    lifespan=_lifespan,
)

_ENV_CODEX_MODEL_DEFAULT = "OPENMCP_CODEX_MODEL_DEFAULT"
_ENV_CODEX_PROFILE_DEFAULT = "OPENMCP_CODEX_PROFILE_DEFAULT"
_ENV_AGY_REASONING_MODEL = "OPENMCP_AGY_REASONING_MODEL"
_ENV_CODEX_REASONING_MODEL = "OPENMCP_CODEX_REASONING_MODEL"
_ENV_PI_MODEL_DEFAULT = "OPENMCP_PI_MODEL_DEFAULT"

_REASONING_MODEL_DEFAULTS: Dict[str, str] = {
    "agy": "gemini-3.5-flash",
    "codex": "gpt-5.5",
}
_REASONING_MODEL_ENV: Dict[str, str] = {
    "agy": _ENV_AGY_REASONING_MODEL,
    "codex": _ENV_CODEX_REASONING_MODEL,
}
_PLUGIN_CONFIG_FILES = ("mcp_config.json", ".mcp.json", "mcp.json")


def _openmcp_env_file() -> Path:
    return Path.home() / ".openmcp" / ".env"


def _load_plugin_env() -> Dict[str, str]:
    plugin_env: Dict[str, str] = {}
    for config_name in _PLUGIN_CONFIG_FILES:
        config_path = Path.cwd() / config_name
        if not config_path.exists():
            continue
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Failed to read plugin config %s: %s", config_path.as_posix(), exc)
            continue
        server_env = (
            config.get("mcpServers", {})
            .get("openmcp", {})
            .get("env", {})
        )
        if not isinstance(server_env, dict):
            continue
        for key, value in server_env.items():
            if value is None:
                continue
            plugin_env[str(key)] = str(value)
    return plugin_env


def _load_openmcp_dotenv() -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        lines = _openmcp_env_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _effective_env() -> Dict[str, str]:
    # Precedence: process env > ~/.openmcp/.env > plugin config env.
    env = _load_plugin_env()
    env.update(_load_openmcp_dotenv())
    env.update(os.environ)
    return env


def _env_truthy(name: str, env: Dict[str, str]) -> bool:
    return env.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _reasoning_model(backend: str, env: Dict[str, str]) -> str:
    return env.get(_REASONING_MODEL_ENV[backend], "") or _REASONING_MODEL_DEFAULTS[backend]


def _resolve_model(
    backend: Literal["agy", "codex", "pi"],
    model: str,
    reasoning: str,
    env: Dict[str, str],
) -> str:
    if model:
        return model
    if reasoning:
        if backend == "agy":
            base = _reasoning_model("agy", env)
            # bare model id (no suffix) corresponds to Medium; preserve that
            return base if reasoning == "medium" else f"{base}-{reasoning}"
        if backend == "codex":
            return _reasoning_model("codex", env)
        return env.get(_ENV_PI_MODEL_DEFAULT, "")
    if backend == "agy":
        return ""
    if backend == "pi":
        return env.get(_ENV_PI_MODEL_DEFAULT, "")
    return env.get(_ENV_CODEX_MODEL_DEFAULT, "")


def _resolve_profile(profile: str, env: Dict[str, str]) -> str:
    if profile:
        return profile
    return env.get(_ENV_CODEX_PROFILE_DEFAULT, "mcp_execution")


def _validate_cd(cd: Any) -> Path | None:
    if cd is None:
        return None
    if isinstance(cd, Path):
        return cd if str(cd) else None
    cd_str = str(cd).strip()
    if not cd_str:
        return None
    path = Path(cd_str)
    if not path.is_absolute():
        log.warning(
            "run(): cd=%r is not absolute; resolving against current working directory. "
            "Pass an absolute path to avoid this.", cd_str,
        )
    return path


async def run(
    backend: Literal["agy", "codex", "pi"],
    PROMPT: str,
    cd: str,
    SESSION_ID: str = "",
    model: str = "",
    profile: str = "",
    reasoning: Literal["", "low", "medium", "high"] = "",
    timeout_s: int = 0,
) -> Dict[str, Any]:
    """
    Run a backend agent.

    Args:
        backend: Backend to run.
        PROMPT: Prompt to execute.
        cd: Working directory for execution (must be an absolute path).
        SESSION_ID: Session ID to reuse. Leave empty to start a new session.
        model: Model to use. Leave empty to use the backend default.
        profile: Codex profile to use. When combined with model, the model
            argument overrides the profile's model field. Ignored by Pi.
        reasoning: Reasoning effort. Pi maps this to its --thinking level.
        timeout_s: Overall subprocess timeout in seconds (0 = no timeout / backend default).
    """

    cd_path = _validate_cd(cd)
    if cd_path is None:
        return {
            "success": False,
            "SESSION_ID": SESSION_ID or "",
            "agent_messages": "",
            "error": f"cd must be a non-empty absolute path; got {cd!r}",
        }
    effective_env = _effective_env()
    resolved_model = _resolve_model(backend, model, reasoning, effective_env)
    resolved_profile = "" if reasoning else _resolve_profile(profile, effective_env)
    if backend != "codex":
        resolved_profile = ""
    codex_model = resolved_model
    if backend == "codex" and profile and model:
        log.info(
            "codex: profile=%r and model=%r both provided; model overrides the profile's model",
            profile, model,
        )
    if backend == "codex" and profile and reasoning:
        log.warning(
            "codex: profile=%r and reasoning=%r both provided; profile is ignored "
            "(reasoning takes precedence and selects its own model)",
            profile, reasoning,
        )
    log.info(
        "run() backend=%s session_id=%s model=%s profile=%s reasoning=%s timeout_s=%s",
        backend, SESSION_ID or "<new>",
        codex_model if backend == "codex" else resolved_model,
        resolved_profile, reasoning or "<off>", timeout_s or "<off>",
    )
    try:
        await emit_start(
            backend=backend,
            session_id=SESSION_ID,
            model=resolved_model,
        )
        if backend == "agy":
            params = AgyParams(
                PROMPT=PROMPT,
                cd=cd_path,
                SESSION_ID=SESSION_ID,
                model=resolved_model,
                timeout_s=timeout_s,
            )
            backend_result = await agy_execute(params)
        elif backend == "codex":
            params = CodexParams(
                PROMPT=PROMPT,
                cd=cd_path,
                SESSION_ID=SESSION_ID,
                model=codex_model,
                profile=resolved_profile,
                reasoning_effort=reasoning,
                timeout_s=timeout_s,
            )
            backend_result = await codex_execute(params)
        else:
            params = PiParams(
                PROMPT=PROMPT,
                cd=cd_path,
                SESSION_ID=SESSION_ID,
                model=resolved_model,
                reasoning_effort=reasoning,
                timeout_s=timeout_s,
            )
            backend_result = await pi_execute(params)

        if backend_result.outcome == "OK":
            result = {
                "success": True,
                "SESSION_ID": backend_result.SESSION_ID,
                "agent_messages": backend_result.agent_messages,
            }
            if backend_result.error_class == "warning" and backend_result.error:
                result["warning"] = backend_result.error
        else:
            result = {
                "success": False,
                "SESSION_ID": backend_result.SESSION_ID or "",
                "agent_messages": backend_result.agent_messages or "",
                "error": backend_result.error,
            }
    except asyncio.CancelledError:
        log.warning(
            "run(): CANCELLED by MCP host (notifications/cancelled or transport closed) "
            "backend=%s session_id=%s",
            backend, SESSION_ID or "<new>",
        )
        raise
    except Exception as exc:
        log.exception("run(): unhandled exception in %s backend", backend)
        await emit_error(
            backend=backend,
            session_id=SESSION_ID,
            model=resolved_model,
            error=f"unhandled: {exc}",
        )
        return {"success": False, "SESSION_ID": SESSION_ID or "", "agent_messages": "", "error": f"unhandled: {exc}"}

    log.info(
        "run() done backend=%s success=%s session_id=%s",
        backend, result.get("success"), result.get("SESSION_ID", ""),
    )
    result_session_id = result.get("SESSION_ID", "") or ""
    if result.get("success", False):
        await emit_finish(
            backend=backend,
            session_id=result_session_id,
            model=resolved_model,
        )
    else:
        await emit_error(
            backend=backend,
            session_id=result_session_id,
            model=resolved_model,
            error=result.get("error", "") or "",
        )
    return {
        "success": result.get("success", False),
        "SESSION_ID": result_session_id,
        "agent_messages": result.get("agent_messages", "") or "",
        "error": result.get("error", "") or "",
    }


def _runtime(ctx: Context) -> Runtime:
    return cast(Runtime, ctx.request_context.lifespan_context)


def _active_runtime() -> Runtime:
    if _ACTIVE_RUNTIME is None:
        raise RuntimeError("OpenMCP runtime is not active")
    return _ACTIVE_RUNTIME


@mcp.tool(description="Register a clean Git project.", structured_output=True)
async def project_register(
    path: str,
    ctx: Context,
    alias: str = "",
) -> ProjectView:
    return _runtime(ctx).register_project(path, alias)


@mcp.tool(description="Initialize project-level OpenMCP files.", structured_output=True)
async def project_init(path: str, ctx: Context) -> ProjectInitResult:
    return _runtime(ctx).initialize_project(path)


@mcp.tool(
    description=(
        "Load task-route definitions. The coordinator breaks down the task "
        "and chooses agent names from the returned template."
    ),
    structured_output=True,
)
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
async def job_cancel(job_id: str, ctx: Context) -> ActionResult:
    return _runtime(ctx).cancel(job_id)


@mcp.tool(description="Retry a failed or interrupted job.", structured_output=True)
async def job_retry(
    job_id: str,
    ctx: Context,
    from_stage: str = "",
) -> SubmissionResult:
    return await _runtime(ctx).retry(job_id, from_stage)


@mcp.tool(description="Fast-forward a successful job into its project.", structured_output=True)
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
