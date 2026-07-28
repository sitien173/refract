from __future__ import annotations

import pytest

from openmcp.workflows import BUILTIN_WORKFLOWS, get_workflow, validate_request


def test_fixed_workflows_are_validated_strings() -> None:
    assert BUILTIN_WORKFLOWS == ("consult", "implement", "other", "review")
    assert get_workflow("implement") == "implement"
    assert get_workflow("review") == "review"
    assert get_workflow("consult") == "consult"
    assert get_workflow("other") == "other"


def test_request_validation_normalizes_prompt_only() -> None:
    assert validate_request(get_workflow("implement"), "  change it  ") == "change it"
    assert validate_request(get_workflow("review"), " review it ") == "review it"
    with pytest.raises(ValueError, match="Prompt must contain text"):
        validate_request(get_workflow("review"), "  ")


def test_unknown_workflow_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown workflow"):
        get_workflow("custom")
