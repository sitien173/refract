"""The MCP application: the server instance, its lifespan and the Starlette app that mounts it."""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, AsyncIterator

from mcp.server import CacheHint, MCPServer
from starlette.applications import Starlette
from starlette.routing import Mount

from refract.api.http.common import DashboardState
from refract.api.http.routes import register_dashboard_routes
from refract.api.mcp.responses import _error_boundary
from refract.api.mcp.tools import tool_definitions
from refract.config import DaemonConfig, load_config, refract_home
from refract.logging_setup import configure as configure_logging, get_logger
from refract.runtime import Runtime
from refract.store.pool import run_sync

log = get_logger("server")

INSTRUCTIONS = """

Standard cycle: list(path) -> active and recent jobs, workflows, profiles, guidance; submit(path, workflow, prompt) -> job.id; wait(job_ids) -> result. Prompts are self-contained. wait blocks up to 3600 s and returns the first of 1 to 16 jobs that is ready. Read result; when truncated is true, read the full text at result_path. get(job_id) reads a job and its attempts without waiting.

Rules:
- A nonterminal wait and dropped connections are normal; wait again on the same job_ids.
- Use session to resume a worker session; fresh=true starts a new one. After failure_kind context_overflow, submit again with fresh=true.
- On session resume, call list(path) and reconcile active jobs before submitting.
- When wait returns pending_question, call answer(job_id, answer).
- cancel(job_id) returns cancel_status: terminated for queued work, requested for running work, already_terminal for finished work.
- To run a succeeded, failed, cancelled, or interrupted job again, call submit(path, from_job=job_id). The new job copies workflow, profile, session, and prompt, and uses next_target or the target after the last attempt. Add target=X to pin a target, or fresh=true for a new worker session. from_job excludes prompt, workflow, profile, and session.
- Record orchestrated work as cards: card_create(path, title) -> card; card_move(card_id, state, job_ids) moves it through todo, in_progress, in_review, done, cancelled and links jobs; card_list(path) -> cards.
- On targets_unavailable, wait retry_after_s seconds before submitting again. Follow each error next_action."""


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
        instructions=INSTRUCTIONS,
        version=package_version("refract"),
        lifespan=lifespan,
        middleware=[error_boundary],
        subscriptions=False,
        cache_hints={"tools/list": CacheHint(ttl_ms=300_000)},
    )
    for function, options in tool_definitions():
        instance.tool(**options)(function)
    return instance


def _write_daemon_file(path: Path, host: str, port: int) -> str:
    """Atomically publish a fresh private runtime token; return it, or "" when the file cannot be written."""
    token = secrets.token_hex(32)
    content = json.dumps({"token": token, "host": host, "port": port, "version": package_version("refract"), "pid": os.getpid()})
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
        session_idle_timeout=None,
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
