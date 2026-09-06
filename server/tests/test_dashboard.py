from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from openmcp.config import load_config
from openmcp.planning import execution_plan_data, resolve_execution_plan
from openmcp.runtime import Runtime
from openmcp.server import create_application
from tests.orchestration_helpers import config


async def request(app, path, *, method="GET", headers=(), body=b"", client_host="127.0.0.1"):
    sent = []
    request_body = body
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": request_body, "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers],
        "client": (client_host, 1234),
        "server": ("127.0.0.1", 8765),
        "scheme": "http",
        "root_path": "",
        "app": None,
    }
    await app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    chunks = [message.get("body", b"") for message in sent if message["type"] == "http.response.body"]
    return start["status"], dict(start["headers"]), b"".join(chunks)


@pytest.fixture
def active_runtime(tmp_path):
    home = tmp_path / "home"
    home.mkdir(parents=True)
    cfg_file = home / "config.toml"
    cfg_file.write_text(
        """# operator comment
[daemon]
default_profile = "balanced"
max_jobs = 2

[[targets]]
id = "primary"
backend = "codex"
profile = "legacy-profile"
model = "gpt-4"
reasoning = "deep"
system_prompt = "act safe"
isolated = false
read_only = false
args = ["--flag"]
max_concurrency = 2

[[targets]]
id = "fallback"
backend = "pi"
isolated = true

[[targets]]
id = "cc/opus-consult-reasoning"
backend = "claude"
model = "claude-opus-5"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
other = "primary"
""",
        encoding="utf-8",
    )
    runtime = Runtime(load_config(cfg_file))
    runtime.register_project(str(tmp_path), "project")
    from openmcp import server
    server._DASHBOARD_STATE.runtime = runtime
    server._DASHBOARD_STATE.csrf_token = "test-token"
    try:
        yield runtime
    finally:
        server._DASHBOARD_STATE.runtime = None
        server._DASHBOARD_STATE.csrf_token = ""
        runtime.database.close()


@pytest.mark.asyncio
async def test_dashboard_reads_fail_closed_without_runtime() -> None:
    from openmcp import server
    server._DASHBOARD_STATE.runtime = None
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/overview")

    assert status == 503
    assert json.loads(body)["error"] == "OpenMCP runtime is not active"


@pytest.mark.asyncio
async def test_dashboard_bootstrap_is_loopback_only_and_not_cached(active_runtime) -> None:
    app = create_application()

    status, headers, body = await request(
        app,
        "/dashboard/api/bootstrap",
        headers=(("Host", "127.0.0.1"),),
    )
    remote, _, _ = await request(
        app,
        "/dashboard/api/bootstrap",
        headers=(("Host", "127.0.0.1"),),
        client_host="192.0.2.1",
    )

    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    assert json.loads(body)["csrf_token"] == "test-token"
    assert remote == 403


@pytest.mark.asyncio
async def test_dashboard_overview_separates_daemon_and_configuration(active_runtime) -> None:
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/overview")

    payload = json.loads(body)
    assert status == 200
    assert set(payload) >= {"daemon", "configuration"}
    assert "status" in payload["daemon"]
    assert "valid" in payload["configuration"]


@pytest.mark.asyncio
async def test_dashboard_project_includes_resolved_configuration(active_runtime) -> None:
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/projects/project")

    payload = json.loads(body)
    assert status == 200
    assert payload["configuration"]["global_default_profile"] == "balanced"
    profile = payload["configuration"]["profiles"][0]
    assert profile["effective"]["consult"]["targets"] == ["primary"]
    assert profile["sources"]["consult"] == "global"


@pytest.mark.asyncio
async def test_dashboard_project_source_attribution_shows_project_override(active_runtime, tmp_path) -> None:
    project_root = tmp_path / "project-config"
    project_root.mkdir()
    project = active_runtime.register_project(str(project_root), "project-config")
    (project_root / ".openmcp").mkdir()
    (project_root / ".openmcp" / "config.toml").write_text(
        '[profiles.balanced]\nconsult = "primary"\n', encoding="utf-8"
    )
    app = create_application()

    status, _, body = await request(
        app, f"/dashboard/api/projects/{project.id}/profiles"
    )

    payload = json.loads(body)
    profile = next(item for item in payload["profiles"] if item["id"] == "balanced")
    assert status == 200
    assert profile["sources"]["consult"] == "project"
    assert profile["effective"]["consult"]["targets"] == ["primary"]


