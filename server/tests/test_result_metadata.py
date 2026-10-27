import math

import pytest
from pydantic import ValidationError

from refract.models import JobResult
from refract.result_metadata import (
    ExecutionMetadata, FailureMetadata, JobResultMetadata, PublicTelemetry,
    RetryMetadata, convert_schema15_metadata,
)
from refract.telemetry import Measurement, TelemetryData

METRICS = (
    "context_remaining_percent", "context_window_size", "context_used_tokens",
    "total_input_tokens", "total_output_tokens", "cache_read_tokens", "cache_write_tokens",
)
FAILURES = (
    "cancelled", "circuit_open", "config_invalid", "context_overflow",
    "replay_blocked", "request_fatal", "retryable", "target_fatal",
)
TS = "2025-01-01T00:00:00Z"


def measurement(value=1, **extra):
    return {"value": value, "source": "provider", "quality": "reported", "observed_at": TS, **extra}


def test_job_result_metadata_is_typed_and_rejects_legacy_fields():
    assert isinstance(JobResult().metadata, JobResultMetadata)
    with pytest.raises(ValidationError):
        JobResult(metadata={"model_name": "legacy"})


def test_metadata_exact_shape_and_explicit_unavailable_defaults():
    metadata = JobResultMetadata()
    assert set(metadata.model_dump()) == {"execution", "failure", "retry", "telemetry"}
    assert set(metadata.execution.model_dump()) == {"model", "duration_ms"}
    assert metadata.failure is None
    assert set(metadata.retry.model_dump()) == {"retryable", "next_target"}
    assert set(metadata.telemetry.model_dump()) == {"completeness", *METRICS}
    assert metadata.telemetry.completeness == "unavailable"
    assert all(getattr(metadata.telemetry, name).quality == "unavailable" for name in METRICS)


@pytest.mark.parametrize("factory", [
    lambda: ExecutionMetadata(extra="x"), lambda: FailureMetadata(kind="x", extra="x"),
    lambda: RetryMetadata(retryable=False, extra="x"),
    lambda: PublicTelemetry(completeness="complete", extra="x"),
    lambda: JobResultMetadata(extra="x"),
])
def test_each_nested_model_forbids_extra_fields(factory):
    with pytest.raises(ValidationError):
        factory()


@pytest.mark.parametrize("failure", FAILURES)
def test_all_existing_failure_kinds_are_valid(failure):
    assert FailureMetadata(kind=failure).kind == failure


@pytest.mark.parametrize("kwargs", [
    {"model_name": "alias"}, {"duration_ms": True}, {"duration_ms": -1},
    {"duration_ms": 1.5}, {"model": 3},
])
def test_execution_rejects_aliases_and_invalid_values(kwargs):
    with pytest.raises(ValidationError):
        ExecutionMetadata(**kwargs)


def test_retry_rejects_wrong_types_and_failure_is_nullable():
    for kwargs in ({"retryable": 1}, {"next_target": 3}):
        with pytest.raises(ValidationError):
            RetryMetadata(**kwargs)
    assert JobResultMetadata(failure=None).failure is None


@pytest.mark.parametrize("completeness", ["complete", "partial", "unavailable"])
def test_completeness_values(completeness):
    assert PublicTelemetry(completeness=completeness).completeness == completeness


@pytest.mark.parametrize("field", METRICS)
def test_every_measurement_rejects_nested_extra(field):
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={field: measurement(extra="bad")})


@pytest.mark.parametrize("field", [name for name in METRICS if name != "context_remaining_percent"])
@pytest.mark.parametrize("value", [1.5, True, -1, float("nan"), float("inf"), -float("inf")])
def test_every_token_measurement_is_strict(field, value):
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={field: measurement(value)})


@pytest.mark.parametrize("value", [-0.1, 100.1, float("nan"), float("inf"), -float("inf"), True])
def test_percent_measurement_is_finite_and_bounded(value):
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={"context_remaining_percent": measurement(value)})


@pytest.mark.parametrize("quality", ["bogus", "unavailable"])
def test_valued_measurement_rejects_invalid_quality(quality):
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={"total_input_tokens": measurement(1, quality=quality)})


@pytest.mark.parametrize("field", METRICS)
def test_each_measurement_accepts_null_unavailable_and_zero_with_timestamp(field):
    null_value = {"value": None, "source": None, "quality": "unavailable", "observed_at": None}
    assert getattr(JobResultMetadata(telemetry={field: null_value}).telemetry, field).value is None
    zero = 0.0 if field == "context_remaining_percent" else 0
    parsed = getattr(JobResultMetadata(telemetry={field: measurement(zero)}).telemetry, field)
    assert parsed.value == zero and parsed.observed_at == TS


