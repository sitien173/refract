"""Safe, in-process dashboard HTTP endpoints."""

from __future__ import annotations

import asyncio
import ipaddress
import inspect
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, cast
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from pydantic import ValidationError

from refract.ask import AskAuthError, AskConflictError
from refract.config import DaemonConfig, ProfileDeclaration, TargetSelection, load_task_guide
from refract.config_inspection import sanitize_config_error
from refract.config_mutation import ConfigurationMutationError
from refract.models import (
    DashboardBootstrap,
    DashboardError,
    DashboardJob,
    DashboardOverview,
    JobOutputResponse,
    JobResult,
    ProfileDeleteResponse,
    ProfileEditorData,
    ProfileEditorResponse,
    ProfileListResponse,
    ProfileResponse,
    ProjectOverrideDeleteResponse,
    ProjectOverrideListResponse,
    ProjectOverrideResponse,
    StreamStatus,
    TERMINAL_STATES,
    TargetDeleteResponse,
    TargetEditorData,
    TargetListResponse,
    TargetResponse,
)
from refract.planning import parse_execution_plan
from refract.workflows import BUILTIN_WORKFLOWS
from refract.workers import run_sync


_STATIC_DIR = Path(__file__).parent / "dashboard_static"
_REFRACT_DIR = ".refract"
_UNKNOWN_PROJECT = "Unknown project"
_TARGET_ROUTE = "/dashboard/api/configuration/targets/{target_id:path}"
_PROFILE_ROUTE = "/dashboard/api/configuration/profiles/{profile_id}"
_PROJECT_OVERRIDE_ROUTE = "/dashboard/api/projects/{project_id}/profile-overrides/{profile_id}"
SSE_KEEPALIVE_INTERVAL_S: float = 20.0


@dataclass
class DashboardState:
    """Application-owned state shared by dashboard routes and MCP lifespan."""

    runtime: Any = None
    csrf_token: str = ""


def _jsonable(value: Any) -> Any:
    if isinstance(
        value,
        (
            ProfileEditorResponse,
            ProfileListResponse,
            ProfileResponse,
            ProjectOverrideListResponse,
            ProjectOverrideResponse,
            ProjectOverrideDeleteResponse,
        ),
    ):
        return value.model_dump(mode="json")
    if isinstance(value, DashboardJob):
        data = value.model_dump(mode="json", exclude={"result"})
        data["result"] = value.result.model_dump(mode="json")
        return data
    if isinstance(value, JobResult):
        return value.model_dump(mode="json")
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
        raise RuntimeError("Refract runtime is not active")
    return state.runtime


def _runtime_error() -> Response:
    return _error(
        "Refract runtime is not active",
        503,
        code="runtime_unavailable",
        unchanged="No dashboard data was changed.",
        recovery="Retry after the daemon has started.",
    )