@pytest.mark.asyncio
async def test_dashboard_identical_project_override_reports_project_source(active_runtime, tmp_path) -> None:
    project_root = tmp_path / "identical-project"
    project_root.mkdir()
    project = active_runtime.register_project(str(project_root), "identical-project")
    (project_root / ".openmcp").mkdir()
    (project_root / ".openmcp" / "config.toml").write_text(
        """[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
other = "primary"
""",
        encoding="utf-8",
    )
    app = create_application()

    status, _, body = await request(app, f"/dashboard/api/projects/{project.id}/profiles")

    profile = next(item for item in json.loads(body)["profiles"] if item["id"] == "balanced")
    assert status == 200
    assert profile["sources"]["consult"] == "project"


@pytest.mark.asyncio
async def test_dashboard_project_self_extension_reports_global_inheritance(active_runtime, tmp_path) -> None:
    project_root = tmp_path / "self-project"
    project_root.mkdir()
    project = active_runtime.register_project(str(project_root), "self-project")
    (project_root / ".openmcp").mkdir()
    (project_root / ".openmcp" / "config.toml").write_text(
        '[profiles.balanced]\nextends = "balanced"\nconsult = "primary"\n',
        encoding="utf-8",
    )
    app = create_application()

    status, _, body = await request(app, f"/dashboard/api/projects/{project.id}/profiles")

    profile = next(item for item in json.loads(body)["profiles"] if item["id"] == "balanced")
    assert status == 200
    assert profile["parent"] == {"value": "balanced", "source": "project"}
    assert set(profile["inherited"]) == {"implement", "review", "other"}
    assert profile["inherited"]["implement"]["targets"] == ["primary"]
    assert profile["sources"]["implement"] == "global"
    assert profile["sources"]["consult"] == "project"


@pytest.mark.asyncio
async def test_dashboard_job_detail_redacts_execution_plan(active_runtime) -> None:
    runtime = active_runtime
    project = runtime.database.project("project")
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    runtime.database.create_job(
        job_id="job",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="secret job prompt",
        execution_plan_json=json.dumps(execution_plan_data(plan)),
        context_key="consult",
    )
    app = create_application()

    status, _, body = await request(app, "/dashboard/api/jobs/job")

    payload = json.loads(body)
    assert status == 200
    assert "prompt" not in payload
    assert "execution_plan" in payload
    serialized = json.dumps(payload)
    assert "system_prompt" not in serialized
    assert "backend_profile" not in serialized
    assert '"args"' not in serialized
    assert payload["execution_plan"]["selection"]["targets"] == ["primary"]


