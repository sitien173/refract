"""In-process read-only web dashboard endpoints and static assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

_STATIC_DIR = Path(__file__).parent / "dashboard_static"


def _profile_config_data(config: Any) -> dict[str, dict[str, Any]]:
    if config.profile_declarations:
        return {
            profile_id: {
                **({"extends": declaration.extends} if declaration.extends else {}),
                **{
                    workflow: {
                        "targets": list(selection.targets),
                        "max_attempts": selection.max_attempts,
                        "timeout_s": selection.timeout_s,
                    }
                    for workflow, selection in declaration.workflows.items()
                },
            }
            for profile_id, declaration in config.profile_declarations.items()
        }
    return {
        profile_id: {
            workflow: {
                "targets": list(selection.targets),
                "max_attempts": selection.max_attempts,
                "timeout_s": selection.timeout_s,
            }
            for workflow, selection in profile_map.items()
        }
        for profile_id, profile_map in config.profiles.items()
    }


def register_dashboard_routes(mcp_server: FastMCP) -> None:
    from openmcp.server import _active_runtime, _json

    def _json_response(data: Any, status_code: int = 200) -> Response:
        return Response(content=_json(data), status_code=status_code, media_type="application/json")
    @mcp_server.custom_route("/dashboard/api/status", methods=["GET"])
    async def api_status(request: Request) -> Response:
        try:
            runtime = _active_runtime()
        except RuntimeError:
            return JSONResponse({"error": "OpenMCP runtime is not active"}, status_code=503)
        return _json_response(runtime.status())

    @mcp_server.custom_route("/dashboard/api/projects", methods=["GET"])
    async def api_projects(request: Request) -> Response:
        try:
            runtime = _active_runtime()
        except RuntimeError:
            return JSONResponse({"error": "OpenMCP runtime is not active"}, status_code=503)
        return _json_response(runtime.database.projects())

    @mcp_server.custom_route("/dashboard/api/projects/{id}/jobs", methods=["GET"])
    async def api_project_jobs(request: Request) -> Response:
        try:
            runtime = _active_runtime()
        except RuntimeError:
            return JSONResponse({"error": "OpenMCP runtime is not active"}, status_code=503)
        project_id = request.path_params["id"]
        if runtime.database.project(project_id) is None:
            return JSONResponse({"error": f"Unknown project: {project_id}"}, status_code=404)
        return _json_response(runtime.database.jobs(project_id))

    @mcp_server.custom_route("/dashboard/api/jobs/{id}", methods=["GET"])
    async def api_job(request: Request) -> Response:
        try:
            runtime = _active_runtime()
        except RuntimeError:
            return JSONResponse({"error": "OpenMCP runtime is not active"}, status_code=503)
        job_id = request.path_params["id"]
        job = runtime.database.job(job_id)
        if job is None:
            return JSONResponse({"error": f"Unknown job: {job_id}"}, status_code=404)
        return _json_response(job)

    @mcp_server.custom_route("/dashboard/api/jobs/{id}/events", methods=["GET"])
    async def api_job_events(request: Request) -> Response:
        try:
            runtime = _active_runtime()
        except RuntimeError:
            return JSONResponse({"error": "OpenMCP runtime is not active"}, status_code=503)
        job_id = request.path_params["id"]
        if runtime.database.job(job_id) is None:
            return JSONResponse({"error": f"Unknown job: {job_id}"}, status_code=404)
        return _json_response(runtime.database.events(job_id))

    @mcp_server.custom_route("/dashboard/api/targets", methods=["GET"])
    async def api_targets(request: Request) -> Response:
        try:
            runtime = _active_runtime()
        except RuntimeError:
            return JSONResponse({"error": "OpenMCP runtime is not active"}, status_code=503)
        return _json_response(runtime.targets())

    @mcp_server.custom_route("/dashboard/api/profiles", methods=["GET"])
    async def api_profiles(request: Request) -> Response:
        try:
            runtime = _active_runtime()
        except RuntimeError:
            return JSONResponse({"error": "OpenMCP runtime is not active"}, status_code=503)
        return _json_response({"default": runtime.catalog.default_profile, "available": sorted(runtime.catalog.profiles)})

    @mcp_server.custom_route("/dashboard/api/config", methods=["GET"])
    async def api_get_config(request: Request) -> Response:
        try:
            runtime = _active_runtime()
        except RuntimeError:
            return JSONResponse({"error": "OpenMCP runtime is not active"}, status_code=503)
        cfg = runtime.catalog
        data = {
            "daemon": {
                "host": cfg.host,
                "port": cfg.port,
                "max_jobs": cfg.max_jobs,
                "history_turns": cfg.history_turns,
                "history_bytes": cfg.history_bytes,
                "default_profile": cfg.default_profile,
            },
            "logging": {
                "level": cfg.logging.level,
                "format": cfg.logging.format,
                "file": str(cfg.logging.file) if cfg.logging.file is not None else False,
                "console": cfg.logging.console,
                "max_bytes": cfg.logging.max_bytes,
                "backup_count": cfg.logging.backup_count,
                "capture_warnings": cfg.logging.capture_warnings,
            },
            "targets": [
                {
                    "id": t.id,
                    "backend": t.backend,
                    "model": t.model,
                    "backend_profile": t.backend_profile,
                    "reasoning": t.reasoning,
                    "system_prompt": t.system_prompt,
                    "isolated": t.isolated,
                    "read_only": t.read_only,
                    "args": list(t.args),
                    "capabilities": [],
                    "max_concurrency": t.max_concurrency,
                }
                for t in cfg.targets
            ],
            "profiles": _profile_config_data(cfg),
        }
        return _json_response(data)

    @mcp_server.custom_route("/dashboard/api/config", methods=["PUT"])
    async def api_put_config(request: Request) -> Response:
        from openmcp.config_writer import write_config
        try:
            runtime = _active_runtime()
        except RuntimeError:
            return JSONResponse({"error": "OpenMCP runtime is not active"}, status_code=503)
        try:
            payload = await request.json()
        except Exception as exc:
            return JSONResponse({"error": f"Invalid JSON body: {exc}"}, status_code=400)

        try:
            write_config(payload, path=runtime.config.config_path)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse({"error": f"Invalid config payload: {exc}"}, status_code=400)

        reload_res = runtime.reload()
        return _json_response({
            "success": reload_res.success,
            "targets": reload_res.targets,
            "profiles": reload_res.profiles,
            "restart_required": reload_res.restart_required,
        })

    @mcp_server.custom_route("/dashboard/api/task-guide", methods=["GET"])
    async def api_get_task_guide(request: Request) -> Response:
        from openmcp.config import load_task_guide
        try:
            runtime = _active_runtime()
        except RuntimeError:
            return JSONResponse({"error": "OpenMCP runtime is not active"}, status_code=503)
        try:
            project_id = request.query_params.get("project_id")
            if project_id:
                project = runtime.database.project(project_id)
                if project is None:
                    return JSONResponse({"error": f"Unknown project: {project_id}"}, status_code=404)
                guide = load_task_guide(runtime.config.home, Path(project.root))
            else:
                guide = load_task_guide(runtime.config.home)
        except ValueError as exc:
            msg = str(exc)
            if msg.startswith("Missing task guide"):
                guide = {}
            else:
                return JSONResponse({"error": str(exc)}, status_code=422)
        return _json_response(guide)

    @mcp_server.custom_route("/dashboard/api/task-guide", methods=["PUT"])
    async def api_put_task_guide(request: Request) -> Response:
        from openmcp.config_writer import write_task_guide
        try:
            runtime = _active_runtime()
        except RuntimeError:
            return JSONResponse({"error": "OpenMCP runtime is not active"}, status_code=503)
        try:
            payload = await request.json()
        except Exception as exc:
            return JSONResponse({"error": f"Invalid JSON body: {exc}"}, status_code=400)

        if not isinstance(payload, dict):
            return JSONResponse({"error": "Task guide must be a non-empty JSON object"}, status_code=400)

        try:
            project_id = request.query_params.get("project_id")
            if project_id:
                project = runtime.database.project(project_id)
                if project is None:
                    return JSONResponse({"error": f"Unknown project: {project_id}"}, status_code=404)
                proj_path = Path(project.root) / ".openmcp"
                written_guide = write_task_guide(payload, path=proj_path / "task_guide.json")
            else:
                written_guide = write_task_guide(payload, home=runtime.config.home)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception as exc:
            return JSONResponse({"error": f"Invalid task-guide payload: {exc}"}, status_code=400)

        return _json_response(written_guide)

    @mcp_server.custom_route("/dashboard", methods=["GET"])

    async def dashboard_index(request: Request) -> Response:
        index_file = _STATIC_DIR / "index.html"
        if not index_file.is_file():
            return JSONResponse({"error": "Dashboard index HTML not found"}, status_code=404)
        return FileResponse(index_file, media_type="text/html")

    @mcp_server.custom_route("/dashboard/", methods=["GET"])
    async def dashboard_index_slash(request: Request) -> Response:
        return await dashboard_index(request)

    mcp_server._custom_starlette_routes.append(
        Mount("/dashboard/assets", app=StaticFiles(directory=_STATIC_DIR), name="dashboard_assets")
    )
