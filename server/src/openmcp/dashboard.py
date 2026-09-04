"""Safe, in-process dashboard HTTP endpoints."""

from __future__ import annotations

import ipaddress
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from pydantic import ValidationError

from openmcp.config import DaemonConfig, ProfileDeclaration, TargetSelection, load_task_guide
from openmcp.config_inspection import sanitize_config_error
from openmcp.config_mutation import ConfigurationMutationError
from openmcp.models import (
    DashboardBootstrap,
    DashboardContextInstruction,
    DashboardError,
    DashboardJob,
    DashboardOverview,
    TargetDeleteResponse,
    TargetEditorData,
    TargetListResponse,
    TargetResponse,
)
from openmcp.planning import parse_execution_plan


_STATIC_DIR = Path(__file__).parent / "dashboard_static"


@dataclass
class DashboardState:
    """Process-owned state shared by the dashboard routes and MCP lifespan."""

    runtime: Any = None
    csrf_token: str = ""


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _json_response(value: Any, status_code: int = 200) -> Response:
    return JSONResponse(_jsonable(value), status_code=status_code)


def _error(
    message: str,
    status_code: int,
    *,
    code: str = "",
    unchanged: str = "",
    recovery: str = "",
    source_path: str = "",
    current: str | None = None,
    references: list[dict[str, Any]] | None = None,
) -> Response:
    return _json_response(
        DashboardError(
            error=message,
            code=code,
            unchanged=unchanged,
            recovery=recovery,
            source_path=source_path,
            current=current,
            references=references,
        ),
        status_code,
    )


def _runtime(state: DashboardState) -> Any:
    if state.runtime is None:
        raise RuntimeError("OpenMCP runtime is not active")
    return state.runtime


def _runtime_error() -> Response:
    return _error(
        "OpenMCP runtime is not active",
        503,
        code="runtime_unavailable",
        unchanged="No dashboard data was changed.",
        recovery="Retry after the daemon has started.",
    )


def _selection_data(selection: TargetSelection) -> dict[str, Any]:
    return {
        "targets": list(selection.targets),
        "max_attempts": selection.max_attempts,
        "timeout_s": selection.timeout_s,
    }


def _declaration_data(declaration: ProfileDeclaration | None) -> dict[str, Any] | None:
    if declaration is None:
        return None
    return {
        "extends": declaration.extends,
        "workflows": {
            workflow: _selection_data(selection)
            for workflow, selection in sorted(declaration.workflows.items())
        },
    }


def _profile_config_data(global_catalog: DaemonConfig, project_catalog: DaemonConfig) -> dict[str, Any]:
    global_declarations = global_catalog.profile_declarations
    merged_declarations = project_catalog.profile_declarations
    project_declarations = project_catalog.project_profile_declarations
    profile_ids = sorted(
        set(global_catalog.profiles)
        | set(project_catalog.profiles)
        | set(global_declarations)
        | set(merged_declarations)
    )
    profiles: list[dict[str, Any]] = []
    for profile_id in profile_ids:
        global_declaration = global_declarations.get(profile_id)
        merged_declaration = merged_declarations.get(profile_id)
        project_declaration = project_declarations.get(profile_id)
        global_workflows = (
            set(global_declaration.workflows) if global_declaration else set()
        )
        project_workflows = (
            set(project_declaration.workflows) if project_declaration else set()
        )
        effective = project_catalog.profiles.get(profile_id, {})
        declared = {
            **(
                {
                    workflow: {
                        "selection": _selection_data(selection),
                        "source": "global",
                    }
                    for workflow, selection in global_declaration.workflows.items()
                }
                if global_declaration
                else {}
            ),
            **(
                {
                    workflow: {
                        "selection": _selection_data(selection),
                        "source": "project",
                    }
                    for workflow, selection in project_declaration.workflows.items()
                }
                if project_declaration
                else {}
            ),
        }
        inherited = {
            workflow: _selection_data(selection)
            for workflow, selection in effective.items()
            if workflow not in project_workflows
            and (project_declaration is not None or workflow not in global_workflows)
        }
        def workflow_source(
            current_profile: str,
            workflow: str,
            seen: set[str] | None = None,
        ) -> str:
            seen = set() if seen is None else seen
            if current_profile in seen:
                return "global"
            seen.add(current_profile)
            current_project = project_declarations.get(current_profile)
            current_global = global_declarations.get(current_profile)
            if current_project and workflow in current_project.workflows:
                return "project"
            if current_global and workflow in current_global.workflows:
                return "global"
            parent = (
                current_project.extends
                if current_project and current_project.extends
                else current_global.extends
                if current_global
                else None
            )
            return (
                workflow_source(parent, workflow, seen)
                if parent
                else "global"
            )

        sources = {
            workflow: workflow_source(profile_id, workflow)
            for workflow in effective
        }
        profiles.append(
            {
                "id": profile_id,
                "parent": {
                    "value": (
                        project_declaration.extends
                        if project_declaration is not None
                        else global_declaration.extends
                        if global_declaration
                        else None
                    ),
                    "source": "project" if project_declaration else "global",
                },
                "declared": declared,
                "inherited": inherited,
                "effective": {
                    workflow: _selection_data(selection)
                    for workflow, selection in sorted(effective.items())
                },
                "sources": sources,
            }
        )
    return {
        "global_default_profile": global_catalog.default_profile,
        "project_default_profile": project_catalog.default_profile,
        "profiles": profiles,
    }