def make_static(root: Path) -> None:
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>OpenMCP</title>", encoding="utf-8")
    (root / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")


@pytest.mark.asyncio
async def test_spa_routes_and_api_guard_are_ordered(monkeypatch, tmp_path) -> None:
    from openmcp import dashboard

    make_static(tmp_path)
    monkeypatch.setattr(dashboard, "_STATIC_DIR", tmp_path)
    app = create_application()

    index, headers, body = await request(app, "/dashboard")
    deep, _, deep_body = await request(app, "/dashboard/projects/project-1")
    typo, typo_headers, typo_body = await request(app, "/dashboard/api/not-a-route")
    missing_asset, _, _ = await request(app, "/dashboard/assets/missing.js")
    missing_namespace, _, namespace_body = await request(app, "/dashboard/assets")

    assert index == deep == 200
    assert body == deep_body
    assert headers[b"cache-control"] == b"no-store"
    assert typo == 404
    assert typo_headers[b"content-type"].startswith(b"application/json")
    assert b"<!doctype html>" not in typo_body
    assert missing_asset == missing_namespace == 404
    assert b"<!doctype html>" not in namespace_body


@pytest.mark.asyncio
async def test_missing_frontend_build_does_not_break_application(monkeypatch, tmp_path) -> None:
    from openmcp import dashboard

    monkeypatch.setattr(dashboard, "_STATIC_DIR", tmp_path / "missing-dashboard")
    app = create_application()

    status, _, body = await request(app, "/dashboard/")
    asset_status, _, _ = await request(app, "/dashboard/assets/app.js")

    assert status == 503
    assert b"Dashboard assets are unavailable" in body
    assert asset_status == 404


def test_builtin_workflows_contract() -> None:
    from openmcp.workflows import BUILTIN_WORKFLOWS

    assert BUILTIN_WORKFLOWS == ("consult", "implement", "other", "review")


def test_readme_documents_dashboard_boundaries() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "/dashboard/" in readme
    assert "loopback" in readme.lower()
    assert "read-only" in readme.lower()
    assert "remote administration" in readme.lower()


# ---------------------------------------------------------------------------
# Phase 2: Target configuration CRUD API tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_targets_endpoint_remains_unchanged(active_runtime) -> None:
    app = create_application()
    status, headers, body = await request(app, "/dashboard/api/targets")
    assert status == 200
    payload = json.loads(body)
    assert isinstance(payload, list)
    assert len(payload) >= 1
    for target in payload:
        assert set(target.keys()) <= {
            "id", "model", "backend", "isolated", "read_only",
            "max_concurrency", "active", "healthy", "circuit_open_until",
        }
        assert "system_prompt" not in target
        assert "args" not in target


@pytest.mark.asyncio
async def test_configuration_targets_read_loopback_only_and_no_store(active_runtime) -> None:
    app = create_application()
    status, headers, body = await request(
        app,
        "/dashboard/api/configuration/targets",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    assert b"etag" in headers
    assert headers[b"etag"].startswith(b'"') and headers[b"etag"].endswith(b'"')
    payload = json.loads(body)
    assert "revision" in payload
    assert "source_path" in payload
    assert "targets" in payload
    primary = next(t for t in payload["targets"] if t["id"] == "primary")
    assert primary["backend"] == "codex"
    assert primary["backend_profile"] == "legacy-profile"
    assert primary["system_prompt"] == "act safe"
    assert primary["args"] == ["--flag"]

    remote_status, _, remote_body = await request(
        app,
        "/dashboard/api/configuration/targets",
        headers=(("Host", "127.0.0.1"),),
        client_host="192.0.2.1",
    )
    assert remote_status == 403
    assert json.loads(remote_body)["code"] == "forbidden"

    host_status, _, host_body = await request(
        app,
        "/dashboard/api/configuration/targets",
        headers=(("Host", "attacker.com"),),
    )
    assert host_status == 403
    assert json.loads(host_body)["code"] == "forbidden"


@pytest.mark.asyncio
async def test_configuration_target_get_by_id_and_not_found(active_runtime) -> None:
    app = create_application()
    status, headers, body = await request(
        app,
        "/dashboard/api/configuration/targets/primary",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    assert b"etag" in headers
    payload = json.loads(body)
    assert payload["target"]["id"] == "primary"
    assert payload["target"]["backend"] == "codex"
    assert payload["target"]["system_prompt"] == "act safe"

    slash_status, _, slash_body = await request(
        app,
        "/dashboard/api/configuration/targets/cc/opus-consult-reasoning",
        headers=(("Host", "127.0.0.1"),),
    )
    assert slash_status == 200
    assert json.loads(slash_body)["target"]["id"] == "cc/opus-consult-reasoning"

    missing_status, _, missing_body = await request(
        app,
        "/dashboard/api/configuration/targets/nonexistent",
        headers=(("Host", "127.0.0.1"),),
    )
    assert missing_status == 404
    assert json.loads(missing_body)["code"] == "not_found"

    remote_status, _, _ = await request(
        app,
        "/dashboard/api/configuration/targets/primary",
        headers=(("Host", "127.0.0.1"),),
        client_host="192.0.2.1",
    )
    assert remote_status == 403


@pytest.mark.asyncio
async def test_configuration_target_update_and_delete_accept_slash_id(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(
        app,
        "/dashboard/api/configuration/targets",
        headers=(("Host", "127.0.0.1"),),
    )
    revision = json.loads(list_body)["revision"]
    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{revision}"'),
    )
    target_id = "cc/opus-consult-reasoning"
    path = f"/dashboard/api/configuration/targets/{target_id}"
    update_body = json.dumps(
        {"id": target_id, "backend": "claude", "model": "claude-opus-5", "reasoning": "max"}
    ).encode()

    update_status, _, update_response = await request(
        app,
        path,
        method="PUT",
        body=update_body,
        headers=headers,
    )
    assert update_status == 200
    update_payload = json.loads(update_response)
    assert update_payload["target"]["reasoning"] == "max"

    delete_headers = (*headers[:-1], ("If-Match", f'"{update_payload["revision"]}"'))
    delete_status, _, delete_response = await request(
        app,
        path,
        method="DELETE",
        headers=delete_headers,
    )
    assert delete_status == 200
    assert json.loads(delete_response)["deleted"] == target_id


@pytest.mark.asyncio
async def test_configuration_target_mutations_require_security_headers(active_runtime) -> None:
    app = create_application()
    endpoints = [
        ("POST", "/dashboard/api/configuration/targets", json.dumps({"id": "t1", "backend": "codex"}).encode()),
        ("PUT", "/dashboard/api/configuration/targets/primary", json.dumps({"id": "primary", "backend": "codex"}).encode()),
        ("DELETE", "/dashboard/api/configuration/targets/primary", b""),
    ]
    for method, path, body in endpoints:
        st, _, bd = await request(
            app, path, method=method, body=body,
            headers=(("Host", "127.0.0.1"), ("Origin", "http://127.0.0.1"), ("X-OpenMCP-CSRF", "test-token"), ("If-Match", '"123"')),
            client_host="192.0.2.1",
        )
        assert st == 403
        assert json.loads(bd)["code"] == "forbidden"

        st, _, bd = await request(
            app, path, method=method, body=body,
            headers=(("Host", "127.0.0.1"), ("Origin", "http://evil.com"), ("X-OpenMCP-CSRF", "test-token"), ("If-Match", '"123"')),
        )
        assert st == 403
        assert json.loads(bd)["code"] == "forbidden"

        st, _, bd = await request(
            app, path, method=method, body=body,
            headers=(("Host", "127.0.0.1"), ("Origin", "http://127.0.0.1"), ("If-Match", '"123"')),
        )
        assert st == 403
        assert json.loads(bd)["code"] == "forbidden"

        st, _, bd = await request(
            app, path, method=method, body=body,
            headers=(("Host", "127.0.0.1"), ("Origin", "http://127.0.0.1"), ("X-OpenMCP-CSRF", "test-token")),
        )
        assert st == 428
        assert json.loads(bd)["code"] == "revision_required"


@pytest.mark.asyncio
async def test_configuration_target_create_route(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(app, "/dashboard/api/configuration/targets", headers=(("Host", "127.0.0.1"),))
    rev = json.loads(list_body)["revision"]

    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )

    data = {
        "id": "tertiary",
        "backend": "codex",
        "backend_profile": "balanced",
        "args": ["--arg1"],
        "max_concurrency": 2,
    }
    status, res_headers, body = await request(
        app, "/dashboard/api/configuration/targets", method="POST", body=json.dumps(data).encode(), headers=headers
    )
    assert status == 200
    assert res_headers[b"cache-control"] == b"no-store"
    assert b"etag" in res_headers
    payload = json.loads(body)
    assert payload["target"]["id"] == "tertiary"
    assert payload["target"]["backend_profile"] == "balanced"
    new_rev = payload["revision"]

    dup_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{new_rev}"'),
    )
    dup_status, _, dup_body = await request(
        app, "/dashboard/api/configuration/targets", method="POST", body=json.dumps(data).encode(), headers=dup_headers
    )
    assert dup_status == 422
    assert json.loads(dup_body)["code"] == "configuration_invalid"

    bad_data = {
        "id": "extra_field_t",
        "backend": "codex",
        "unknown_extra": "rejected",
    }
    bad_status, _, bad_body = await request(
        app, "/dashboard/api/configuration/targets", method="POST", body=json.dumps(bad_data).encode(), headers=dup_headers
    )
    assert bad_status == 422
    assert json.loads(bad_body)["code"] == "configuration_invalid"

    stale_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", '"stale-revision"'),
    )
    fresh_data = {"id": "fresh", "backend": "codex"}
    stale_status, _, stale_body = await request(
        app, "/dashboard/api/configuration/targets", method="POST", body=json.dumps(fresh_data).encode(), headers=stale_headers
    )
    assert stale_status == 409
    stale_payload = json.loads(stale_body)
    assert stale_payload["code"] == "configuration_conflict"
    assert stale_payload["current"] == new_rev


@pytest.mark.asyncio
async def test_configuration_target_update_route(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(app, "/dashboard/api/configuration/targets", headers=(("Host", "127.0.0.1"),))
    rev = json.loads(list_body)["revision"]

    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )

    update_data = {
        "id": "primary",
        "backend": "codex",
        "model": "gpt-4o",
        "backend_profile": "balanced",
        "args": ["--updated"],
        "max_concurrency": 5,
    }
    status, res_headers, body = await request(
        app, "/dashboard/api/configuration/targets/primary", method="PUT", body=json.dumps(update_data).encode(), headers=headers
    )
    assert status == 200
    assert res_headers[b"cache-control"] == b"no-store"
    payload = json.loads(body)
    assert payload["target"]["model"] == "gpt-4o"
    assert payload["target"]["max_concurrency"] == 5
    new_rev = payload["revision"]

    rename_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{new_rev}"'),
    )
    rename_data = dict(update_data, id="renamed")
    ren_status, _, ren_body = await request(
        app, "/dashboard/api/configuration/targets/primary", method="PUT", body=json.dumps(rename_data).encode(), headers=rename_headers
    )
    assert ren_status == 422
    assert json.loads(ren_body)["code"] == "configuration_invalid"

    missing_data = {"id": "missing", "backend": "codex"}
    mis_status, _, mis_body = await request(
        app, "/dashboard/api/configuration/targets/missing", method="PUT", body=json.dumps(missing_data).encode(), headers=rename_headers
    )
    assert mis_status == 404
    assert json.loads(mis_body)["code"] == "not_found"

    stale_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )
    stale_status, _, stale_body = await request(
        app, "/dashboard/api/configuration/targets/primary", method="PUT", body=json.dumps(update_data).encode(), headers=stale_headers
    )
    assert stale_status == 409
    assert json.loads(stale_body)["code"] == "configuration_conflict"


