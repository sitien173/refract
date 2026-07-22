"""In-process read-only web dashboard endpoints and static assets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

_STATIC_DIR = Path(__file__).parent / "dashboard_static"


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
