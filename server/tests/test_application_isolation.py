import os

import pytest

from refract import cli, server
from refract.logging_setup import resolve_config
from tests.orchestration_helpers import config


@pytest.mark.asyncio
async def test_applications_own_independent_runtimes_and_tokens(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "configure_logging", lambda _: None)
    first = server.create_application(config(tmp_path / "first"))
    second = server.create_application(config(tmp_path / "second"))
    async with first.router.lifespan_context(first):
        first_runtime = first.state.runtime
        async with second.router.lifespan_context(second):
            second_runtime = second.state.runtime
            assert first_runtime is not second_runtime
            assert first.state.mcp is not second.state.mcp
            assert first.state.refract_dashboard.csrf_token
            assert first.state.refract_dashboard.csrf_token != second.state.refract_dashboard.csrf_token
            first_runtime.database.upsert_project(project_id="one", alias="one", root="/one")
            assert not second_runtime.database.projects()
        assert first.state.runtime is first_runtime
        assert second.state.runtime is None
        assert second.state.refract_dashboard.runtime is None
    assert first.state.runtime is None
    assert not first.state.refract_dashboard.csrf_token


def test_cli_logging_overrides_do_not_modify_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("REFRACT_LOG_LEVEL", "ERROR")
    before = dict(os.environ)
    args = cli._parser().parse_args([
        "serve", "--log-level", "DEBUG", "--log-file", "-", "--log-format", "json",
    ])
    overrides = cli._logging_overrides(args)
    resolved = resolve_config(config(tmp_path).logging, overrides=overrides)
    assert resolved.level == "DEBUG"
    assert resolved.format == "json"
    assert resolved.file is None
    assert dict(os.environ) == before