@pytest.mark.asyncio
async def test_configuration_target_delete_route(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(app, "/dashboard/api/configuration/targets", headers=(("Host", "127.0.0.1"),))
    rev = json.loads(list_body)["revision"]

    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )
    create_status, _, create_body = await request(
        app, "/dashboard/api/configuration/targets", method="POST",
        body=json.dumps({"id": "to_delete", "backend": "pi"}).encode(),
        headers=headers,
    )
    assert create_status == 200
    rev2 = json.loads(create_body)["revision"]

    del_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev2}"'),
    )
    del_status, del_headers_res, del_body = await request(
        app, "/dashboard/api/configuration/targets/to_delete", method="DELETE", headers=del_headers
    )
    assert del_status == 200
    assert del_headers_res[b"cache-control"] == b"no-store"
    assert json.loads(del_body)["deleted"] == "to_delete"
    rev3 = json.loads(del_body)["revision"]

    ref_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev3}"'),
    )
    ref_status, _, ref_body = await request(
        app, "/dashboard/api/configuration/targets/primary", method="DELETE", headers=ref_headers
    )
    assert ref_status == 409
    ref_payload = json.loads(ref_body)
    assert ref_payload["code"] == "referenced"
    assert "references" in ref_payload
    assert len(ref_payload["references"]) > 0

    mis_status, _, mis_body = await request(
        app, "/dashboard/api/configuration/targets/missing", method="DELETE", headers=ref_headers
    )
    assert mis_status == 404
    assert json.loads(mis_body)["code"] == "not_found"


