from __future__ import annotations

import pytest

from openmcp.planning import execution_plan_data, parse_execution_plan, resolve_execution_plan
from openmcp.workflows import get_workflow
from tests.orchestration_helpers import config


def test_plan_snapshots_one_workflow_selection(tmp_path) -> None:
    catalog = config(tmp_path / "home")
    plan = resolve_execution_plan(get_workflow("implement"), catalog, "balanced")
    data = execution_plan_data(plan)
    assert data["profile"] == "balanced"
    assert data["workflow"] == "implement"
    assert data["selection"] == {"targets": ["primary"], "max_attempts": 1, "timeout_s": 0}
    assert parse_execution_plan(data) == plan


def test_plan_rejects_legacy_multi_workflow_shape(tmp_path) -> None:
    data = execution_plan_data(resolve_execution_plan(get_workflow("review"), config(tmp_path / "home"), "balanced"))
    data.pop("selection")
    data["workflows"] = {"review": "primary"}
    with pytest.raises(ValueError, match="selection"):
        parse_execution_plan(data)