def test_null_measurement_requires_unavailable_quality_and_provenance_types_are_strict():
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={"total_input_tokens": measurement(None, quality="reported")})
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={"total_input_tokens": measurement(1, source=7)})
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={"total_input_tokens": measurement(1, observed_at=7)})


def test_canonical_valued_measurement_requires_observation_time():
    with pytest.raises(ValidationError, match="observed_at"):
        JobResultMetadata(telemetry={"total_input_tokens": {"value": 3, "source": "provider", "quality": "reported"}})


def test_converter_drops_legacy_counters_and_stored_token_and_separates_state():
    metadata, internal = convert_schema15_metadata({
        "model_name": "model-x", "duration_ms": 7, "failure_kind": None,
        "retryable": None, "next_target": "secret", "input_tokens": 999, "unknown": 4,
    })
    public = metadata.model_dump(mode="json")
    assert public["execution"] == {"model": "model-x", "duration_ms": 7}
    assert public["failure"] is None
    assert public["retry"] == {"retryable": None, "next_target": None}
    assert public["telemetry"]["total_input_tokens"]["value"] is None
    assert internal is None
    assert set(public["telemetry"]) == {"completeness", *METRICS}


def test_empty_present_telemetry_has_internal_defaults_but_absent_is_none():
    metadata, internal = convert_schema15_metadata({"telemetry": {}})
    assert internal is not None and internal.version == 1
    assert metadata.telemetry.completeness == "unavailable"


def test_converter_preserves_historical_measurement_exactly_and_legacy_does_not_override():
    m = {"value": 12, "source": None, "quality": "reported", "observed_at": TS}
    metadata, internal = convert_schema15_metadata({
        "telemetry": {"version": 1, "completeness": "partial", "total_input_tokens": m},
        "input_tokens": 900,
    })
    assert metadata.telemetry.total_input_tokens.model_dump() == m
    assert internal.total_input_tokens.model_dump() == m
    assert metadata.telemetry.completeness == "partial"
    assert internal.attribution.attempt == 1
    assert internal.completed_attempts.total_input_tokens == 0
    assert "attribution" not in metadata.telemetry.model_dump()
    assert "completed_attempts" not in metadata.telemetry.model_dump()


def test_converter_rejects_valued_history_missing_timestamp_without_clock_fill():
    with pytest.raises(ValueError, match="observed_at"):
        convert_schema15_metadata({"telemetry": {"total_input_tokens": {"value": 1, "source": None, "quality": "reported"}}})


@pytest.mark.parametrize("bad", ["2", True, 0, -1, 1.5])
def test_converter_rejects_invalid_internal_attribution_attempt(bad):
    with pytest.raises(ValueError, match="attribution"):
        convert_schema15_metadata({"telemetry": {"attribution": {"attempt": bad}}})


@pytest.mark.parametrize("bad", ["2", True, -1, 1.5])
def test_converter_rejects_invalid_internal_aggregate_counts(bad):
    with pytest.raises(ValueError, match="completed_attempts"):
        convert_schema15_metadata({"telemetry": {"completed_attempts": {"total_input_tokens": bad}}})


@pytest.mark.parametrize("field", ["attempt", "invocation"])
@pytest.mark.parametrize("bad", ["2", True, 0, -1, 1.5])
def test_converter_rejects_invalid_internal_attribution_fields(field, bad):
    with pytest.raises(ValueError, match="attribution"):
        convert_schema15_metadata({"telemetry": {"attribution": {field: bad}}})


@pytest.mark.parametrize("field", ["total_input_tokens", "total_output_tokens", "cache_read_tokens", "cache_write_tokens"])
@pytest.mark.parametrize("bad", ["2", True, -1, 1.5])
def test_converter_rejects_invalid_internal_aggregate_fields(field, bad):
    with pytest.raises(ValueError, match="completed_attempts"):
        convert_schema15_metadata({"telemetry": {"completed_attempts": {field: bad}}})


@pytest.mark.parametrize("field", METRICS)
@pytest.mark.parametrize("source", [7, "/secret/path", "{payload}"])
def test_public_measurements_reject_invalid_provenance(field, source):
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={field: measurement(1, source=source)})


@pytest.mark.parametrize("version", [0, 2, "1", True])
def test_converter_rejects_unsupported_or_mistyped_versions(version):
    with pytest.raises(ValueError, match="version"):
        convert_schema15_metadata({"telemetry": {"version": version}})


@pytest.mark.parametrize("field,value", [("duration_ms", True), ("duration_ms", -1), ("retryable", 1), ("input_tokens", True), ("failure_kind", "unknown")])
def test_converter_rejects_invalid_recognized_legacy_fields(field, value):
    with pytest.raises(ValueError):
        convert_schema15_metadata({field: value})