@pytest.mark.asyncio
async def test_configuration_target_error_redaction(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(app, "/dashboard/api/configuration/targets", headers=(("Host", "127.0.0.1"),))
    rev = json.loads(list_body)["revision"]

    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )

    bad_data = {
        "id": "secret_target",
        "backend": "codex",
        "system_prompt": "SUPER_SECRET_OPERATOR_PROMPT_XYZ",
        "args": ["--"],
    }
    status, _, body = await request(
        app, "/dashboard/api/configuration/targets", method="POST", body=json.dumps(bad_data).encode(), headers=headers
    )
    assert status == 422
    payload = json.loads(body)
    assert payload["code"] == "configuration_invalid"
    assert "SUPER_SECRET_OPERATOR_PROMPT_XYZ" not in body.decode("utf-8")
    assert payload["error"] == "Invalid configuration"


@pytest.mark.asyncio
async def test_configuration_profiles_read_and_security(active_runtime) -> None:
    app = create_application()

    # Non-loopback host rejected with 403
    status, _, _ = await request(
        app, "/dashboard/api/configuration/profiles", headers=(("Host", "attacker.com"),)
    )
    assert status == 403

    # Non-loopback client rejected with 403
    status, _, _ = await request(
        app,
        "/dashboard/api/configuration/profiles",
        headers=(("Host", "127.0.0.1"),),
        client_host="192.168.1.50",
    )
    assert status == 403

    # Loopback read succeeds
    status, headers, body = await request(
        app, "/dashboard/api/configuration/profiles", headers=(("Host", "127.0.0.1"),)
    )
    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    assert b"etag" in headers
    data = json.loads(body)
    assert data["default_profile"] == "balanced"
    assert "primary" in data["available_targets"]
    assert len(data["profiles"]) == 1
    prof = data["profiles"][0]
    assert prof["id"] == "balanced"
    assert prof["declared"]["implement"]["targets"] == ["primary"]
    assert prof["effective"]["implement"]["targets"] == ["primary"]
    assert prof["sources"]["implement"] == "declared"

    # Single profile get
    status, headers, body = await request(
        app, "/dashboard/api/configuration/profiles/balanced", headers=(("Host", "127.0.0.1"),)
    )
    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    single = json.loads(body)
    assert single["profile"]["id"] == "balanced"

    # Missing profile get
    status, _, body = await request(
        app, "/dashboard/api/configuration/profiles/missing", headers=(("Host", "127.0.0.1"),)
    )
    assert status == 404
    assert json.loads(body)["code"] == "not_found"


