from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from openmcp.models import JobResult, JobView
from openmcp.notifications import send_job_notification


def _make_job(
    *,
    state: str = "succeeded",
    context_key: str = "test-ctx",
    workflow: str = "implement",
    target_id: str = "primary",
    result_text: str = "",
    result_error: str = "",
) -> JobView:
    return JobView(
        id="job-123",
        project_id="proj-456",
        workflow=workflow,
        profile="balanced",
        state=state,  # type: ignore[arg-type]
        context_key=context_key,
        target_id=target_id,
        attempts=1,
        created_at="2026-10-05T00:00:00Z",
        updated_at="2026-10-05T00:01:00Z",
        result=JobResult(text=result_text, error=result_error),
    )


def test_send_job_notification_success(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_notify_instance = MagicMock()
    mock_notify_instance.send.return_value = True
    mock_notify_cls = MagicMock(return_value=mock_notify_instance)
    monkeypatch.setattr("openmcp.notifications.Notify", mock_notify_cls)

    job = _make_job(state="succeeded", context_key="auth", workflow="implement", target_id="codex-1")
    result = send_job_notification(job, "web-app")

    assert result is True
    mock_notify_cls.assert_called_once_with()
    assert mock_notify_instance.application_name == "OpenMCP"
    assert mock_notify_instance.title == "OpenMCP job succeeded"
    assert mock_notify_instance.message == "web-app / auth / implement / codex-1"
    mock_notify_instance.send.assert_called_once_with(block=True)


def test_send_job_notification_empty_target_renders_dash(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_notify_instance = MagicMock()
    mock_notify_instance.send.return_value = True
    monkeypatch.setattr("openmcp.notifications.Notify", MagicMock(return_value=mock_notify_instance))

    job = _make_job(state="cancelled", context_key="feature", workflow="review", target_id="")
    result = send_job_notification(job, "cli-tool")

    assert result is True
    assert mock_notify_instance.title == "OpenMCP job cancelled"
    assert mock_notify_instance.message == "cli-tool / feature / review / -"


def test_send_job_notification_omits_sensitive_content(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_notify_instance = MagicMock()
    mock_notify_instance.send.return_value = True
    monkeypatch.setattr("openmcp.notifications.Notify", MagicMock(return_value=mock_notify_instance))

    secret_text = "SECRET_PASSWORD_12345"
    secret_error = "FAILED_AUTHENTICATION_TOKEN_XYZ"
    job = _make_job(result_text=secret_text, result_error=secret_error)

    send_job_notification(job, "infra")

    assert secret_text not in mock_notify_instance.message
    assert secret_error not in mock_notify_instance.message
    assert secret_text not in mock_notify_instance.title
    assert secret_error not in mock_notify_instance.title


@pytest.mark.parametrize(
    ("raw_return", "expected"),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        (None, False),
        ("ok", True),
    ],
)
def test_send_job_notification_converts_result_to_bool(
    monkeypatch: pytest.MonkeyPatch, raw_return: object, expected: bool
) -> None:
    mock_notify_instance = MagicMock()
    mock_notify_instance.send.return_value = raw_return
    monkeypatch.setattr("openmcp.notifications.Notify", MagicMock(return_value=mock_notify_instance))

    job = _make_job()
    assert send_job_notification(job, "proj") is expected
