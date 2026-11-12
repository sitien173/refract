from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from refract.config import load_config
from refract.runtime import OrchestrationError, Runtime
from refract.planning import execution_plan_data, resolve_execution_plan, target_execution_key
from tests.orchestration_helpers import config as make_config, git, register_project


def test_runtime_rejects_removed_marked_target_without_echoing_identifier(tmp_path) -> None:
    base = make_config(tmp_path / "home")
    target = replace(base.targets[0], env={"LOCAL": "value"})
    runtime = Runtime(replace(base, targets=(target,)))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    runtime._catalog = replace(runtime.catalog, targets=())
    try:
        with pytest.raises(ValueError, match="Unknown target") as error:
            runtime._resolve_target_environment(project, target.id)
        assert target.id not in str(error.value)
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_environment_session_revision_is_opaque_and_runtime_scoped(tmp_path) -> None:
    base = make_config(tmp_path / "home")
    target = replace(base.targets[0], env={"SECRET": "SYNTHETIC_REVISION_SECRET"})
    catalog = replace(base, targets=(target,))
    root = tmp_path / "project"
    root.mkdir()
    first_runtime = Runtime(catalog)
    project = register_project(first_runtime, str(root))
    try:
        _, first = first_runtime._resolve_target_environment(project, target.id)
        _, repeated = first_runtime._resolve_target_environment(project, target.id)
        assert first == repeated
    finally:
        import asyncio
        asyncio.run(first_runtime.close())

    second_runtime = Runtime(catalog)
    try:
        same_project = second_runtime.database.project(project.id)
        assert same_project is not None
        _, restarted = second_runtime._resolve_target_environment(same_project, target.id)
        assert restarted != first
    finally:
        import asyncio
        asyncio.run(second_runtime.close())


