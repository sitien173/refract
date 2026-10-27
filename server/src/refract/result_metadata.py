"""Strict public result metadata and pure schema-15 conversion boundary."""
from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

from refract.telemetry import Measurement, TelemetryCompleteness, TelemetryData

FAILURE_KINDS = ("cancelled", "circuit_open", "config_invalid", "context_overflow", "replay_blocked", "request_fatal", "retryable", "target_fatal")
FailureKind = Literal["cancelled", "circuit_open", "config_invalid", "context_overflow", "replay_blocked", "request_fatal", "retryable", "target_fatal"]
METRIC_NAMES = (
    "context_remaining_percent", "context_window_size", "context_used_tokens",
    "total_input_tokens", "total_output_tokens", "cache_read_tokens", "cache_write_tokens",
)
TOKEN_METRICS = frozenset(METRIC_NAMES[1:])
MEASUREMENT_KEYS = frozenset({"value", "source", "quality", "observed_at"})
QUALITIES = frozenset({"reported", "derived", "estimated", "unavailable"})


def _check_measurement(name: str, raw: Any) -> Any:
    if isinstance(raw, Measurement):
        raw = raw.model_dump()
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must be a measurement object")
    extras = raw.keys() - MEASUREMENT_KEYS
    if extras:
        raise ValueError(f"{name} has unknown fields")
    raw = dict(raw)
    value = raw.get("value")
    if value is not None:
        if type(value) is bool:
            raise ValueError(f"{name}.value cannot be boolean")
        if name in TOKEN_METRICS:
            if type(value) is not int or value < 0:
                raise ValueError(f"{name}.value must be a non-negative integer")
        elif not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError(f"{name}.value must be finite and between 0 and 100")
        if raw.get("observed_at") is None:
            raise ValueError(f"{name}.observed_at is required for valued measurements")
        if "quality" not in raw or raw["quality"] is None:
            raise ValueError(f"{name}.quality is required for valued measurements")
        quality = raw["quality"]
        if not isinstance(quality, str) or quality not in ("reported", "derived", "estimated"):
            raise ValueError(f"{name}.quality is invalid for its value")
    else:
        if "quality" not in raw:
            raw["quality"] = "unavailable"
        else:
            quality = raw["quality"]
            if not isinstance(quality, str) or quality != "unavailable":
                raise ValueError(f"{name}.quality is invalid for its value")

    source = raw.get("source")
    if source is not None and not isinstance(source, str):
        raise ValueError(f"{name}.source must be a string or null")
    observed = raw.get("observed_at")
    if observed is not None and not isinstance(observed, str):
        raise ValueError(f"{name}.observed_at must be a string or null")
    return raw


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

class ExecutionMetadata(StrictModel):
    model: StrictStr | None = None
    duration_ms: StrictInt | None = None

    @field_validator("duration_ms")
    @classmethod
    def nonnegative_duration(cls, value):
        if value is not None and value < 0:
            raise ValueError("duration_ms must be non-negative")
        return value


class FailureMetadata(StrictModel):
    kind: FailureKind


class RetryMetadata(StrictModel):
    retryable: StrictBool | None = None
    next_target: StrictStr | None = None


class PublicTelemetry(StrictModel):
    completeness: TelemetryCompleteness = "unavailable"
    context_remaining_percent: Measurement = Field(default_factory=Measurement.unavailable)
    context_window_size: Measurement = Field(default_factory=Measurement.unavailable)
    context_used_tokens: Measurement = Field(default_factory=Measurement.unavailable)
    total_input_tokens: Measurement = Field(default_factory=Measurement.unavailable)
    total_output_tokens: Measurement = Field(default_factory=Measurement.unavailable)
    cache_read_tokens: Measurement = Field(default_factory=Measurement.unavailable)
    cache_write_tokens: Measurement = Field(default_factory=Measurement.unavailable)

    @model_validator(mode="before")
    @classmethod
    def strict_measurements(cls, data):
        if isinstance(data, dict):
            for name in METRIC_NAMES:
                if name in data:
                    _check_measurement(name, data[name])
        return data

    @classmethod
    def from_internal(cls, data: TelemetryData) -> "PublicTelemetry":
        return cls.model_validate({name: getattr(data, name).model_dump() for name in METRIC_NAMES} | {"completeness": data.completeness})


