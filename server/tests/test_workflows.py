from __future__ import annotations

import pytest

from openmcp.workflows import BUILTIN_WORKFLOWS, get_workflow, validate_request


def test_fixed_workflows_expose_capability_and_write_behavior() -> None:
    assert BUILTIN_WORKFLOWS == ("consult", "implement", "review")
    assert get_workflow("implement").capability == "code"
    assert get_workflow("implement").writes
    assert get_workflow("review").capability == "review"
    assert not get_workflow("review").writes
    assert get_workflow("consult").capability == "consult"


def test_request_validation_normalizes_prompt_and_commit_message() -> None:
    assert validate_request(get_workflow("implement"), "  change it  ", "  feat: change  ") == ("change it", "feat: change")
    with pytest.raises(ValueError, match="Prompt must contain text"):
        validate_request(get_workflow("review"), "  ", "")
    with pytest.raises(ValueError, match="only valid for implement"):
        validate_request(get_workflow("review"), "review it", "feat: invalid")


def test_unknown_workflow_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown workflow"):
        get_workflow("custom")