def test_capacity_only_global_edits_preserve_environment_session_revision(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('''[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "primary"\nbackend = "codex"\nenv = { ENDPOINT = "synthetic-one" }\n\n[profiles.balanced]\nimplement = "primary"\nreview = "primary"\nconsult = "primary"\n''', encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    try:
        env_initial, revision_initial = runtime._resolve_target_environment(project, "primary")
        assert env_initial == {"ENDPOINT": "synthetic-one"}
        for context_window in (200000, 250000, None):
            current = config_path.read_text(encoding="utf-8")
            lines = [line for line in current.splitlines() if not line.startswith("context_window =")]
            target_start = lines.index('id = "primary"')
            if context_window is not None:
                lines.insert(target_start + 1, f"context_window = {context_window}")
            config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            runtime.publish_configuration()
            env_values, revision = runtime._resolve_target_environment(project, "primary")
            assert env_values == env_initial
            assert revision == revision_initial

        changed = config_path.read_text(encoding="utf-8").replace('ENDPOINT = "synthetic-one"', 'ENDPOINT = "synthetic-two"')
        config_path.write_text(changed, encoding="utf-8")
        runtime.publish_configuration()
        changed_env, changed_revision = runtime._resolve_target_environment(project, "primary")
        assert changed_env == {"ENDPOINT": "synthetic-two"}
        assert changed_revision != revision_initial
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_runtime_resolves_current_project_environment_by_stored_target_id(tmp_path) -> None:
    base = make_config(tmp_path / "home")
    target = replace(base.targets[0], env={"ENDPOINT": "global"}, args=("--safe",), max_concurrency=3)
    catalog = replace(base, targets=(target,))
    root = tmp_path / "project"
    root.mkdir()
    runtime = Runtime(catalog)
    project = register_project(runtime, str(root))
    project_config = root / ".refract" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text(f'[[targets]]\nid = "{target.id}"\nenv = {{ ENDPOINT = "project-one" }}\n', encoding="utf-8")
    try:
        first, first_revision = runtime._resolve_target_environment(project, target.id)
        stored_plan = resolve_execution_plan("implement", catalog, "balanced")
        project_config.write_text(f'[[targets]]\nid = "{target.id}"\nenv = {{ ENDPOINT = "project-two" }}\n', encoding="utf-8")
        second, second_revision = runtime._resolve_target_environment(project, target.id)
        assert first == {"ENDPOINT": "project-one"}
        assert second == {"ENDPOINT": "project-two"}
        assert first_revision != second_revision
        other_root = tmp_path / "other-project"
        other_root.mkdir()
        other_project = register_project(runtime, str(other_root))
        other_config = other_root / ".refract" / "config.toml"
        other_config.parent.mkdir()
        other_config.write_text(f'[[targets]]\nid = "{target.id}"\nenv = {{ ENDPOINT = "isolated-project" }}\n', encoding="utf-8")
        other_values, other_revision = runtime._resolve_target_environment(other_project, target.id)
        assert other_values == {"ENDPOINT": "isolated-project"}
        assert other_revision != second_revision
        assert stored_plan.target(target.id).args == ("--safe",)
        assert stored_plan.target(target.id).max_concurrency == 3
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_resolve_target_environment_derives_revision_from_catalog_snapshot_not_subsequent_stat(tmp_path, monkeypatch) -> None:
    import refract.runtime as runtime_module

    base = make_config(tmp_path / "home")
    target = replace(base.targets[0], env={"ENDPOINT": "global"})
    catalog = replace(base, targets=(target,))
    root = tmp_path / "project"
    root.mkdir()
    runtime = Runtime(catalog)
    project = register_project(runtime, str(root))
    project_config = root / ".refract" / "config.toml"
    project_config.parent.mkdir()
    project_config.write_text(f'[[targets]]\nid = "{target.id}"\nenv = {{ ENDPOINT = "v1" }}\n', encoding="utf-8")
    try:
        original_resolve = runtime_module.resolve_target_environment
        edited = False

        def edit_during_resolution(cat, tgt):
            nonlocal edited
            res = original_resolve(cat, tgt)
            if not edited:
                edited = True
                # Simulate an external edit between catalog acquisition and revision generation
                project_config.write_text(f'[[targets]]\nid = "{target.id}"\nenv = {{ ENDPOINT = "v2" }}\n', encoding="utf-8")
            return res

        monkeypatch.setattr(runtime_module, "resolve_target_environment", edit_during_resolution)

        first_values, first_revision = runtime._resolve_target_environment(project, target.id)
        assert first_values == {"ENDPOINT": "v1"}

        second_values, second_revision = runtime._resolve_target_environment(project, target.id)
        assert second_values == {"ENDPOINT": "v2"}

        assert first_revision != second_revision
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_project_catalog_snapshot_retries_when_file_changes_during_load(tmp_path, monkeypatch) -> None:
    import refract.runtime as runtime_module

    base = make_config(tmp_path / "home")
    root = tmp_path / "project"
    root.mkdir()
    runtime = Runtime(base)
    old_identity = (1000, 100, 1)
    new_identity = (2000, 200, 2)
    identities = iter((old_identity, new_identity, new_identity, new_identity))
    loaded = []
    catalog = replace(base, targets=(replace(base.targets[0], env={"ENDPOINT": "current"}),))

    def file_identity(path):
        return next(identities)

    def load_project(root_path, base_catalog):
        loaded.append(base_catalog)
        return catalog

    monkeypatch.setattr(runtime_module, "_file_identity", file_identity)
    monkeypatch.setattr(runtime_module, "load_project_config", load_project)
    try:
        # A distinct base object forces the project-catalog cache miss that exposed
        # the pre-load identity race during a global configuration reload.
        result, revision = runtime._project_catalog_snapshot(root, replace(base))
        assert result is catalog
        assert len(loaded) == 2
        assert runtime._project_catalogs[root][0] == new_identity
        assert revision == runtime._project_catalogs[root][3]
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_project_catalog_snapshot_sees_same_size_rewrite_within_one_clock_tick(tmp_path, monkeypatch) -> None:
    import refract.runtime as runtime_module

    base = make_config(tmp_path / "home")
    target = replace(base.targets[0], env={"ENDPOINT": "global"})
    catalog = replace(base, targets=(target,))
    root = tmp_path / "project"
    root.mkdir()
    config_path = root / ".refract" / "config.toml"
    config_path.parent.mkdir()
    runtime = Runtime(catalog)
    # Windows file times tick about every 15 ms, so a quick same-size rewrite keeps its stat identity.
    monkeypatch.setattr(runtime_module, "_file_identity", lambda path: (1000, 100, 1))
    try:
        values = []
        revisions = []
        for endpoint in ("v1", "v2"):
            config_path.write_text(f'[[targets]]\nid = "{target.id}"\nenv = {{ ENDPOINT = "{endpoint}" }}\n', encoding="utf-8")
            snapshot, revision = runtime._project_catalog_snapshot(root, catalog)
            values.append(snapshot.targets[0].env)
            revisions.append(revision)
        assert values == [{"ENDPOINT": "v1"}, {"ENDPOINT": "v2"}]
        assert revisions[0] != revisions[1]
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_project_catalog_snapshot_fails_safely_after_continuous_file_churn(tmp_path, monkeypatch) -> None:
    import refract.runtime as runtime_module

    base = make_config(tmp_path / "home")
    root = tmp_path / "project"
    root.mkdir()
    runtime = Runtime(base)
    identities = iter((1000, 2000, 3000, 4000, 5000, 6000))
    loads = 0

    def file_identity(path):
        return (next(identities), 100, 1)

    def load_project(root_path, base_catalog):
        nonlocal loads
        loads += 1
        return replace(base_catalog, targets=(replace(base_catalog.targets[0], env={"TOKEN": "SYNTHETIC_SECRET"}),))

    monkeypatch.setattr(runtime_module, "_file_identity", file_identity)
    monkeypatch.setattr(runtime_module, "load_project_config", load_project)
    updated_base = replace(base)
    try:
        with pytest.raises(ValueError, match="Project configuration changed during loading") as error:
            runtime._project_catalog_snapshot(root, updated_base)
        assert loads == 3
        assert "SYNTHETIC_SECRET" not in str(error.value)
        assert root not in runtime._project_catalogs
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_resolve_target_environment_mocked_sequence_does_not_label_old_binding_with_new_identity(tmp_path, monkeypatch) -> None:
    import refract.runtime as runtime_module

    base = make_config(tmp_path / "home")
    target = base.targets[0]
    catalog_old = replace(base, targets=(replace(target, env={"ENDPOINT": "old"}),))
    catalog_new = replace(base, targets=(replace(target, env={"ENDPOINT": "new"}),))

    root = tmp_path / "project"
    root.mkdir()
    runtime = Runtime(base)
    project = register_project(runtime, str(root))

    old_ident = (1000, 100, 1)
    new_ident = (2000, 200, 2)
    file_identities = [old_ident, old_ident, new_ident, new_ident]
    catalog_loads = [catalog_old, catalog_new]

    def mock_file_identity(path):
        return file_identities.pop(0) if file_identities else new_ident

    def mock_load_project_config(root_path, base_catalog):
        return catalog_loads.pop(0)

    monkeypatch.setattr(runtime_module, "_file_identity", mock_file_identity)
    monkeypatch.setattr(runtime_module, "load_project_config", mock_load_project_config)

    try:
        first_values, first_revision = runtime._resolve_target_environment(project, target.id)
        second_values, second_revision = runtime._resolve_target_environment(project, target.id)

        assert first_values == {"ENDPOINT": "old"}
        assert second_values == {"ENDPOINT": "new"}
        assert first_revision != second_revision
    finally:
        import asyncio
        asyncio.run(runtime.close())


@pytest.mark.asyncio
async def test_retry_pins_target_and_submit_prechecks_all_open_targets(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('''[daemon]\ndefault_profile = "balanced"\nbreaker_base_cooldown_s = 7\n\n[[targets]]\nid = "a"\nbackend = "codex"\nenv = { A = "SYNTHETIC_MARKER" }\n\n[[targets]]\nid = "b"\nbackend = "claude"\n\n[profiles.balanced]\nconsult = ["a", "b"]\n''', encoding="utf-8")
    runtime = Runtime(load_config(path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    try:
        source = await runtime.submit(project.id, "consult", "hello")
        runtime.database.finish_job(source.job_id, "failed", target="a")
        first = await runtime.retry(source.job_id, target="b")
        stored = runtime.database.job_record(first.job_id)
        stored_plan = json.loads(stored["execution_plan_json"])
        assert stored_plan["selection"]["targets"] == ["b"]
        assert "environment_targets" not in stored_plan
        assert len(runtime.database.jobs(project.id)) == 2
        for target in plan.targets:
            runtime.database.record_target_failure(target_execution_key(target), immediate=True, base_cooldown_s=7)
        with pytest.raises(OrchestrationError) as raised:
            await runtime.submit(project.id, "consult", "no row")
        assert raised.value.code == "targets_unavailable"
        assert type(raised.value.retry_after_s) is int
        assert len(runtime.database.jobs(project.id)) == 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_context_overflow_projects_read_time_route_to_next_healthy_target(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "overflow-project"
    root.mkdir()
    project = register_project(runtime, str(root))
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    try:
        job_id = "overflow-route"
        runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="consult", profile="balanced", prompt="overflow", execution_plan_json=json.dumps(execution_plan_data(plan)), session=job_id)
        runtime.database.finish_job(job_id, "failed", target="a", failure_kind="context_overflow")
        view = runtime.database.job(job_id)
        result = runtime.live_routing(view)
        assert result["retry"]["next_target"] == "b"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_live_metadata_routes_after_failure_without_persisting_hint(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    try:
        for target_b_open in (False, True):
            job_id = "live-route-open" if target_b_open else "live-route-closed"
            runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="consult", profile="balanced", prompt="fail", execution_plan_json=json.dumps(execution_plan_data(plan)), session=job_id)
            runtime.database.finish_job(job_id, "failed", target="a", failure_kind="transient")
            if target_b_open:
                runtime.database._connection.execute("INSERT OR REPLACE INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2999-01-01T00:00:00+00:00', 60, '')", (target_execution_key(plan.targets[1]),))
            else:
                runtime.database.record_target_success(target_execution_key(plan.targets[1]))
            view = runtime.database.job(job_id)
            result = runtime.live_routing(view)
            assert result["retry"]["next_target"] == ("b" if not target_b_open else None)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_all_open_leaves_failed_job_untouched(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    job_id = "retry-open"
    runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="consult", profile="balanced", prompt="x", execution_plan_json=json.dumps(execution_plan_data(plan)), session="retry-open")
    runtime.database.record_job_target(job_id, "a")
    runtime.database.finish_job(job_id, "failed", target="a", failure_kind="transient")
    for target in plan.targets:
        runtime.database._connection.execute("INSERT OR REPLACE INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '2999-01-01T00:00:00+00:00', 60, '')", (target_execution_key(target),))
    runtime.database._connection.commit()
    prior = runtime.database.job_record(job_id)
    try:
        with pytest.raises(OrchestrationError) as raised:
            await runtime.retry(job_id)
        assert raised.value.code == "targets_unavailable"
        assert type(raised.value.retry_after_s) is int
        after = runtime.database.job_record(job_id)
        assert after["state"] == prior["state"] == "failed"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_retry_after_uses_reloaded_cooldown_for_held_probes(tmp_path) -> None:
    config_path = tmp_path / "config.toml"
    _two_target_config(config_path)
    content = config_path.read_text(encoding="utf-8").replace('default_profile = "balanced"', 'default_profile = "balanced"\nbreaker_base_cooldown_s = 7')
    config_path.write_text(content, encoding="utf-8")
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    plan = resolve_execution_plan("consult", runtime.catalog, "balanced")
    job_id = "retry-reloaded-cooldown"
    runtime.database.create_job(job_id=job_id, project_id=project.id, workflow="consult", profile="balanced", prompt="x", execution_plan_json=json.dumps(execution_plan_data(plan)), session=job_id)
    runtime.database.finish_job(job_id, "failed")
    changed = config_path.read_text(encoding="utf-8").replace("breaker_base_cooldown_s = 7", "breaker_base_cooldown_s = 23")
    config_path.write_text(changed, encoding="utf-8")
    runtime.publish_configuration()
    for target in plan.targets:
        runtime.database._connection.execute("INSERT OR REPLACE INTO target_health(target_id, consecutive_failures, circuit_open_until, cooldown_s, probe_job_id) VALUES (?, 1, '', 0, 'held-probe')", (target_execution_key(target),))
    runtime.database._connection.commit()
    try:
        with pytest.raises(OrchestrationError) as raised:
            await runtime.retry(job_id)
        assert raised.value.code == "targets_unavailable"
        assert raised.value.retry_after_s == 23
    finally:
        await runtime.close()


def _two_target_config(path) -> None:
    path.write_text('''[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "a"\nbackend = "codex"\n\n[[targets]]\nid = "b"\nbackend = "claude"\n\n[profiles.balanced]\nconsult = ["a", "b"]\nreview = ["a", "b"]\n\n[profiles.alternate]\nconsult = ["a", "b"]\nreview = ["a", "b"]\n''', encoding="utf-8")


def _config(path) -> None:
    path.write_text('''[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
''', encoding="utf-8")


@pytest.mark.asyncio
async def test_failed_reload_preserves_catalog_health_and_blocks_submission(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root))
    original = runtime.catalog
    original_revision = original.config_revision

    config_path.write_text("[daemon\ndefault_profile =", encoding="utf-8")
    with pytest.raises(OrchestrationError):
        await runtime.submit(project.id, "consult", "question")

    assert runtime.catalog is original
    health = runtime.config_health
    assert not health.valid
    assert health.last_known_good_revision == original_revision
    assert health.revision != original_revision
    with pytest.raises(OrchestrationError):
        await runtime.submit(project.id, "consult", "question")
    await runtime.close()


@pytest.mark.asyncio
async def test_configuration_error_does_not_expose_secret(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root))
    secret = "SUPER_SECRET_CONFIGURATION_VALUE"
    path.write_text(path.read_text(encoding="utf-8").rstrip() + f'\n[logging]\nlevel = "{secret}"\n', encoding="utf-8")

    with pytest.raises(OrchestrationError) as raised:
        await runtime.submit(project.id, "consult", "question")

    assert secret not in str(raised.value)
    assert secret not in runtime.config_health.latest_error
    await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_kind", ["profile", "workflow"])
async def test_configuration_identifiers_do_not_leak_from_errors(tmp_path, invalid_kind) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root))
    content = path.read_text(encoding="utf-8")
    if invalid_kind == "profile":
        content += '[profiles."SECRET_PROFILE"]\n'
    else:
        content = content.replace(
            'consult = "primary"', 'SECRET_WORKFLOW = "primary"'
        )
    path.write_text(content, encoding="utf-8")

    with pytest.raises(OrchestrationError) as raised:
        await runtime.submit(project.id, "consult", "question")

    assert "SECRET_" not in str(raised.value)
    assert "SECRET_" not in runtime.config_health.latest_error
    await runtime.close()


def test_initial_health_is_seeded(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    catalog = load_config(path)
    runtime = Runtime(catalog)
    health = runtime.config_health
    assert health.valid
    assert health.revision == hashlib.sha256(path.read_bytes()).hexdigest()
    assert health.last_known_good_revision == health.revision
    runtime.database.close()


# ---------------------------------------------------------------------------
# Configuration publication boundary (dashboard target-profile CRUD phase 1).
# ---------------------------------------------------------------------------


def test_publish_configuration_refreshes_catalog_and_executor(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    try:
        previous = runtime.catalog
        path.write_text(
            path.read_text(encoding="utf-8") + "\n# refreshed\n",
            encoding="utf-8",
        )
        runtime.publish_configuration()
        assert runtime.catalog is not previous
        assert runtime.target_executor.config is runtime.catalog
        health = runtime.config_health
        assert health.valid
        assert health.revision == hashlib.sha256(path.read_bytes()).hexdigest()
    finally:
        runtime.database.close()

def test_catalog_reload_after_manual_edit_refreshes_executor(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    try:
        path.write_text(path.read_text(encoding="utf-8") + "\n# manual edit\n", encoding="utf-8")
        runtime.publish_configuration()
        assert runtime.target_executor.config is runtime.catalog
        assert runtime.target_executor.config.config_revision == hashlib.sha256(path.read_bytes()).hexdigest()
    finally:
        runtime.database.close()

@pytest.mark.asyncio
async def test_catalog_cache_reuses_parses_and_invalidates_on_changes(tmp_path, monkeypatch) -> None:
    import refract.runtime as module

    path = tmp_path / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    counts = {"global": 0, "project": 0}
    global_loader = module.load_config
    project_loader = module.load_project_config

    def global_load(*args):
        counts["global"] += 1
        return global_loader(*args)

    def project_load(*args):
        counts["project"] += 1
        return project_loader(*args)

    monkeypatch.setattr(module, "load_config", global_load)
    monkeypatch.setattr(module, "load_project_config", project_load)
    try:
        first = runtime.catalog_for_project(project.id)
        assert runtime.catalog_for_project(project.id) is first
        await runtime.submit(project.id, "consult", "cached")
        assert counts == {"global": 1, "project": 1}
        path.write_text(path.read_text() + "\n# changed\n")
        second = runtime.catalog_for_project(project.id)
        assert second is not first
        assert counts == {"global": 2, "project": 2}
        local = root / ".refract" / "config.toml"
        local.parent.mkdir()
        local.write_text('[profiles.balanced]\nextends = "balanced"\n')
        third = runtime.catalog_for_project(project.id)
        assert third is not second
        assert runtime.catalog_for_project(project.id) is third
        local.unlink()
        assert runtime.catalog_for_project(project.id) is not third
        assert counts == {"global": 2, "project": 4}
        path.write_text("invalid TOML [")
        for _ in range(2):
            with pytest.raises(OrchestrationError):
                runtime.catalog_for_project(project.id)
        assert not runtime.config_health.valid
        _config(path)
        assert runtime.catalog_for_project(project.id)
        assert runtime.config_health.valid
    finally:
        await runtime.close()


def test_runtime_configuration_lock_is_reentrant(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    try:
        assert runtime._lock is not None
        # The lock is re-entrant so reloads inside a lock do not deadlock.
        with runtime._lock:
            runtime.publish_configuration()
            runtime.publish_configuration()
    finally:
        runtime.database.close()

@pytest.mark.asyncio
async def test_project_override_runtime_activation_and_plan_preservation(tmp_path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root))

    # Submit job 1 under initial configuration
    sub1 = await runtime.submit(project.id, "consult", "initial question")
    record1_before = runtime.database.job_record(sub1.job_id)
    assert record1_before is not None
    plan1_before = record1_before["execution_plan_json"]

    # Create project profile override without daemon restart
    override_path = project_root / ".refract" / "config.toml"
    override_path.parent.mkdir(parents=True, exist_ok=True)
    override_path.write_text(
        '[profiles.balanced]\nextends = "balanced"\nconsult = { targets = ["primary"], timeout_s = 99 }\n',
        encoding="utf-8",
    )

    # Runtime activation: project catalog immediately reflects the override
    proj_catalog = runtime.catalog_for_project_cached(project.id)
    assert proj_catalog.profiles["balanced"]["consult"].timeout_s == 99

    # Submit job 2 under updated override
    sub2 = await runtime.submit(project.id, "consult", "follow-up question")
    job2 = runtime.database.job(sub2.job_id)
    assert job2 is not None

    # Existing job 1 retains its original execution plan
    record1_after = runtime.database.job_record(sub1.job_id)
    assert record1_after is not None
    assert record1_after["execution_plan_json"] == plan1_before

    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_start_prunes_expired_terminal_transcripts_without_pruning_active_jobs(tmp_path) -> None:
    from datetime import datetime, timedelta, timezone

    home = tmp_path / "home"
    home.mkdir()
    path = home / "config.toml"
    _config(path)
    runtime = Runtime(load_config(path))
    project_root = tmp_path / "project"
    project_root.mkdir()
    project = register_project(runtime, str(project_root))

    # 1. Expired terminal job (10 days old)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    runtime.database.create_job(
        job_id="job-expired-term",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p1",
        execution_plan_json="{}",
        session="c1",
    )
    with runtime.database._connection:
        runtime.database._connection.execute(
            "UPDATE jobs SET state='succeeded', updated_at=? WHERE id='job-expired-term'",
            (old_ts,),
        )
    runtime.database.append_stream("job-expired-term", [{
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "old terminal transcript"},
    }])

    # 2. Recent terminal job (2 days old)
    recent_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    runtime.database.create_job(
        job_id="job-recent-term",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p2",
        execution_plan_json="{}",
        session="c2",
    )
    with runtime.database._connection:
        runtime.database._connection.execute(
            "UPDATE jobs SET state='succeeded', updated_at=? WHERE id='job-recent-term'",
            (recent_ts,),
        )
    runtime.database.append_stream("job-recent-term", [{
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "recent terminal transcript"},
    }])

    # 3. Active running job (10 days old) - should NOT be pruned despite being old
    runtime.database.create_job(
        job_id="job-old-running",
        project_id=project.id,
        workflow="consult",
        profile="balanced",
        prompt="p3",
        execution_plan_json="{}",
        session="c3",
    )
    with runtime.database._connection:
        runtime.database._connection.execute(
            "UPDATE jobs SET state='running', updated_at=? WHERE id='job-old-running'",
            (old_ts,),
        )
    runtime.database.append_stream("job-old-running", [{
        "kind": "assistant.text.delta",
        "entity_id": "msg-1",
        "data": {"text": "active running transcript"},
    }])

    # Verify initial stream data exists
    assert runtime.database.stream_path("job-expired-term").exists()
    assert runtime.database.stream_path("job-recent-term").exists()
    assert runtime.database.stream_path("job-old-running").exists()

    # Start runtime (triggers start retention cleanup)
    await runtime.start()

    # Expired terminal job is deleted with its stream file
    assert runtime.database.job("job-expired-term") is None
    assert not runtime.database.stream_path("job-expired-term").exists()

    # Recent terminal and active running transcripts are preserved
    assert runtime.database.stream_path("job-recent-term").exists()
    # Note: runtime.start() interrupts active jobs upon restart, changing running -> interrupted,
    # but the stream events of active jobs prior to start were not pruned by the retention step!
    assert runtime.database.stream_path("job-old-running").exists()

    # Recent and active job records remain intact
    assert runtime.database.job("job-recent-term") is not None
    assert runtime.database.job("job-old-running") is not None

    await runtime.close()


def test_resolve_project_rereads_concurrent_root_winner(tmp_path, monkeypatch) -> None:
    import sqlite3

    config_path = tmp_path / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "raced-root"
    root.mkdir()
    git(root, "init", "-q")
    original_upsert = runtime.database.upsert_project
    simulated_race = False

    def race_on_root(**kwargs):
        nonlocal simulated_race
        if kwargs["root"] == root.resolve().as_posix() and not simulated_race:
            simulated_race = True
            winner = original_upsert(project_id="concurrent-winner", root=kwargs["root"])
            raise sqlite3.IntegrityError("UNIQUE constraint failed: projects.root")
        return original_upsert(**kwargs)

    monkeypatch.setattr(runtime.database, "upsert_project", race_on_root)
    try:
        project = runtime.resolve_project(str(root))
        assert project.id == "concurrent-winner"
        assert runtime.database.project("concurrent-winner").root == root.resolve().as_posix()
    finally:
        runtime.database.close()

def test_resolve_project_returns_concurrent_canonical_winner(tmp_path, monkeypatch) -> None:
    from refract.database import Database

    config_path = tmp_path / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    other = Database(runtime.config.database_path)
    root = tmp_path / "real-race"
    root.mkdir()
    git(root, "init", "-q")
    original_projects = runtime.database.projects
    inserted = False

    def insert_winner_after_stale_read():
        nonlocal inserted
        rows = original_projects()
        if not inserted:
            inserted = True
            other.upsert_project(project_id="race-winner", root=root.resolve().as_posix())
        return rows

    monkeypatch.setattr(runtime.database, "projects", insert_winner_after_stale_read)
    try:
        resolved = runtime.resolve_project(str(root))
        stored = other.project("race-winner")
        assert resolved.id == "race-winner"
        assert stored is not None
        assert stored.root == root.resolve().as_posix()
    finally:
        other.close()
        runtime.database.close()


def test_target_execution_key_matches_literal_pre_change_fixture() -> None:
    from refract.config import RetryPolicy, TargetConfig
    from refract.planning import target_execution_key

    # Exact historical key fixture before Phase 1
    target_plain = TargetConfig(id="primary", backend="codex")
    assert target_execution_key(target_plain) == "primary:fcb7f648a676a587"

    target_with_args = TargetConfig(
        id="native-with-custom-args",
        backend="pi",
        args=("--verbose", "--system-prompt", "advisory only"),
    )
    assert target_execution_key(target_with_args) == "native-with-custom-args:d2edd4569fa44ac6"

    # Adding or modifying retry produces the EXACT same historical key
    target_with_retry = TargetConfig(id="primary", backend="codex", retry=RetryPolicy(2, ("rate_limit",), ()))
    assert target_execution_key(target_with_retry) == "primary:fcb7f648a676a587"

    target_with_other_retry = TargetConfig(id="primary", backend="codex", retry=RetryPolicy(3, (), ("overloaded",)))
    assert target_execution_key(target_with_other_retry) == "primary:fcb7f648a676a587"


def test_retry_only_configuration_changes_preserve_existing_sessions(tmp_path) -> None:
    from refract.planning import target_execution_key

    config_path = tmp_path / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    try:
        target_initial = runtime.catalog.targets[0]
        key_initial = target_execution_key(target_initial)
        runtime.database.store_session(
            project_id=project.id,
            session="ctx_1",
            workflow="implement",
            target_key=key_initial,
            backend_session_id="sess_historical_123",
        )
        assert runtime.database.session(project.id, "ctx_1", "implement", key_initial) == "sess_historical_123"

        # Reconfigure target with an inline retry policy
        config_path.write_text(
            """[daemon]
default_profile = "balanced"

[[targets]]
id = "primary"
backend = "codex"
retry = { attempts = 2, codes = ["rate_limit"] }

[profiles.balanced]
implement = "primary"
review = "primary"
consult = "primary"
""",
            encoding="utf-8",
        )
        runtime.publish_configuration()
        target_reconfigured = runtime.catalog.targets[0]
        key_reconfigured = target_execution_key(target_reconfigured)
        assert key_reconfigured == key_initial
        assert runtime.database.session(project.id, "ctx_1", "implement", key_reconfigured) == "sess_historical_123"
    finally:
        runtime.database.close()


@pytest.mark.asyncio
async def test_manual_retry_receives_fresh_policy_budget_on_new_job(tmp_path) -> None:
    from dataclasses import replace
    from refract.config import RetryPolicy, TargetConfig, TargetSelection
    from refract.drivers import DriverResult
    from tests.orchestration_helpers import FakeDrivers, config, repository

    root = repository(tmp_path)
    base = config(tmp_path / "home")

    policy = RetryPolicy(1, ("rate_limit",), ())
    catalog = replace(
        base,
        targets=(TargetConfig(id="primary", backend="codex", retry=policy),),
        profiles={"balanced": {"implement": TargetSelection(("primary",)), "review": TargetSelection(("primary",)), "consult": TargetSelection(("primary",))}},
    )

    class ManualRetrySequenceDrivers(FakeDrivers):
        def __init__(self):
            super().__init__()
            self.invocations = []

        async def supports_structured_streaming(self, target, cancel_event=None):
            return True

        async def execute(self, *, target, **kwargs):
            self.invocations.append(len(self.invocations) + 1)
            attempt_idx = len(self.invocations)
            if attempt_idx in {1, 2, 3}:
                return DriverResult("RETRYABLE", "", "", f"transient {attempt_idx}", "rate_limit")
            return DriverResult("SUCCESS", "sess-manual", "manual recovery done", "", "")

    drivers = ManualRetrySequenceDrivers()
    runtime = Runtime(catalog)
    runtime.drivers = drivers
    await runtime.start()
    try:
        project = register_project(runtime, str(root))
        sub = await runtime.submit(project.id, "implement", "manual retry budget test")
        job = await runtime.wait(sub.job_id, 10)
        assert job.state == "failed"
        assert len(drivers.invocations) == 2

        # Explicit manual retry gets fresh policy budget
        retried = await runtime.retry(job.id, target="primary")
        job2 = await runtime.wait(retried.job_id, 10)
        assert job2.state == "succeeded"
        assert len(drivers.invocations) == 4
    finally:
        await runtime.close()


def test_live_routing_dynamic_routing_and_context_overflow(tmp_path) -> None:
    from refract.models import JobView, JobResult

    config_path = tmp_path / "config.toml"
    _config(config_path)
    runtime = Runtime(load_config(config_path))
    try:
        # 1. Success job
        job_succ = JobView(
            id="j1", project_id="p1", workflow="consult", profile="balanced",
            state="succeeded", session="c1", created_at="now", updated_at="now",
            result=JobResult(model="m1", duration_ms=10),
        )
        live_succ = runtime.live_routing(job_succ)
        assert set(live_succ) == {"failure_kind", "retry"}
        assert live_succ["retry"] == {"next_target": None}

        # 2. Context overflow job
        job_overflow = JobView(
            id="j2", project_id="p1", workflow="consult", profile="balanced",
            state="failed", session="c1", created_at="now", updated_at="now",
            result=JobResult(failure_kind="context_overflow"),
        )
        live_overflow = runtime.live_routing(job_overflow)
        assert set(live_overflow) == {"failure_kind", "retry"}
        assert live_overflow["failure_kind"] == "context_overflow"
        assert live_overflow["retry"] == {"next_target": None}
    finally:
        runtime.database.close()










@pytest.mark.asyncio
async def test_runtime_recovery_string_names_config_toml(tmp_path, monkeypatch) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "t"\nbackend = "codex"\n\n[profiles.balanced]\nconsult = "t"\n',
        encoding="utf-8",
    )
    runtime = Runtime(load_config(path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    try:
        from unittest.mock import MagicMock
        monkeypatch.setattr("refract.runtime.resolve_execution_plan", MagicMock(side_effect=ValueError("malformed config")))
        with pytest.raises(OrchestrationError) as raised:
            await runtime.submit(project.id, "consult", "test prompt")
        assert raised.value.code == "config_invalid"
        assert raised.value.next_action == "Fix the project configuration in .refract/config.toml."
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_job_submission_succeeds_without_runtime_mutations(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[daemon]\ndefault_profile = "balanced"\n\n[[targets]]\nid = "t"\nbackend = "codex"\n\n[profiles.balanced]\nconsult = "t"\n',
        encoding="utf-8",
    )
    runtime = Runtime(load_config(path))
    root = tmp_path / "project"
    root.mkdir()
    project = register_project(runtime, str(root))
    try:
        assert not hasattr(runtime, "mutations")
        result = await runtime.submit(project.id, "consult", "test prompt")
        assert result.job_id
        stored = runtime.database.job_record(result.job_id)
        assert stored is not None
        assert stored["state"] == "queued"
    finally:
        await runtime.close()



def _admission_runtime(tmp_path):
    runtime = Runtime(make_config(tmp_path / "home"))
    root = tmp_path / "project"
    root.mkdir()
    return runtime, register_project(runtime, str(root))


@pytest.mark.parametrize(
    ("closing", "known_project", "workflow", "message", "code", "next_action"),
    [
        pytest.param(True, False, "implement", "The daemon is stopping.", "daemon_stopping", "Wait, then call submit again.", id="closing-wins-over-unknown-project"),
        pytest.param(False, False, "implement", "Project is not registered.", "unknown_project", "Call submit with a path inside a Git repository.", id="unknown-project"),
        pytest.param(False, False, "no-such-workflow", "Project is not registered.", "unknown_project", "Call submit with a path inside a Git repository.", id="unknown-project-wins-over-invalid-workflow"),
        pytest.param(False, True, "no-such-workflow", "Unknown workflow .no-such-workflow.", "invalid_request", "Correct the workflow or prompt and call submit again.", id="invalid-workflow"),
    ],
)
def test_admit_submission_rejects_before_planning(tmp_path, closing, known_project, workflow, message, code, next_action) -> None:
    runtime, project = _admission_runtime(tmp_path)
    runtime._closing = closing
    try:
        with pytest.raises(OrchestrationError, match=message) as raised:
            runtime._admit_submission("job-1", project.id if known_project else "missing", workflow, "do it")
        assert (raised.value.code, raised.value.next_action) == (code, next_action)
        assert runtime.database.job("job-1") is None
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_admit_submission_creates_job_with_defaults(tmp_path) -> None:
    runtime, project = _admission_runtime(tmp_path)
    try:
        admitted = runtime._admit_submission("job-1", project.id, "implement", "do it", profile="  ")
        assert admitted == (project, "implement", "balanced")
        job = runtime.database.job("job-1")
        assert (job.workflow, job.profile, job.session) == ("implement", "balanced", "implement")
    finally:
        import asyncio
        asyncio.run(runtime.close())


@pytest.mark.parametrize(
    ("profile", "code", "next_action"),
    [
        pytest.param("missing-profile", "unknown_profile", "Call list and choose an available profile.", id="unknown-profile"),
    ],
)
def test_admit_submission_maps_plan_errors(tmp_path, profile, code, next_action) -> None:
    runtime, project = _admission_runtime(tmp_path)
    try:
        with pytest.raises(OrchestrationError) as raised:
            runtime._admit_submission("job-1", project.id, "implement", "do it", profile=profile)
        assert (raised.value.code, raised.value.next_action) == (code, next_action)
    finally:
        import asyncio
        asyncio.run(runtime.close())


def test_admit_submission_retry_rejects_unlisted_target_and_exhausted_order(tmp_path) -> None:
    runtime, project = _admission_runtime(tmp_path)
    try:
        with pytest.raises(OrchestrationError, match="Target 'other' is not in profile balanced; profile targets: primary.") as pinned:
            runtime._admit_submission("job-1", project.id, "implement", "do it", retry_of="old", target="other")
        assert (pinned.value.code, pinned.value.next_action) == ("invalid_request", "Call retry with target set to one of: primary.")
        with pytest.raises(OrchestrationError, match="No target follows the job's target in profile order.") as exhausted:
            runtime._admit_submission("job-2", project.id, "implement", "do it", retry_of="old", after="primary")
        assert (exhausted.value.code, exhausted.value.next_action) == ("targets_unavailable", "Call retry with target set to one of: primary.")
    finally:
        import asyncio
        asyncio.run(runtime.close())
