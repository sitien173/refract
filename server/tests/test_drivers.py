from refract.backends import BackendResult
from refract.drivers import _normalize


def test_normalize_preserves_backend_telemetry() -> None:
    telemetry = {"total_input_tokens": {"value": 17}}
    result = _normalize(BackendResult(
        outcome="OK",
        SESSION_ID="session",
        agent_messages="done",
        error="",
        error_class="",
        telemetry=telemetry,
    ))

    assert result.telemetry == telemetry


def test_driver_result_telemetry_is_optional_for_legacy_construction() -> None:
    from refract.drivers import DriverResult

    result = DriverResult("SUCCESS", "", "", "", "")

    assert result.telemetry is None