def _selection_data(selection: TargetSelection) -> dict[str, Any]:
    return {
        "targets": list(selection.targets),
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


def _settings_payload(runtime: Any) -> dict[str, Any]:
    cfg = runtime.catalog
    logging = cfg.logging
    return {
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


def _dashboard_job(runtime: Any, job_id: str) -> DashboardJob | None:
    record = runtime.database.job_record(job_id)
    return None if record is None else _dashboard_job_from_record(runtime, record)


def _dashboard_job_from_record(runtime: Any, record: dict[str, Any], diagnostic_count: int | None = None) -> DashboardJob:
    job = runtime.database.job_view(record)
    try:
        raw_plan = json.loads(record.get("execution_plan_json", ""))
    except (TypeError, json.JSONDecodeError):
        raw_plan = None
    if diagnostic_count is None:
        diagnostic_count = runtime.database.diagnostic_counts([job.id]).get(job.id, 0)
    return DashboardJob(
        id=job.id,
        project_id=job.project_id,
        workflow=job.workflow,
        profile=job.profile,
        prompt=str(record.get("prompt") or ""),
        state=job.state,
        context_key=job.context_key,
        config_revision=job.config_revision,
        target_id=job.target_id,
        attempts=job.attempts,
        created_at=job.created_at,
        updated_at=job.updated_at,
        result=JobResult(
            text=job.result.text,
            error=job.result.error,
            metadata=runtime.live_result_metadata(job),
        ),
        execution_plan=_safe_execution_plan(raw_plan),
        diagnostic_count=diagnostic_count,
        suspect=diagnostic_count > 0,
    )


def _source_path(runtime: Any, project_id: str) -> Path:
    project = runtime.database.project(project_id)
    if project is not None:
        root = Path(project.root) / _REFRACT_DIR
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
    # Service messages are written by the service itself; loader messages
    # inside them were sanitized when the load error was raised.
    return _error(
        str(exc),
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
    provided = request.headers.get("x-refract-csrf", "")
    return bool(state.csrf_token) and secrets.compare_digest(
        provided, state.csrf_token
    )


def _loopback_route(path: str, endpoint: Callable[[Request], Awaitable[Response] | Response], methods: list[str]) -> Route:
    """Serve ``endpoint`` only to loopback clients that address a loopback host.

    The check blocks DNS-rebinding pages, which reach the daemon from a
    loopback client but under a foreign Host header.
    """

    async def guarded(request: Request) -> Response:
        if not _authorized_editor_read(request):
            return _forbidden()
        if inspect.iscoroutinefunction(endpoint):
            return await endpoint(request)
        return await run_sync(cast(Callable[[Request], Response], endpoint), request)

    return Route(path, guarded, methods=methods)


def _register_status_routes(state: DashboardState) -> list[Route]:
    async def bootstrap(request: Request) -> Response:
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

    def overview(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            daemon = runtime.status()
            configuration = runtime.config_health
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
            return _json_response(_runtime(state).config_health)
        except RuntimeError:
            return _runtime_error()

    def settings(request: Request) -> Response:
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        if request.method != "GET":
            return Response(status_code=405, headers={"allow": "GET"})
        response = _json_response(_settings_payload(runtime))
        response.headers["cache-control"] = "no-store"
        response.headers["etag"] = f'"{runtime.catalog.config_revision}"'
        return response

    return [
        _loopback_route("/dashboard/api/bootstrap", bootstrap, methods=["GET"]),
        _loopback_route("/dashboard/api/overview", overview, methods=["GET"]),
        _loopback_route("/dashboard/api/status", status, methods=["GET"]),
        _loopback_route("/dashboard/api/configuration", configuration, methods=["GET"]),
        _loopback_route("/dashboard/api/settings", settings, methods=["GET"]),
    ]


def _register_target_configuration_routes(state: DashboardState) -> list[Route]:
    def config_targets_get(request: Request) -> Response:
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

    def config_target_get(request: Request) -> Response:
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

    config_target_create = _mutation_route(
        state, TargetEditorData, "create_target", TargetResponse, "target"
    )
    config_target_update = _mutation_route(
        state, TargetEditorData, "update_target", TargetResponse, "target"
    )
    config_target_delete = _mutation_route(
        state, None, "delete_target", TargetDeleteResponse, "deleted", delete=True
    )
    return [
        _loopback_route("/dashboard/api/configuration/targets", config_targets_get, methods=["GET"]),
        _loopback_route("/dashboard/api/configuration/targets", config_target_create, methods=["POST"]),
        _loopback_route(_TARGET_ROUTE, config_target_get, methods=["GET"]),
        _loopback_route(_TARGET_ROUTE, config_target_update, methods=["PUT"]),
        _loopback_route(_TARGET_ROUTE, config_target_delete, methods=["DELETE"]),
    ]


async def _mutation_scope(request: Request, runtime: Any, project_scope: bool) -> tuple[list[Any], str] | Response:
    if not project_scope:
        return [], runtime.config.config_path.as_posix() if runtime.config.config_path else ""
    project_view = await run_sync(runtime.database.project, request.path_params["project_id"])
    if project_view is None:
        return _error(_UNKNOWN_PROJECT, 404, code="not_found")
    root = Path(project_view.root)
    return [root], (root / _REFRACT_DIR / "config.toml").as_posix()


async def _mutation_payload(request: Request, model: Any, source_path: str) -> Any:
    try:
        payload = await request.json()
    except Exception:
        return _error(
            "Invalid JSON body", 422, code="configuration_invalid",
            unchanged="No configuration file was changed.",
            recovery="Provide a valid JSON request body and retry.", source_path=source_path,
        )
    if not isinstance(payload, dict):
        return _error(
            "Request body must be a JSON object", 422, code="configuration_invalid",
            unchanged="No configuration file was changed.",
            recovery="Provide a JSON object payload and retry.", source_path=source_path,
        )
    try:
        return model.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        entity = "target" if model is TargetEditorData else "profile"
        return _error(
            sanitize_config_error(exc), 422, code="configuration_invalid",
            unchanged="No configuration file was changed.",
            recovery=f"Correct the {entity} fields and retry.", source_path=source_path,
        )


def _mutation_response(result, value, remaining, response_model, field) -> Response:
    values = {"revision": result.revision, "source_path": result.source_path.as_posix()}
    values[field] = value
    if response_model is ProfileResponse:
        values.update(default_profile=result.config.default_profile,
                      available_targets=sorted(t.id for t in result.config.targets))
    if response_model is ProjectOverrideDeleteResponse:
        values["fallback"] = remaining[0]
    response = _json_response(response_model(**values))
    response.headers["cache-control"] = "no-store"
    response.headers["etag"] = f'"{result.revision}"'
    return response


def _mutation_route(state, model, method, response_model, field, *, project_scope=False, delete=False):
    async def mutate(request: Request) -> Response:
        if not _authorized_mutation(request, state):
            return _forbidden()
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        scope = await _mutation_scope(request, runtime, project_scope)
        if isinstance(scope, Response):
            return scope
        args, source_path = scope
        expected_revision = _parse_if_match(request)
        if expected_revision is None:
            return _error(
                "An expected source revision is required before any file change.",
                428, code="revision_required",
                unchanged="No configuration file was changed.",
                recovery="Reload the current configuration and retry the deletion." if delete
                else "Reload the current configuration and retry the edit.",
                source_path=source_path,
            )
        if not method.startswith("create_"):
            id_key = "target_id" if "target" in method else "profile_id"
            args.append(request.path_params[id_key])
        if model is not None:
            payload = await _mutation_payload(request, model, source_path)
            if isinstance(payload, Response):
                return payload
            args.append(payload)
        try:
            result, value, *remaining = await run_sync(
                getattr(runtime.mutations, method), *args, expected_revision=expected_revision
            )
            return _mutation_response(result, value, remaining, response_model, field)
        except ConfigurationMutationError as exc:
            return _handle_mutation_error(exc)
    return mutate


def _register_profile_configuration_routes(state: DashboardState) -> list[Route]:
    def config_profiles_get(request: Request) -> Response:
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        try:
            source_read, profiles_data, default_profile, available_targets = (
                runtime.mutations.read_profiles()
            )
            response = _json_response(
                ProfileListResponse(
                    revision=source_read.revision,
                    source_path=source_read.path.as_posix(),
                    default_profile=default_profile,
                    available_targets=available_targets,
                    profiles=profiles_data,
                )
            )
            response.headers["cache-control"] = "no-store"
            response.headers["etag"] = f'"{source_read.revision}"'
            return response
        except ConfigurationMutationError as exc:
            return _handle_mutation_error(exc)

    def config_profile_get(request: Request) -> Response:
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        profile_id = request.path_params["profile_id"]
        try:
            source_read, profile_data, default_profile, available_targets = (
                runtime.mutations.get_profile(profile_id)
            )
            response = _json_response(
                ProfileResponse(
                    revision=source_read.revision,
                    source_path=source_read.path.as_posix(),
                    default_profile=default_profile,
                    available_targets=available_targets,
                    profile=profile_data,
                )
            )
            response.headers["cache-control"] = "no-store"
            response.headers["etag"] = f'"{source_read.revision}"'
            return response
        except ConfigurationMutationError as exc:
            return _handle_mutation_error(exc)

    config_profile_create = _mutation_route(
        state, ProfileEditorData, "create_profile", ProfileResponse, "profile"
    )

    config_profile_update = _mutation_route(
        state, ProfileEditorData, "update_profile", ProfileResponse, "profile"
    )

    config_profile_delete = _mutation_route(
        state, None, "delete_profile", ProfileDeleteResponse, "deleted", delete=True
    )
    return [
        _loopback_route("/dashboard/api/configuration/profiles", config_profiles_get, methods=["GET"]),
        _loopback_route("/dashboard/api/configuration/profiles", config_profile_create, methods=["POST"]),
        _loopback_route(_PROFILE_ROUTE, config_profile_get, methods=["GET"]),
        _loopback_route(_PROFILE_ROUTE, config_profile_update, methods=["PUT"]),
        _loopback_route(_PROFILE_ROUTE, config_profile_delete, methods=["DELETE"]),
    ]


def _register_project_override_routes(state: DashboardState) -> list[Route]:
    def project_profile_overrides_get(request: Request) -> Response:
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        project_view = runtime.database.project(request.path_params["project_id"])
        if project_view is None:
            return _error(_UNKNOWN_PROJECT, 404, code="not_found")
        try:
            source_read, overrides, g_def, p_def, targets = (
                runtime.mutations.read_project_overrides(Path(project_view.root))
            )
            response = _json_response(
                ProjectOverrideListResponse(
                    revision=source_read.revision,
                    source_path=source_read.path.as_posix(),
                    global_default_profile=g_def,
                    project_default_profile=p_def,
                    available_targets=targets,
                    overrides=overrides,
                )
            )
            response.headers["cache-control"] = "no-store"
            response.headers["etag"] = f'"{source_read.revision}"'
            return response
        except ConfigurationMutationError as exc:
            return _handle_mutation_error(exc)

    def project_profile_override_get(request: Request) -> Response:
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        project_view = runtime.database.project(request.path_params["project_id"])
        if project_view is None:
            return _error(_UNKNOWN_PROJECT, 404, code="not_found")
        profile_id = request.path_params["profile_id"]
        try:
            source_read, override, _, _, _ = (
                runtime.mutations.get_project_override(Path(project_view.root), profile_id)
            )
            response = _json_response(
                ProjectOverrideResponse(
                    revision=source_read.revision,
                    source_path=source_read.path.as_posix(),
                    override=override,
                )
            )
            response.headers["cache-control"] = "no-store"
            response.headers["etag"] = f'"{source_read.revision}"'
            return response
        except ConfigurationMutationError as exc:
            return _handle_mutation_error(exc)

    project_profile_override_create = _mutation_route(
        state, ProfileEditorData, "create_project_override", ProjectOverrideResponse, "override", project_scope=True
    )

    project_profile_override_update = _mutation_route(
        state, ProfileEditorData, "update_project_override", ProjectOverrideResponse, "override", project_scope=True
    )

    project_profile_override_delete = _mutation_route(
        state, None, "delete_project_override", ProjectOverrideDeleteResponse, "deleted", project_scope=True, delete=True
    )
    return [
        _loopback_route("/dashboard/api/projects/{project_id}/profile-overrides", project_profile_overrides_get, methods=["GET"]),
        _loopback_route("/dashboard/api/projects/{project_id}/profile-overrides", project_profile_override_create, methods=["POST"]),
        _loopback_route(_PROJECT_OVERRIDE_ROUTE, project_profile_override_get, methods=["GET"]),
        _loopback_route(_PROJECT_OVERRIDE_ROUTE, project_profile_override_update, methods=["PUT"]),
        _loopback_route(_PROJECT_OVERRIDE_ROUTE, project_profile_override_delete, methods=["DELETE"]),
    ]


def _register_catalog_routes(state: DashboardState) -> list[Route]:
    def targets(request: Request) -> Response:
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

    return [
        _loopback_route("/dashboard/api/targets", targets, methods=["GET"]),
        _loopback_route("/dashboard/api/profiles", profiles, methods=["GET"]),
    ]


def _register_project_routes(state: DashboardState) -> list[Route]:
    def projects(request: Request) -> Response:
        try:
            return _json_response(_runtime(state).database.projects())
        except RuntimeError:
            return _runtime_error()

    def project(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            project_view = runtime.database.project(request.path_params["project_id"])
            if project_view is None:
                return _error(_UNKNOWN_PROJECT, 404, code="not_found")
            catalog = runtime.catalog_for_project_cached(project_view.id)
            return _json_response(
                {
                    "project": project_view,
                    "configuration": _profile_config_data(runtime.catalog, catalog),
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
                source_path=(Path(project_view.root) / _REFRACT_DIR / "config.toml").as_posix(),
            )

    return [
        _loopback_route("/dashboard/api/projects", projects, methods=["GET"]),
        _loopback_route("/dashboard/api/projects/{project_id}", project, methods=["GET"]),
    ]


def _register_task_guide_routes(state: DashboardState) -> list[Route]:
    def task_guide(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            project_id = request.query_params.get("project_id", "")
            if project_id and runtime.database.project(project_id) is None:
                return _error(_UNKNOWN_PROJECT, 404, code="not_found")
            guide = load_task_guide(
                runtime.config.home,
                Path(runtime.database.project(project_id).root)
                if project_id
                else None,
            )
            return _json_response({"guide": guide, "workflows": list(BUILTIN_WORKFLOWS),
                                   "source_path": _source_path(runtime, project_id).as_posix()})
        except RuntimeError:
            return _runtime_error()
        except ValueError as exc:
            return _error(str(exc), 422, code="task_guide_invalid")

    return [
        _loopback_route("/dashboard/api/task-guide", task_guide, methods=["GET"]),
    ]


def _register_diagnostics_routes(state: DashboardState) -> list[Route]:
    def diagnostics(request: Request) -> Response:
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()
        allowed = {"project_id", "job_id", "category", "before", "limit"}
        if set(request.query_params.keys()) - allowed or any(len(request.query_params.getlist(key)) != 1 for key in request.query_params.keys()):
            return _error("Invalid diagnostics query parameters", 400, code="bad_request")
        project_id = request.query_params.get("project_id", "")
        job_id = request.query_params.get("job_id", "")
        category = request.query_params.get("category", "")
        if any(key in request.query_params and not request.query_params[key]
               for key in ("project_id", "job_id", "category")):
            return _error("Diagnostics filters must not be empty", 400, code="bad_request")
        if category and category not in {"protocol", "output"}:
            return _error("Invalid diagnostics category", 400, code="bad_request")
        before_raw = request.query_params.get("before")
        limit_raw = request.query_params.get("limit", "50")
        if not limit_raw.isascii() or not limit_raw.isdecimal():
            return _error("Invalid diagnostics limit", 400, code="bad_request")
        normalized_limit = limit_raw.lstrip("0")
        if not normalized_limit or len(normalized_limit) > 3:
            return _error("Invalid diagnostics limit", 400, code="bad_request")
        limit = int(normalized_limit)
        if not 1 <= limit <= 100:
            return _error("Invalid diagnostics limit", 400, code="bad_request")
        before = None
        if before_raw is not None:
            if not before_raw.isascii() or not before_raw.isdecimal():
                return _error("Invalid diagnostics cursor", 400, code="bad_request")
            normalized_before = before_raw.lstrip("0")
            max_cursor = "9223372036854775807"
            if (not normalized_before or len(normalized_before) > len(max_cursor)
                    or (len(normalized_before) == len(max_cursor) and normalized_before > max_cursor)):
                return _error("Invalid diagnostics cursor", 400, code="bad_request")
            before = int(normalized_before)
        if project_id:
            project = runtime.database.project(project_id)
            if project is None:
                return _error(_UNKNOWN_PROJECT, 404, code="not_found")
            project_id = project.id
        if job_id and runtime.database.job(job_id) is None:
            return _error("Unknown job", 404, code="not_found")
        rows = runtime.database.diagnostic_reports(
            project_id=project_id, job_id=job_id, category=category,
            before=before, limit=limit,
        )
        has_more = len(rows) > limit
        reports = rows[:limit]
        return _json_response({"reports": reports, "next_before": reports[-1]["id"] if has_more and reports else None})

    return [_loopback_route("/dashboard/api/diagnostics", diagnostics, methods=["GET"])]


def _register_job_routes(state: DashboardState) -> list[Route]:
    def project_jobs(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            project_id = request.path_params["project_id"]
            project_view = runtime.database.project(project_id)
            if project_view is None:
                return _error(_UNKNOWN_PROJECT, 404, code="not_found")
            active, recent, more_recent = runtime.database.job_listing(project_view.id)
            counts = runtime.database.diagnostic_counts([record["id"] for record in (*active, *recent)])
            return _json_response({
                "active": [_dashboard_job_from_record(runtime, record, counts.get(record["id"], 0)) for record in active],
                "recent": [_dashboard_job_from_record(runtime, record, counts.get(record["id"], 0)) for record in recent],
                "more_recent": more_recent,
            })
        except RuntimeError:
            return _runtime_error()

    def job(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            value = _dashboard_job(runtime, request.path_params["job_id"])
            if value is None:
                return _error("Unknown job", 404, code="not_found")
            return _json_response(value)
        except RuntimeError:
            return _runtime_error()

    return [
        _loopback_route("/dashboard/api/projects/{project_id}/jobs", project_jobs, methods=["GET"]),
        _loopback_route("/dashboard/api/jobs/{job_id}", job, methods=["GET"]),
    ]


def _job_stream_status(metadata: dict[str, Any], state: str) -> StreamStatus:
    if metadata["failed"]:
        return "failed"
    if metadata["truncated"]:
        return "truncated"
    if state not in TERMINAL_STATES:
        return "active"
    if metadata["retained_from"] <= 0:
        return "unavailable"
    return "complete"


def _output_update(cursor: int) -> bytes:
    return (
        f"event: output-updated\n"
        f"id: {cursor}\n"
        f"data: {json.dumps({'cursor': cursor})}\n\n"
    ).encode("utf-8")


async def _stream_output_updates(request: Request, runtime: Any, job_id: str, queue: Any, last_sent: int):
    while True:
        current = await run_sync(runtime.database.job, job_id)
        if current is None or current.state in TERMINAL_STATES:
            final_cursor = await run_sync(runtime.database.stream_high_water, job_id)
            if final_cursor > last_sent:
                yield _output_update(final_cursor)
            break
        if await request.is_disconnected():
            break
        try:
            cursor = await asyncio.wait_for(
                queue.get(), timeout=SSE_KEEPALIVE_INTERVAL_S
            )
            if cursor > last_sent:
                last_sent = cursor
                yield _output_update(cursor)
        except asyncio.TimeoutError:
            yield b": keepalive\n\n"


async def _job_output_events(request: Request, runtime: Any, job_id: str):
    queue = runtime.stream_hub.subscribe(job_id)
    try:
        initial_hw = await run_sync(runtime.database.stream_high_water, job_id)
        yield _output_update(initial_hw)
        async for event in _stream_output_updates(request, runtime, job_id, queue, initial_hw):
            yield event
    finally:
        runtime.stream_hub.unsubscribe(job_id, queue)


def _register_job_output_routes(state: DashboardState) -> list[Route]:
    def job_output(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            job_id = request.path_params["job_id"]
            job = runtime.database.job(job_id)
            if job is None:
                return _error("Unknown job", 404, code="not_found")
            try:
                after = max(0, int(request.query_params.get("after", 0)))
            except (ValueError, TypeError):
                after = 0
            try:
                limit = int(request.query_params.get("limit", 100))
            except (ValueError, TypeError):
                limit = 100
            safe_limit = max(1, min(limit, 500))

            metadata = runtime.database.stream_metadata(job_id)
            high_water = metadata["high_water"]
            retained_from = metadata["retained_from"]
            events = runtime.database.stream_events(job_id, after=after, limit=safe_limit)

            stream_status = _job_stream_status(metadata, job.state)

            cursor = events[-1].id if events else after
            has_more = bool(events and events[-1].id < high_water)

            return _json_response(
                JobOutputResponse(
                    events=events,
                    cursor=cursor,
                    has_more=has_more,
                    retained_from=retained_from,
                    stream_status=stream_status,
                )
            )
        except RuntimeError:
            return _runtime_error()

    async def job_output_updates(request: Request) -> Response:
        try:
            runtime = _runtime(state)
            job_id = request.path_params["job_id"]
            job = await run_sync(runtime.database.job, job_id)
            if job is None:
                return _error("Unknown job", 404, code="not_found")

            response = StreamingResponse(
                _job_output_events(request, runtime, job_id),
                media_type="text/event-stream",
            )
            response.headers["Cache-Control"] = "no-cache"
            response.headers["Connection"] = "keep-alive"
            response.headers["X-Accel-Buffering"] = "no"
            return response
        except RuntimeError:
            return _runtime_error()

    return [
        _loopback_route("/dashboard/api/jobs/{job_id}/output", job_output, methods=["GET"]),
        _loopback_route("/dashboard/api/jobs/{job_id}/output/updates", job_output_updates, methods=["GET"]),
    ]


def _register_asset_routes() -> list[Route]:
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
        _loopback_route("/dashboard/api", api_not_found, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]),
        _loopback_route("/dashboard/api/{path:path}", api_not_found, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]),
        _loopback_route("/dashboard/assets", missing_asset, methods=["GET"]),
        asset_route,
        _loopback_route("/dashboard", dashboard_index, methods=["GET"]),
        _loopback_route("/dashboard/", dashboard_index, methods=["GET"]),
        _loopback_route("/dashboard/{path:path}", dashboard_deep_link, methods=["GET"]),
    ]


def _register_ask_routes(state: DashboardState) -> list[Route]:
    async def ask(request: Request) -> Response:
        try:
            runtime = _runtime(state)
        except RuntimeError:
            return _runtime_error()

        try:
            raw_body = await request.body()
        except Exception:
            return _error("Malformed request body", 400, code="bad_request")

        if not raw_body:
            return _error("Malformed request body", 400, code="bad_request")

        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception:
            return _error("Malformed request body", 400, code="bad_request")

        if not isinstance(body, dict):
            return _error("Malformed request body", 400, code="bad_request")

        token = body.get("token")
        question = body.get("question")
        job_id = body.get("job_id") or request.headers.get("x-refract-job-id") or request.query_params.get("job_id")

        if not isinstance(token, str) or not token:
            return _error("token must be a non-empty string", 400, code="bad_request")

        if not isinstance(question, str) or not question.strip():
            return _error("question must be a non-empty string", 400, code="bad_request")

        if job_id is not None and not isinstance(job_id, str):
            return _error("job_id must be a string", 400, code="bad_request")

        registry = getattr(runtime, "ask_registry", None)
        if registry is None:
            return _runtime_error()

        timeout_s = getattr(runtime.config, "ask_timeout_s", 300)
        try:
            answer = await registry.ask(
                token=token,
                question=question,
                timeout_s=timeout_s,
                job_id=job_id,
            )
            return _json_response({"answer": answer}, 200)
        except AskAuthError:
            return _error("Forbidden", 403, code="forbidden")
        except AskConflictError:
            return _error("A question is already pending for this job", 409, code="conflict")

    return [
        _loopback_route("/ask", ask, methods=["POST"]),
    ]


def register_dashboard_routes(state: DashboardState) -> list[Route]:
    return [
        *_register_ask_routes(state),
        *_register_status_routes(state),
        *_register_target_configuration_routes(state),
        *_register_profile_configuration_routes(state),
        *_register_project_override_routes(state),
        *_register_catalog_routes(state),
        *_register_project_routes(state),
        *_register_task_guide_routes(state),
        *_register_diagnostics_routes(state),
        *_register_job_routes(state),
        *_register_job_output_routes(state),
        *_register_asset_routes(),
    ]


__all__ = ["DashboardState", "register_dashboard_routes"]