@pytest.mark.asyncio
async def test_configuration_profiles_crud_and_references(active_runtime) -> None:
    app = create_application()
    _, _, list_body = await request(
        app, "/dashboard/api/configuration/profiles", headers=(("Host", "127.0.0.1"),)
    )
    rev = json.loads(list_body)["revision"]

    # CSRF check
    bad_csrf_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "wrong-token"),
        ("If-Match", f'"{rev}"'),
    )
    status, _, _ = await request(
        app,
        "/dashboard/api/configuration/profiles",
        method="POST",
        body=json.dumps({"id": "p1"}).encode(),
        headers=bad_csrf_headers,
    )
    assert status == 403

    # If-Match missing check
    no_match_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
    )
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles",
        method="POST",
        body=json.dumps({"id": "p1"}).encode(),
        headers=no_match_headers,
    )
    assert status == 428
    assert json.loads(body)["code"] == "revision_required"

    # If-Match stale check
    stale_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", '"stale-rev"'),
    )
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles",
        method="POST",
        body=json.dumps({"id": "p1"}).encode(),
        headers=stale_headers,
    )
    assert status == 409
    assert json.loads(body)["code"] == "configuration_conflict"

    # Create profile "quality" extending "balanced"
    headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )
    payload = {
        "id": "quality",
        "extends": "balanced",
        "implement": {
            "targets": ["fallback", "primary"],
            "max_attempts": 2,
            "timeout_s": 30,
        },
    }
    status, res_headers, body = await request(
        app,
        "/dashboard/api/configuration/profiles",
        method="POST",
        body=json.dumps(payload).encode(),
        headers=headers,
    )
    assert status == 200
    assert res_headers[b"cache-control"] == b"no-store"
    res_data = json.loads(body)
    new_rev = res_data["revision"]
    q_prof = res_data["profile"]
    assert q_prof["id"] == "quality"
    assert q_prof["declared"]["implement"]["targets"] == ["fallback", "primary"]
    assert q_prof["declared"]["implement"]["timeout_s"] == 30
    assert q_prof["declared"]["implement"]["max_attempts"] == 2
    # Undeclared workflows appear as null in declared
    assert q_prof["declared"]["review"] is None
    assert q_prof["declared"]["consult"] is None
    assert q_prof["declared"]["other"] is None
    # Inherited and effective policies
    assert q_prof["inherited"]["review"]["targets"] == ["primary"]
    assert q_prof["effective"]["review"]["targets"] == ["primary"]
    assert q_prof["sources"]["review"] == "balanced"
    assert q_prof["sources"]["implement"] == "declared"

    # Update: rename rejection
    update_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{new_rev}"'),
    )
    rename_data = dict(payload, id="renamed")
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/quality",
        method="PUT",
        body=json.dumps(rename_data).encode(),
        headers=update_headers,
    )
    assert status == 422
    assert json.loads(body)["code"] == "configuration_invalid"

    # Update: valid update adding review workflow
    valid_update = {
        "id": "quality",
        "extends": "balanced",
        "implement": {
            "targets": ["fallback", "primary"],
            "max_attempts": 2,
            "timeout_s": 30,
        },
        "review": {
            "targets": ["primary"],
        },
    }
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/quality",
        method="PUT",
        body=json.dumps(valid_update).encode(),
        headers=update_headers,
    )
    assert status == 200
    updated_rev = json.loads(body)["revision"]

    # Delete blocked by default_profile: deleting balanced
    del_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{updated_rev}"'),
    )
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/balanced",
        method="DELETE",
        headers=del_headers,
    )
    assert status == 409
    ref_payload = json.loads(body)
    assert ref_payload["code"] == "referenced"
    assert any(ref["relationship"] == "default_profile" for ref in ref_payload["references"])

    # Create child extending quality to verify extends blocking
    child_payload = {
        "id": "child",
        "extends": "quality",
    }
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles",
        method="POST",
        body=json.dumps(child_payload).encode(),
        headers=del_headers,
    )
    assert status == 200
    rev_after_child = json.loads(body)["revision"]

    # Delete quality blocked by child extending it
    del_q_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev_after_child}"'),
    )
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/quality",
        method="DELETE",
        headers=del_q_headers,
    )
    assert status == 409
    ref_payload = json.loads(body)
    assert ref_payload["code"] == "referenced"
    assert any(ref["profile_id"] == "child" and ref["relationship"] == "extends" for ref in ref_payload["references"])

    # Delete child
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/child",
        method="DELETE",
        headers=del_q_headers,
    )
    assert status == 200
    rev_after_child_del = json.loads(body)["revision"]

    # Delete quality succeeds now
    del_q2_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev_after_child_del}"'),
    )
    status, _, body = await request(
        app,
        "/dashboard/api/configuration/profiles/quality",
        method="DELETE",
        headers=del_q2_headers,
    )
    assert status == 200
    assert json.loads(body)["deleted"] == "quality"