@pytest.mark.parametrize("field", METRICS)
def test_public_valued_measurement_rejects_missing_quality(field):
    zero = 0.0 if field == "context_remaining_percent" else 1
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={field: {"value": zero, "source": "provider", "observed_at": TS}})


@pytest.mark.parametrize("field", METRICS)
def test_public_measurement_rejects_explicit_null_quality(field):
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={field: {"value": None, "quality": None}})


@pytest.mark.parametrize("field", METRICS)
def test_historical_measurement_rejects_explicit_null_quality(field):
    with pytest.raises(ValueError, match="quality"):
        convert_schema15_metadata({"telemetry": {field: {"value": None, "quality": None}}})


@pytest.mark.parametrize("bad_quality", [["reported"], {"quality": "reported"}, 1, True])
def test_public_measurement_rejects_non_string_quality_without_type_error(bad_quality):
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={"total_input_tokens": measurement(1, quality=bad_quality)})
    with pytest.raises(ValidationError):
        JobResultMetadata(telemetry={"total_input_tokens": {"value": None, "quality": bad_quality}})


@pytest.mark.parametrize("field", METRICS)
def test_public_unavailable_measurement_permits_missing_quality(field):
    res = JobResultMetadata(telemetry={field: {"value": None, "source": None, "observed_at": None}})
    assert getattr(res.telemetry, field).quality == "unavailable"
    assert getattr(res.telemetry, field).value is None

    empty_res = JobResultMetadata(telemetry={field: {}})
    assert getattr(empty_res.telemetry, field).quality == "unavailable"
    assert getattr(empty_res.telemetry, field).value is None


@pytest.mark.parametrize("quality", ["reported", "derived", "estimated"])
def test_public_valued_measurement_preserves_valid_quality(quality):
    meta = JobResultMetadata(telemetry={"total_input_tokens": measurement(2, quality=quality)})
    assert meta.telemetry.total_input_tokens.quality == quality


@pytest.mark.parametrize("field", METRICS)
def test_converter_rejects_valued_measurement_missing_quality(field):
    zero = 0.0 if field == "context_remaining_percent" else 2
    with pytest.raises(ValueError, match="quality"):
        convert_schema15_metadata({"telemetry": {field: {"value": zero, "source": "provider", "observed_at": TS}}})


@pytest.mark.parametrize("bad_quality", [["reported"], {"quality": "reported"}, 1, True])
def test_converter_rejects_non_string_quality_without_type_error(bad_quality):
    with pytest.raises(ValueError, match="quality"):
        convert_schema15_metadata({"telemetry": {"total_input_tokens": measurement(2, quality=bad_quality)}})
    with pytest.raises(ValueError, match="quality"):
        convert_schema15_metadata({"telemetry": {"total_input_tokens": {"value": None, "quality": bad_quality}}})


@pytest.mark.parametrize("field", METRICS)
def test_converter_permits_missing_quality_on_unavailable_measurement(field):
    meta, internal = convert_schema15_metadata({"telemetry": {field: {"value": None}}})
    assert getattr(meta.telemetry, field).quality == "unavailable"
    assert getattr(internal, field).quality == "unavailable"

    meta2, internal2 = convert_schema15_metadata({"telemetry": {field: {}}})
    assert getattr(meta2.telemetry, field).quality == "unavailable"
    assert getattr(internal2, field).quality == "unavailable"


@pytest.mark.parametrize("quality", ["reported", "derived", "estimated"])
def test_converter_preserves_valid_quality_exactly(quality):
    meta, internal = convert_schema15_metadata({
        "telemetry": {"total_input_tokens": {"value": 2, "source": "provider", "quality": quality, "observed_at": TS}}
    })
    assert meta.telemetry.total_input_tokens.quality == quality
    assert internal.total_input_tokens.quality == quality


def test_canonical_schema_accepts_config_invalid_and_nonretryable_metadata():
    metadata = JobResultMetadata(
        failure=FailureMetadata(kind="config_invalid"),
        retry=RetryMetadata(retryable=False),
    )
    assert metadata.failure is not None
    assert metadata.failure.kind == "config_invalid"
    assert metadata.retry.retryable is False

    job_result = JobResult(metadata=metadata)
    assert job_result.metadata.failure is not None
    assert job_result.metadata.failure.kind == "config_invalid"
    assert job_result.metadata.retry.retryable is False


def test_converter_accepts_historical_config_invalid():
    metadata, internal = convert_schema15_metadata({
        "failure_kind": "config_invalid",
        "retryable": False,
    })
    assert metadata.failure is not None
    assert metadata.failure.kind == "config_invalid"
    assert metadata.retry.retryable is False
    assert internal is None


def test_strict_unknown_failure_validation_preserved():
    with pytest.raises(ValidationError):
        FailureMetadata(kind="unknown")
    with pytest.raises(ValidationError):
        JobResultMetadata(failure={"kind": "unknown"})