def _safe_execution_plan(raw: Any) -> dict[str, Any]:
    """Allow-list the plan fields useful to operators; omit all other fields."""
    try:
        plan = parse_execution_plan(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return {
        "profile": plan.profile,
        "workflow": plan.workflow,
        "selection": _selection_data(plan.selection),
        "targets": [
            {
                "id": target.id,
                "backend": target.backend,
                "model": target.model,
                "isolated": target.isolated,
                "read_only": target.read_only,
                "max_concurrency": target.max_concurrency,
            }
            for target in plan.targets
        ],
    }


def _dashboard_job(runtime: Any, job_id: str) -> DashboardJob | None:
    job = runtime.database.job(job_id)
    if job is None:
        return None
    record = runtime.database.job_record(job_id) or {}
    try:
        raw_plan = json.loads(record.get("execution_plan_json", ""))
    except (TypeError, json.JSONDecodeError):
        raw_plan = None
    return DashboardJob(
        id=job.id,
        project_id=job.project_id,
        workflow=job.workflow,
        profile=job.profile,
        state=job.state,
        context_key=job.context_key,
        config_revision=job.config_revision,
        target_id=job.target_id,
        attempts=job.attempts,
        created_at=job.created_at,
        updated_at=job.updated_at,
        result=job.result,
        execution_plan=_safe_execution_plan(raw_plan),
    )


def _source_path(runtime: Any, project_id: str) -> Path:
    project = runtime.database.project(project_id)
    if project is not None:
        root = Path(project.root) / ".openmcp"
        for name in ("task_guide.json", "task_routes.json"):
            if (root / name).exists():
                return root / name
    home = runtime.config.home
    for name in ("task_guide.json", "task_routes.json"):
        if (home / name).exists():
            return home / name
    return home / "task_guide.json"


def _host_name(request: Request) -> str:
    return request.headers.get("host", "")


def _is_loopback_host(value: str) -> bool:
    try:
        hostname = urlsplit(f"//{value}").hostname
        if hostname is None:
            return False
        if hostname.lower() == "localhost":
            return True
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _is_loopback_client(request: Request) -> bool:
    try:
        return request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        return False


def _origin_matches_host(request: Request) -> bool:
    origin = request.headers.get("origin", "")
    host = _host_name(request)
    if not origin or not host:
        return False
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    return (
        parsed.scheme == request.url.scheme
        and parsed.netloc.lower() == host.lower()
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


def _forbidden(
    unchanged: str = "No configuration was changed.",
    recovery: str = "Use a loopback browser with a matching same-origin CSRF token.",
) -> Response:
    return _error(
        "Forbidden",
        403,
        code="forbidden",
        unchanged=unchanged,
        recovery=recovery,
    )


def _authorized_editor_read(request: Request) -> bool:
    return _is_loopback_client(request) and _is_loopback_host(_host_name(request))


def _parse_if_match(request: Request) -> str | None:
    raw = request.headers.get("if-match", "").strip()
    if not raw:
        return None
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1]
    return raw


def _handle_mutation_error(exc: ConfigurationMutationError) -> Response:
    status_code = 422
    if exc.code == "revision_required":
        status_code = 428
    elif exc.code == "not_found":
        status_code = 404
    elif exc.code in {"configuration_conflict", "referenced"}:
        status_code = 409
    elif exc.code == "configuration_commit_failed":
        status_code = 500
    return _error(
        sanitize_config_error(str(exc)),
        status_code,
        code=exc.code,
        unchanged=exc.unchanged,
        recovery=exc.recovery,
        source_path=exc.source_path,
        current=exc.current_revision or None,
        references=exc.references,
    )


def _authorized_mutation(request: Request, state: DashboardState) -> bool:
    if not _is_loopback_client(request) or not _is_loopback_host(_host_name(request)):
        return False
    if not _origin_matches_host(request):
        return False
    provided = request.headers.get("x-openmcp-csrf", "")
    return bool(state.csrf_token) and secrets.compare_digest(
        provided, state.csrf_token
    )


def register_dashboard_routes(state: DashboardState) -> list[Route]:
    async def bootstrap(request: Request) -> Response:
        if not _is_loopback_client(request) or not _is_loopback_host(_host_name(request)):
            return _forbidden()
        try:
            _runtime(state)
        except RuntimeError:
            return _runtime_error()
        response = _json_response(DashboardBootstrap(csrf_token=state.csrf_token))
        response.headers["cache-control"] = "no-store"
        return response

    async def status(request: Request) -> Response:
        try:
            return _json_response(_runtime(state).status())
        except RuntimeError:
            return _runtime_error()

    async def overview(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            daemon = runtime.status()
            configuration = runtime.configuration_health()
            targets = runtime.targets()
            return _json_response(
                DashboardOverview(
                    daemon=daemon,
                    configuration=configuration,
                    projects=len(runtime.database.projects()),
                    unhealthy_targets=sum(not target.healthy for target in targets),
                )
            )
        except RuntimeError:
            return _runtime_error()

    async def configuration(request: Request) -> Response:
        try:
            return _json_response(_runtime(state).configuration_health())
        except RuntimeError:
            return _runtime_error()

    async def settings(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            cfg = runtime.catalog
            logging = cfg.logging
            return _json_response(
                {
                    "source_path": cfg.config_path.as_posix() if cfg.config_path else "",
                    "revision": cfg.config_revision,
                    "daemon": {
                        "host": cfg.host,
                        "port": cfg.port,
                        "max_jobs": cfg.max_jobs,
                        "history_turns": cfg.history_turns,
                        "history_bytes": cfg.history_bytes,
                        "default_profile": cfg.default_profile,
                    },
                    "logging": {
                        "level": logging.level,
                        "format": logging.format,
                        "file": logging.file.as_posix() if logging.file else False,
                        "console": logging.console,
                        "max_bytes": logging.max_bytes,
                        "backup_count": logging.backup_count,
                        "capture_warnings": logging.capture_warnings,
                    },
                }
            )
        except RuntimeError:
            return _runtime_error()

    async def config_targets_get(request: Request) -> Response:
        if not _authorized_editor_read(request):
            return _forbidden()
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        try:
            source_read, targets_data = runtime.mutations.read_targets()
            response = _json_response(
                TargetListResponse(
                    revision=source_read.revision,
                    source_path=source_read.path.as_posix(),
                    targets=targets_data,
                )
            )
            response.headers["cache-control"] = "no-store"
            response.headers["etag"] = f'"{source_read.revision}"'
            return response
        except ConfigurationMutationError as exc:
            return _handle_mutation_error(exc)

    async def config_target_get(request: Request) -> Response:
        if not _authorized_editor_read(request):
            return _forbidden()
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        target_id = request.path_params["target_id"]
        try:
            source_read, target_data = runtime.mutations.get_target(target_id)
            response = _json_response(
                TargetResponse(
                    revision=source_read.revision,
                    source_path=source_read.path.as_posix(),
                    target=target_data,
                )
            )
            response.headers["cache-control"] = "no-store"
            response.headers["etag"] = f'"{source_read.revision}"'
            return response
        except ConfigurationMutationError as exc:
            return _handle_mutation_error(exc)

    async def config_target_create(request: Request) -> Response:
        if not _authorized_mutation(request, state):
            return _forbidden()
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        source_path = (
            runtime.config.config_path.as_posix() if runtime.config.config_path else ""
        )
        expected_revision = _parse_if_match(request)
        if expected_revision is None:
            return _error(
                "An expected source revision is required before any file change.",
                428,
                code="revision_required",
                unchanged="No configuration file was changed.",
                recovery="Reload the current configuration and retry the edit.",
                source_path=source_path,
            )
        try:
            payload = await request.json()
        except Exception:
            return _error(
                "Invalid JSON body",
                422,
                code="configuration_invalid",
                unchanged="No configuration file was changed.",
                recovery="Provide a valid JSON request body and retry.",
                source_path=source_path,
            )
        if not isinstance(payload, dict):
            return _error(
                "Request body must be a JSON object",
                422,
                code="configuration_invalid",
                unchanged="No configuration file was changed.",
                recovery="Provide a JSON object payload and retry.",
                source_path=source_path,
            )
        try:
            data = TargetEditorData.model_validate(payload)
        except (ValidationError, ValueError) as exc:
            return _error(
                sanitize_config_error(exc),
                422,
                code="configuration_invalid",
                unchanged="No configuration file was changed.",
                recovery="Correct the target fields and retry.",
                source_path=source_path,
            )
        try:
            result, created = runtime.mutations.create_target(
                data, expected_revision=expected_revision
            )
            response = _json_response(
                TargetResponse(
                    revision=result.revision,
                    source_path=result.source_path.as_posix(),
                    target=created,
                )
            )
            response.headers["cache-control"] = "no-store"
            response.headers["etag"] = f'"{result.revision}"'
            return response
        except ConfigurationMutationError as exc:
            return _handle_mutation_error(exc)

    async def config_target_update(request: Request) -> Response:
        if not _authorized_mutation(request, state):
            return _forbidden()
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        source_path = (
            runtime.config.config_path.as_posix() if runtime.config.config_path else ""
        )
        expected_revision = _parse_if_match(request)
        if expected_revision is None:
            return _error(
                "An expected source revision is required before any file change.",
                428,
                code="revision_required",
                unchanged="No configuration file was changed.",
                recovery="Reload the current configuration and retry the edit.",
                source_path=source_path,
            )
        target_id = request.path_params["target_id"]
        try:
            payload = await request.json()
        except Exception:
            return _error(
                "Invalid JSON body",
                422,
                code="configuration_invalid",
                unchanged="No configuration file was changed.",
                recovery="Provide a valid JSON request body and retry.",
                source_path=source_path,
            )
        if not isinstance(payload, dict):
            return _error(
                "Request body must be a JSON object",
                422,
                code="configuration_invalid",
                unchanged="No configuration file was changed.",
                recovery="Provide a JSON object payload and retry.",
                source_path=source_path,
            )
        try:
            data = TargetEditorData.model_validate(payload)
        except (ValidationError, ValueError) as exc:
            return _error(
                sanitize_config_error(exc),
                422,
                code="configuration_invalid",
                unchanged="No configuration file was changed.",
                recovery="Correct the target fields and retry.",
                source_path=source_path,
            )
        try:
            result, updated = runtime.mutations.update_target(
                target_id, data, expected_revision=expected_revision
            )
            response = _json_response(
                TargetResponse(
                    revision=result.revision,
                    source_path=result.source_path.as_posix(),
                    target=updated,
                )
            )
            response.headers["cache-control"] = "no-store"
            response.headers["etag"] = f'"{result.revision}"'
            return response
        except ConfigurationMutationError as exc:
            return _handle_mutation_error(exc)

    async def config_target_delete(request: Request) -> Response:
        if not _authorized_mutation(request, state):
            return _forbidden()
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        source_path = (
            runtime.config.config_path.as_posix() if runtime.config.config_path else ""
        )
        expected_revision = _parse_if_match(request)
        if expected_revision is None:
            return _error(
                "An expected source revision is required before any file change.",
                428,
                code="revision_required",
                unchanged="No configuration file was changed.",
                recovery="Reload the current configuration and retry the deletion.",
                source_path=source_path,
            )
        target_id = request.path_params["target_id"]
        try:
            result, deleted_id = runtime.mutations.delete_target(
                target_id, expected_revision=expected_revision
            )
            response = _json_response(
                TargetDeleteResponse(
                    revision=result.revision,
                    source_path=result.source_path.as_posix(),
                    deleted=deleted_id,
                )
            )
            response.headers["cache-control"] = "no-store"
            response.headers["etag"] = f'"{result.revision}"'
            return response
        except ConfigurationMutationError as exc:
            return _handle_mutation_error(exc)

    async def targets(request: Request) -> Response:
        try:
            return _json_response(_runtime(state).targets())
        except RuntimeError:
            return _runtime_error()

    async def profiles(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            return _json_response(
                {
                    "default": runtime.catalog.default_profile,
                    "available": sorted(runtime.catalog.profiles),
                }
            )
        except RuntimeError:
            return _runtime_error()

    async def projects(request: Request) -> Response:
        try:
            return _json_response(_runtime(state).database.projects())
        except RuntimeError:
            return _runtime_error()

    async def project(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            project_view = runtime.database.project(request.path_params["project_id"])
            if project_view is None:
                return _error("Unknown project", 404, code="not_found")
            catalog = runtime.catalog_for_project_cached(project_view.id)
            return _json_response(
                {
                    "project": project_view,
                    "configuration": _profile_config_data(runtime.catalog, catalog),
                    "context_instructions": runtime.context_instructions(project_view.id),
                }
            )
        except RuntimeError:
            return _runtime_error()
        except (ValueError, KeyError) as exc:
            return _error(
                sanitize_config_error(exc),
                422,
                code="configuration_invalid",
                unchanged="No configuration file was changed.",
                recovery="Fix the project configuration file and retry.",
                source_path=(Path(project_view.root) / ".openmcp" / "config.toml").as_posix(),
            )

    async def project_profiles(request: Request) -> Response:
        response = await project(request)
        if response.status_code != 200:
            return response
        payload = json.loads(response.body)
        return _json_response(payload["configuration"])

    async def task_guide(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            project_id = request.query_params.get("project_id", "")
            if project_id and runtime.database.project(project_id) is None:
                return _error("Unknown project", 404, code="not_found")
            guide = load_task_guide(
                runtime.config.home,
                Path(runtime.database.project(project_id).root)
                if project_id
                else None,
            )
            return _json_response({"guide": guide, "source_path": _source_path(runtime, project_id).as_posix()})
        except RuntimeError:
            return _runtime_error()
        except ValueError as exc:
            return _error(str(exc), 422, code="task_guide_invalid")

    async def context_instructions(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            project_id = request.path_params["project_id"]
            if runtime.database.project(project_id) is None:
                return _error("Unknown project", 404, code="not_found")
            return _json_response(runtime.context_instructions(project_id))
        except RuntimeError:
            return _runtime_error()

    async def project_jobs(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            project_id = request.path_params["project_id"]
            project_view = runtime.database.project(project_id)
            if project_view is None:
                return _error("Unknown project", 404, code="not_found")
            jobs = [
                _dashboard_job(runtime, job.id)
                for job in runtime.database.jobs(project_view.id)
            ]
            return _json_response([job for job in jobs if job is not None])
        except RuntimeError:
            return _runtime_error()

    async def job(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            value = _dashboard_job(runtime, request.path_params["job_id"])
            if value is None:
                return _error("Unknown job", 404, code="not_found")
            return _json_response(value)
        except RuntimeError:
            return _runtime_error()

    async def job_events(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            job_id = request.path_params["job_id"]
            if _dashboard_job(runtime, job_id) is None:
                return _error("Unknown job", 404, code="not_found")
            return _json_response(
                [
                    {key: event[key] for key in ("id", "created_at", "kind")}
                    for event in runtime.database.events(job_id)
                ]
            )
        except RuntimeError:
            return _runtime_error()

    async def api_not_found(request: Request) -> Response:
        return _error(
            "Dashboard API route not found",
            404,
            code="not_found",
            unchanged="No dashboard data was changed.",
            recovery="Check the dashboard API path and try again.",
        )

    async def dashboard_index(request: Request) -> Response:
        index_file = _STATIC_DIR / "index.html"
        if not index_file.is_file():
            return _error(
                "Dashboard assets are unavailable",
                503,
                code="dashboard_unavailable",
                unchanged="The MCP transport and dashboard API remain available.",
                recovery="Build the frontend assets and restart the daemon.",
            )
        response = FileResponse(index_file, media_type="text/html")
        response.headers["cache-control"] = "no-store"
        return response

    async def dashboard_deep_link(request: Request) -> Response:
        return await dashboard_index(request)

    async def update_context_instruction(request: Request) -> Response:
        if not _authorized_mutation(request, state):
            return _forbidden()
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        try:
            payload = await request.json()
        except Exception:
            return _error("Invalid JSON body", 400, code="invalid_request")
        if not isinstance(payload, dict):
            return _error("Request body must be an object", 400, code="invalid_request")
        if request.method == "DELETE" and not any(
            key in payload for key in ("expected_current", "expected_current_value", "expected")
        ):
            return _error(
                "Expected current value is required",
                400,
                code="invalid_request",
            )
        if not isinstance(payload.get("instruction", ""), str):
            return _error("Instruction must be a string", 400, code="invalid_request")
        expected = payload.get(
            "expected_current",
            payload.get("expected_current_value", payload.get("expected", "")),
        )
        if not isinstance(expected, str):
            return _error("Expected current value must be a string", 400, code="invalid_request")
        workflow = request.path_params.get("workflow", "") or payload.get("workflow", "")
        if not isinstance(workflow, str) or not workflow:
            return _error("Workflow must be a string", 400, code="invalid_request")
        try:
            updated, current, workflow = runtime.compare_and_set_context_instruction(
                request.path_params["project_id"],
                workflow,
                expected,
                payload.get("instruction", ""),
            )
            project_view = runtime.database.project(request.path_params["project_id"])
            if not updated:
                return _error(
                    "Context instruction changed",
                    409,
                    code="context_conflict",
                    unchanged="The newer context instruction remains unchanged.",
                    recovery="Refresh the current instruction and retry.",
                    current=current,
                )
            return _json_response(
                DashboardContextInstruction(
                    project_id=project_view.id,
                    workflow=workflow,
                    instruction=current,
                )
            )
        except RuntimeError:
            return _runtime_error()
        except ValueError as exc:
            message = str(exc)
            if message.startswith("Unknown project"):
                return _error("Unknown project", 404, code="not_found")
            return _error(message, 400, code="invalid_request")

    async def missing_asset(request: Request) -> Response:
        return Response(status_code=404)

    asset_directory = _STATIC_DIR / "assets"
    asset_route = (
        Mount(
            "/dashboard/assets",
            app=StaticFiles(directory=str(asset_directory)),
            name="dashboard_assets",
        )
        if asset_directory.is_dir()
        else Route("/dashboard/assets/{path:path}", missing_asset, methods=["GET"])
    )

    return [
        Route("/dashboard/api/bootstrap", bootstrap, methods=["GET"]),
        Route("/dashboard/api/overview", overview, methods=["GET"]),
        Route("/dashboard/api/status", status, methods=["GET"]),
        Route("/dashboard/api/configuration", configuration, methods=["GET"]),
        Route("/dashboard/api/config", configuration, methods=["GET"]),
        Route("/dashboard/api/config/health", configuration, methods=["GET"]),
        Route("/dashboard/api/settings", settings, methods=["GET"]),
        Route("/dashboard/api/configuration/targets", config_targets_get, methods=["GET"]),
        Route("/dashboard/api/configuration/targets", config_target_create, methods=["POST"]),
        Route("/dashboard/api/configuration/targets/{target_id}", config_target_get, methods=["GET"]),
        Route("/dashboard/api/configuration/targets/{target_id}", config_target_update, methods=["PUT"]),
        Route("/dashboard/api/configuration/targets/{target_id}", config_target_delete, methods=["DELETE"]),
        Route("/dashboard/api/targets", targets, methods=["GET"]),
        Route("/dashboard/api/profiles", profiles, methods=["GET"]),
        Route("/dashboard/api/projects", projects, methods=["GET"]),
        Route("/dashboard/api/projects/{project_id}", project, methods=["GET"]),
        Route("/dashboard/api/projects/{project_id}/configuration", project_profiles, methods=["GET"]),
        Route("/dashboard/api/projects/{project_id}/profiles", project_profiles, methods=["GET"]),
        Route("/dashboard/api/task-guide", task_guide, methods=["GET"]),
        Route("/dashboard/api/projects/{project_id}/task-guide", task_guide, methods=["GET"]),
        Route("/dashboard/api/projects/{project_id}/context-instructions", context_instructions, methods=["GET"]),
        Route("/dashboard/api/projects/{project_id}/context-instructions", update_context_instruction, methods=["PUT", "POST", "DELETE"]),
        Route("/dashboard/api/projects/{project_id}/jobs", project_jobs, methods=["GET"]),
        Route("/dashboard/api/jobs/{job_id}", job, methods=["GET"]),
        Route("/dashboard/api/jobs/{job_id}/events", job_events, methods=["GET"]),
        Route(
            "/dashboard/api/projects/{project_id}/context-instructions/{workflow}",
            update_context_instruction,
            methods=["PUT", "POST", "DELETE"],
        ),
        Route("/dashboard/api", api_not_found, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]),
        Route("/dashboard/api/{path:path}", api_not_found, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]),
        Route("/dashboard/assets", missing_asset, methods=["GET"]),
        asset_route,
        Route("/dashboard", dashboard_index, methods=["GET"]),
        Route("/dashboard/", dashboard_index, methods=["GET"]),
        Route("/dashboard/{path:path}", dashboard_deep_link, methods=["GET"]),
    ]


__all__ = ["DashboardState", "register_dashboard_routes"]