@pytest.mark.asyncio
async def test_project_profile_override_routes_crud_and_fallback(active_runtime) -> None:
    app = create_application()
    project_id = active_runtime.database.projects()[0].id
    url_base = f"/dashboard/api/projects/{project_id}/profile-overrides"

    # Security: non-loopback host rejected
    status, _, _ = await request(app, url_base, headers=(("Host", "attacker.com"),))
    assert status == 403

    # Unknown project rejected
    status, _, body = await request(
        app,
        "/dashboard/api/projects/unknown-proj/profile-overrides",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 404

    # Initial list before any project config file exists
    status, headers, body = await request(app, url_base, headers=(("Host", "127.0.0.1"),))
    assert status == 200
    assert headers[b"cache-control"] == b"no-store"
    list_data = json.loads(body)
    assert list_data["overrides"] == []
    assert list_data["global_default_profile"] == "balanced"
    assert list_data["project_default_profile"] == "balanced"
    rev = list_data["revision"]

    # Create override for "balanced" - creating minimal project file on demand
    create_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev}"'),
    )
    override_payload = {
        "id": "balanced",
        "extends": "balanced",
        "implement": {"targets": ["fallback"]},
    }
    status, _, body = await request(
        app,
        url_base,
        method="POST",
        body=json.dumps(override_payload).encode(),
        headers=create_headers,
    )
    assert status == 200
    created_data = json.loads(body)
    rev2 = created_data["revision"]
    created_ov = created_data["override"]
    assert created_ov["id"] == "balanced"
    assert created_ov["declared"]["implement"]["targets"] == ["fallback"]
    assert created_ov["effective"]["implement"]["targets"] == ["fallback"]
    assert created_ov["effective"]["review"]["targets"] == ["primary"]
    assert created_ov["sources"]["review"] == "global"

    # Single override GET
    status, _, body = await request(
        app,
        f"{url_base}/balanced",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 200
    assert json.loads(body)["override"]["id"] == "balanced"

    # Update override
    update_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev2}"'),
    )
    update_payload = {
        "id": "balanced",
        "extends": "balanced",
        "implement": {"targets": ["fallback"]},
        "review": {"targets": ["fallback"]},
    }
    status, _, body = await request(
        app,
        f"{url_base}/balanced",
        method="PUT",
        body=json.dumps(update_payload).encode(),
        headers=update_headers,
    )
    assert status == 200
    rev3 = json.loads(body)["revision"]

    # DELETE override - returns resulting effective global fallback!
    del_headers = (
        ("Host", "127.0.0.1"),
        ("Origin", "http://127.0.0.1"),
        ("X-OpenMCP-CSRF", "test-token"),
        ("If-Match", f'"{rev3}"'),
    )
    status, del_h, body = await request(
        app,
        f"{url_base}/balanced",
        method="DELETE",
        headers=del_headers,
    )
    assert status == 200
    del_data = json.loads(body)
    assert del_data["deleted"] == "balanced"
    fallback = del_data["fallback"]
    assert fallback is not None
    assert fallback["id"] == "balanced"
    assert fallback["effective"]["implement"]["targets"] == ["primary"]
    assert fallback["effective"]["review"]["targets"] == ["primary"]

    # Existing runtime read endpoints remain compatible
    status, _, body = await request(
        app,
        "/dashboard/api/profiles",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 200
    rt_profiles = json.loads(body)
    assert rt_profiles["default"] == "balanced"
    assert "balanced" in rt_profiles["available"]

    status, _, body = await request(
        app,
        f"/dashboard/api/projects/{project_id}/configuration",
        headers=(("Host", "127.0.0.1"),),
    )
    assert status == 200


@pytest.mark.asyncio
async def test_project_profile_override_conflict_and_validation(active_runtime) -> None:
    app = create_application()
    project_id = active_runtime.database.projects()[0].id
    url_base = f"/dashboard/api/projects/{project_id}/profile-overrides"

    # 1. Missing If-Match revision returns 428
    status, _, body = await request(
        app,
        url_base,
        method="POST",
        body=json.dumps({"id": "custom", "implement": {"targets": ["fallback"]}}).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-OpenMCP-CSRF", "test-token"),
        ),
    )
    assert status == 428
    assert json.loads(body)["code"] == "revision_required"

    # 2. Creating with non-matching revision when file does not exist returns 409 conflict
    status, _, body = await request(
        app,
        url_base,
        method="POST",
        body=json.dumps({"id": "custom", "implement": {"targets": ["fallback"]}}).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-OpenMCP-CSRF", "test-token"),
            ("If-Match", '"non-existent-rev"'),
        ),
    )
    assert status == 409
    assert json.loads(body)["code"] == "configuration_conflict"

    # 3. Validation: empty profile id returns 422
    status, _, body = await request(
        app,
        url_base,
        method="POST",
        body=json.dumps({"id": "   ", "implement": {"targets": ["fallback"]}}).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-OpenMCP-CSRF", "test-token"),
            ("If-Match", '""'),
        ),
    )
    assert status == 422
    assert json.loads(body)["code"] == "configuration_invalid"

    # 4. Successful creation on missing file with empty If-Match
    status, _, body = await request(
        app,
        url_base,
        method="POST",
        body=json.dumps({
            "id": "dev-profile",
            "extends": "balanced",
            "implement": {"targets": ["fallback"]},
        }).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-OpenMCP-CSRF", "test-token"),
            ("If-Match", '""'),
        ),
    )
    assert status == 200
    created = json.loads(body)
    new_rev = created["revision"]
    assert created["override"]["id"] == "dev-profile"

    # 5. Stale revision update returns 409 with current revision
    status, _, body = await request(
        app,
        f"{url_base}/dev-profile",
        method="PUT",
        body=json.dumps({
            "id": "dev-profile",
            "extends": "balanced",
            "implement": {"targets": ["primary"]},
        }).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-OpenMCP-CSRF", "test-token"),
            ("If-Match", '"stale-revision-value"'),
        ),
    )
    assert status == 409
    conflict_err = json.loads(body)
    assert conflict_err["code"] == "configuration_conflict"
    assert conflict_err["current"] == new_rev

    # 6. Conflict recovery: update with correct current revision succeeds
    status, _, body = await request(
        app,
        f"{url_base}/dev-profile",
        method="PUT",
        body=json.dumps({
            "id": "dev-profile",
            "extends": "balanced",
            "implement": {"targets": ["primary"]},
        }).encode(),
        headers=(
            ("Host", "127.0.0.1"),
            ("Origin", "http://127.0.0.1"),
            ("X-OpenMCP-CSRF", "test-token"),
            ("If-Match", f'"{new_rev}"'),
        ),
    )
    assert status == 200
    assert json.loads(body)["override"]["effective"]["implement"]["targets"] == ["primary"]