class JobResultMetadata(StrictModel):
    execution: ExecutionMetadata = Field(default_factory=ExecutionMetadata)
    failure: FailureMetadata | None = None
    retry: RetryMetadata = Field(default_factory=RetryMetadata)
    telemetry: PublicTelemetry = Field(default_factory=PublicTelemetry)


def project_telemetry(data: TelemetryData) -> PublicTelemetry:
    return PublicTelemetry.from_internal(data)


def _legacy_validate(raw: dict[str, Any]) -> None:
    specs = {
        "model_name": "string", "duration_ms": "count", "failure_kind": "failure",
        "retryable": "bool", "next_target": "string", "context_window_max": "count",
        "context_window_used": "count", "input_tokens": "count", "output_tokens": "count",
        "cached_input_tokens": "count",
    }
    for key, kind in specs.items():
        if key not in raw or raw[key] is None:
            continue
        value = raw[key]
        valid = (
            isinstance(value, str) if kind == "string" else
            type(value) is int and value >= 0 if kind == "count" else
            type(value) is bool if kind == "bool" else
            value in FAILURE_KINDS if kind == "failure" else False
        )
        if not valid:
            raise ValueError(f"{key} is invalid")


def _historical_payload(raw: dict[str, Any]) -> dict[str, Any]:
    version = raw.get("version", 1)
    if type(version) is not int or version != 1:
        raise ValueError("telemetry.version is unsupported")
    completeness = raw.get("completeness", "unavailable")
    if completeness not in ("complete", "partial", "unavailable"):
        raise ValueError("telemetry.completeness is invalid")
    payload: dict[str, Any] = {"version": version, "completeness": completeness}
    for name in METRIC_NAMES:
        if name in raw:
            payload[name] = _check_measurement(name, raw[name])

    attribution = raw.get("attribution", {})
    if not isinstance(attribution, dict):
        raise ValueError("telemetry.attribution must be an object")
    attr = {}
    for key in ("attempt", "invocation"):
        value = attribution.get(key, 1)
        if type(value) is not int or value < 1:
            raise ValueError(f"telemetry.attribution.{key} is invalid")
        attr[key] = value
    payload["attribution"] = attr

    completed = raw.get("completed_attempts", {})
    if not isinstance(completed, dict):
        raise ValueError("telemetry.completed_attempts must be an object")
    aggregate = {}
    for key in ("total_input_tokens", "total_output_tokens", "cache_read_tokens", "cache_write_tokens"):
        value = completed.get(key, 0)
        if type(value) is not int or value < 0:
            raise ValueError(f"telemetry.completed_attempts.{key} is invalid")
        aggregate[key] = value
    payload["completed_attempts"] = aggregate
    return payload


def convert_schema15_metadata(raw: dict[str, Any]) -> tuple[JobResultMetadata, TelemetryData | None]:
    """Convert historical metadata only; return public data and optional accumulator state."""
    if not isinstance(raw, dict):
        raise ValueError("metadata must be an object")
    _legacy_validate(raw)
    model = raw.get("model_name")
    failure_kind = raw.get("failure_kind")
    historical = raw.get("telemetry")
    internal = None
    if historical is not None:
        if not isinstance(historical, dict):
            raise ValueError("telemetry must be an object")
        internal = TelemetryData.model_validate(_historical_payload(historical))
        public_telemetry = project_telemetry(internal)
    else:
        public_telemetry = PublicTelemetry()
    metadata = JobResultMetadata(
        execution=ExecutionMetadata(model=model, duration_ms=raw.get("duration_ms")),
        failure=FailureMetadata(kind=failure_kind) if failure_kind is not None else None,
        retry=RetryMetadata(retryable=raw.get("retryable"), next_target=None),
        telemetry=public_telemetry,
    )
    return metadata, internal
