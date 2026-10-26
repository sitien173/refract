"""Shared typed telemetry contract, reconciliation, and validation."""

from __future__ import annotations

import math
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from refract.config_inspection import utc_now


TelemetryQuality = Literal["reported", "derived", "estimated", "unavailable"]
TelemetryCompleteness = Literal["complete", "partial", "unavailable"]

VALID_SOURCES = frozenset({
    "stream",
    "session",
    "provider",
    "response",
    "result",
    "synthetic",
    "derived",
    "cli",
    "turn",
    "step",
    "summary",
})


def _validate_source(source: str | None) -> str | None:
    if source is None:
        return None
    if not isinstance(source, str):
        raise ValueError("Source must be a string")
    if "/" in source or "\\" in source:
        raise ValueError("Raw file paths are not permitted as telemetry source")
    if "{" in source or "}" in source or "\n" in source:
        raise ValueError("Raw payloads are not permitted as telemetry source")
    if source not in VALID_SOURCES:
        raise ValueError(f"Invalid telemetry source: {source}")
    return source


class Measurement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int | float | None = None
    source: str | None = None
    quality: TelemetryQuality = "unavailable"
    observed_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _validate_measurement(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        raw_val = data.get("value")
        if isinstance(raw_val, bool) or type(raw_val) is bool:
            raise ValueError("Boolean values are not permitted for measurements")
        if isinstance(raw_val, float):
            if not math.isfinite(raw_val):
                raise ValueError("Non-finite numbers are not permitted for measurements")
        if raw_val is not None and raw_val < 0:
            raise ValueError("Measurement value cannot be negative")

        quality = data.get("quality", "unavailable" if raw_val is None else "reported")
        if raw_val is None:
            if quality != "unavailable":
                raise ValueError("Null measurement value must have unavailable quality")
        else:
            if quality == "unavailable":
                raise ValueError("Non-null measurement value cannot have unavailable quality")
            if quality not in ("reported", "derived", "estimated"):
                raise ValueError(f"Invalid quality: {quality}")

        source = _validate_source(data.get("source"))
        observed_at = data.get("observed_at")
        if raw_val is not None and observed_at is None:
            observed_at = utc_now()

        return {
            "value": raw_val,
            "source": source,
            "quality": quality,
            "observed_at": observed_at,
        }

    @classmethod
    def reported(cls, value: int | float | None, source: str = "provider", observed_at: str | None = None) -> Measurement:
        if value is None:
            return cls.unavailable()
        return cls(value=value, source=source, quality="reported", observed_at=observed_at or utc_now())

    @classmethod
    def derived(cls, value: int | float | None, source: str = "derived", observed_at: str | None = None) -> Measurement:
        if value is None:
            return cls.unavailable()
        return cls(value=value, source=source, quality="derived", observed_at=observed_at or utc_now())

    @classmethod
    def estimated(cls, value: int | float | None, source: str = "stream", observed_at: str | None = None) -> Measurement:
        if value is None:
            return cls.unavailable()
        return cls(value=value, source=source, quality="estimated", observed_at=observed_at or utc_now())

    @classmethod
    def unavailable(cls) -> Measurement:
        return cls(value=None, source=None, quality="unavailable", observed_at=None)


class TelemetryAttribution(BaseModel):
    model_config = ConfigDict(extra="ignore")

    attempt: int = 1
    invocation: int = 1


class CompletedAttemptsAggregate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class TelemetryData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 1
    completeness: TelemetryCompleteness = "unavailable"
    context_remaining_percent: Measurement = Field(default_factory=Measurement.unavailable)
    context_window_size: Measurement = Field(default_factory=Measurement.unavailable)
    context_used_tokens: Measurement = Field(default_factory=Measurement.unavailable)
    total_input_tokens: Measurement = Field(default_factory=Measurement.unavailable)
    total_output_tokens: Measurement = Field(default_factory=Measurement.unavailable)
    cache_read_tokens: Measurement = Field(default_factory=Measurement.unavailable)
    cache_write_tokens: Measurement = Field(default_factory=Measurement.unavailable)
    attribution: TelemetryAttribution = Field(default_factory=TelemetryAttribution)
    completed_attempts: CompletedAttemptsAggregate = Field(default_factory=CompletedAttemptsAggregate)

    @field_validator("context_remaining_percent", mode="after")
    @classmethod
    def _validate_percent(cls, m: Measurement) -> Measurement:
        if m.value is not None:
            if isinstance(m.value, bool):
                raise ValueError("Boolean values are not permitted")
            val = float(m.value)
            if not math.isfinite(val) or val < 0.0 or val > 100.0:
                raise ValueError("Context remaining percentage must be between 0 and 100")
            if m.value != val:
                return m.model_copy(update={"value": val})
        return m

    @field_validator(
        "context_window_size",
        "context_used_tokens",
        "total_input_tokens",
        "total_output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        mode="after",
    )
    @classmethod
    def _validate_token_count(cls, m: Measurement) -> Measurement:
        if m.value is not None:
            if isinstance(m.value, bool):
                raise ValueError("Boolean values are not permitted")
            if isinstance(m.value, float):
                raise ValueError("Token counts must be integers, not floats")
            if not isinstance(m.value, int):
                raise ValueError("Token counts must be non-negative integers")
        return m


class TelemetryAccumulator:
    """Accumulates and reconciles telemetry observations across attempts and invocations."""

    def __init__(self, initial_data: TelemetryData | dict[str, Any] | None = None) -> None:
        self._completed_attempts = CompletedAttemptsAggregate()
        self._active_attempt = 1
        self._active_invocation = 1

        # Current context snapshot
        self._context_used_tokens: Measurement = Measurement.unavailable()
        self._context_window_size: Measurement = Measurement.unavailable()
        self._context_remaining_percent: Measurement = Measurement.unavailable()

        # Responses consumption keyed by (attempt, invocation, response_id) -> dict
        self._responses: dict[tuple[int, int, str], dict[str, Any]] = {}
        # Cumulative reconciliation per (attempt, invocation)
        self._cumulative_invocations: dict[tuple[int, int], dict[str, Any]] = {}

        # Has missing contribution
        self._has_missing_contribution = False
        self._has_any_consumption = False
        self._loaded_total_input = 0
        self._loaded_total_output = 0
        self._loaded_cache_read = 0
        self._loaded_cache_write = 0

        if initial_data is not None:
            self._load(initial_data)

    def _load(self, data: TelemetryData | dict[str, Any]) -> None:
        if isinstance(data, dict):
            telemetry = TelemetryData.model_validate(data)
        else:
            telemetry = data

        self._completed_attempts = telemetry.completed_attempts.model_copy()
        self._active_attempt = telemetry.attribution.attempt
        self._active_invocation = telemetry.attribution.invocation
        self._context_used_tokens = telemetry.context_used_tokens.model_copy()
        self._context_window_size = telemetry.context_window_size.model_copy()
        self._context_remaining_percent = telemetry.context_remaining_percent.model_copy()
        if telemetry.total_input_tokens.value is not None:
            self._has_any_consumption = True
            self._loaded_total_input = telemetry.total_input_tokens.value
        if telemetry.total_output_tokens.value is not None:
            self._loaded_total_output = telemetry.total_output_tokens.value
        if telemetry.cache_read_tokens.value is not None:
            self._loaded_cache_read = telemetry.cache_read_tokens.value
        if telemetry.cache_write_tokens.value is not None:
            self._loaded_cache_write = telemetry.cache_write_tokens.value
        if telemetry.completeness == "partial":
            self._has_missing_contribution = True

    def record_context_snapshot(
        self,
        *,
        used_tokens: int | None = None,
        window_size: int | None = None,
        remaining_percent: float | None = None,
        source: str = "provider",
        quality: TelemetryQuality = "reported",
        observed_at: str | None = None,
        attempt: int | None = None,
        invocation: int | None = None,
    ) -> None:
        if attempt is not None:
            self._active_attempt = attempt
        if invocation is not None:
            self._active_invocation = invocation

        ts = observed_at or utc_now()
        if used_tokens is not None:
            self._context_used_tokens = Measurement(
                value=used_tokens, source=source, quality=quality, observed_at=ts
            )
        if window_size is not None:
            self._context_window_size = Measurement(
                value=window_size, source=source, quality=quality, observed_at=ts
            )

        if remaining_percent is not None:
            self._context_remaining_percent = Measurement(
                value=float(remaining_percent), source=source, quality=quality, observed_at=ts
            )
        elif (
            self._context_window_size.value is not None
            and self._context_window_size.value > 0
            and self._context_used_tokens.value is not None
        ):
            used = self._context_used_tokens.value
            cap = self._context_window_size.value
            derived_pct = round(max(0.0, min(100.0, (1.0 - (used / cap)) * 100.0)), 2)
            self._context_remaining_percent = Measurement.derived(
                derived_pct, source="derived", observed_at=ts
            )
        else:
            self._context_remaining_percent = Measurement.unavailable()

    def invalidate_context(self) -> None:
        self._context_used_tokens = Measurement.unavailable()
        self._context_window_size = Measurement.unavailable()
        self._context_remaining_percent = Measurement.unavailable()

    def record_consumption(
        self,
        *,
        attempt: int,
        invocation: int,
        response_id: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        cache_write_tokens: int | None = None,
        is_snapshot: bool = False,
        source: str = "response",
        quality: TelemetryQuality = "reported",
        observed_at: str | None = None,
    ) -> None:
        self._active_attempt = max(self._active_attempt, attempt)
        self._active_invocation = invocation
        self._has_any_consumption = True

        if input_tokens is None or output_tokens is None:
            self._has_missing_contribution = True

        resp_key = (
            attempt,
            invocation,
            response_id or f"_anon_{len(self._responses)}",
        )
        self._responses[resp_key] = {
            "input": input_tokens or 0,
            "output": output_tokens or 0,
            "cache_read": cache_read_tokens or 0,
            "cache_write": cache_write_tokens or 0,
            "source": source,
            "quality": quality,
            "observed_at": observed_at or utc_now(),
        }

    def reconcile_cumulative(
        self,
        *,
        attempt: int,
        invocation: int,
        total_input: int | None,
        total_output: int | None,
        cache_read: int | None = None,
        cache_write: int | None = None,
        source: str = "result",
        quality: TelemetryQuality = "reported",
        observed_at: str | None = None,
    ) -> None:
        self._active_attempt = max(self._active_attempt, attempt)
        self._active_invocation = invocation
        self._has_any_consumption = True

        key = (attempt, invocation)
        self._cumulative_invocations[key] = {
            "total_input": total_input,
            "total_output": total_output,
            "cache_read": cache_read,
            "cache_write": cache_write,
            "source": source,
            "quality": quality,
            "observed_at": observed_at or utc_now(),
        }

    def record_missing_contribution(self, *, attempt: int, invocation: int) -> None:
        self._has_missing_contribution = True
        self._active_attempt = max(self._active_attempt, attempt)
        self._active_invocation = invocation

    def complete_attempt(self, attempt: int) -> None:
        # Sum consumption for this attempt and commit to completed_attempts
        attempt_input = 0
        attempt_output = 0
        attempt_cache_read = 0
        attempt_cache_write = 0

        # Invocations for this attempt
        invocations = {inv for (att, inv, _) in self._responses if att == attempt}
        invocations |= {inv for (att, inv) in self._cumulative_invocations if att == attempt}

        if not invocations and self._has_any_consumption:
            # Fall back to loaded consumption difference if responses were not held in memory
            attempt_input = max(0, self._loaded_total_input - self._completed_attempts.total_input_tokens)
            attempt_output = max(0, self._loaded_total_output - self._completed_attempts.total_output_tokens)
            attempt_cache_read = max(0, self._loaded_cache_read - self._completed_attempts.cache_read_tokens)
            attempt_cache_write = max(0, self._loaded_cache_write - self._completed_attempts.cache_write_tokens)
        else:
            for inv in invocations:
                inv_input, inv_output, inv_cr, inv_cw = self._calculate_invocation(attempt, inv)
                attempt_input += inv_input
                attempt_output += inv_output
                attempt_cache_read += inv_cr
                attempt_cache_write += inv_cw

        self._completed_attempts = CompletedAttemptsAggregate(
            total_input_tokens=self._completed_attempts.total_input_tokens + attempt_input,
            total_output_tokens=self._completed_attempts.total_output_tokens + attempt_output,
            cache_read_tokens=self._completed_attempts.cache_read_tokens + attempt_cache_read,
            cache_write_tokens=self._completed_attempts.cache_write_tokens + attempt_cache_write,
        )

        # Clear responses for this attempt
        self._responses = {k: v for k, v in self._responses.items() if k[0] != attempt}
        self._cumulative_invocations = {
            k: v for k, v in self._cumulative_invocations.items() if k[0] != attempt
        }

        # Clear context snapshot for retry
        self.invalidate_context()
        self._active_attempt = attempt + 1
        self._active_invocation = 1

    def _calculate_invocation(self, attempt: int, invocation: int) -> tuple[int, int, int, int]:
        cum = self._cumulative_invocations.get((attempt, invocation))
        resp_input = 0
        resp_output = 0
        resp_cr = 0
        resp_cw = 0

        for (att, inv, _), data in self._responses.items():
            if att == attempt and inv == invocation:
                resp_input += data["input"]
                resp_output += data["output"]
                resp_cr += data["cache_read"]
                resp_cw += data["cache_write"]

        if cum is not None:
            total_in = max(resp_input, cum["total_input"] or 0)
            total_out = max(resp_output, cum["total_output"] or 0)
            total_cr = max(resp_cr, cum["cache_read"] or 0)
            total_cw = max(resp_cw, cum["cache_write"] or 0)
            return total_in, total_out, total_cr, total_cw

        return resp_input, resp_output, resp_cr, resp_cw

    def snapshot(self) -> TelemetryData:
        # Sum active attempts
        active_input = 0
        active_output = 0
        active_cr = 0
        active_cw = 0

        active_invocations = {inv for (att, inv, _) in self._responses}
        active_invocations |= {inv for (att, inv) in self._cumulative_invocations}

        for inv in active_invocations:
            in_val, out_val, cr_val, cw_val = self._calculate_invocation(self._active_attempt, inv)
            active_input += in_val
            active_output += out_val
            active_cr += cr_val
            active_cw += cw_val

        total_input = self._completed_attempts.total_input_tokens + active_input
        total_output = self._completed_attempts.total_output_tokens + active_output
        total_cr = self._completed_attempts.cache_read_tokens + active_cr
        total_cw = self._completed_attempts.cache_write_tokens + active_cw

        if not self._has_any_consumption and total_input == 0 and total_output == 0:
            m_input = Measurement.unavailable()
            m_output = Measurement.unavailable()
            m_cr = Measurement.unavailable()
            m_cw = Measurement.unavailable()
            completeness: TelemetryCompleteness = "unavailable"
        else:
            completeness = "partial" if self._has_missing_contribution else "complete"
            m_input = Measurement.reported(total_input, source="response")
            m_output = Measurement.reported(total_output, source="response")
            m_cr = Measurement.reported(total_cr, source="response")
            m_cw = Measurement.reported(total_cw, source="response")

        return TelemetryData(
            version=1,
            completeness=completeness,
            context_remaining_percent=self._context_remaining_percent,
            context_window_size=self._context_window_size,
            context_used_tokens=self._context_used_tokens,
            total_input_tokens=m_input,
            total_output_tokens=m_output,
            cache_read_tokens=m_cr,
            cache_write_tokens=m_cw,
            attribution=TelemetryAttribution(
                attempt=self._active_attempt,
                invocation=self._active_invocation,
            ),
            completed_attempts=self._completed_attempts,
        )


def merge_telemetry(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    if not existing:
        return incoming
    if not incoming:
        return existing

    try:
        ext = TelemetryData.model_validate(existing)
        inc = TelemetryData.model_validate(incoming)
    except Exception:
        return incoming if incoming else existing

    if inc.attribution.attempt > ext.attribution.attempt:
        attr = inc.attribution
        completed = inc.completed_attempts
        ctx_used = inc.context_used_tokens
        ctx_win = inc.context_window_size
        ctx_rem = inc.context_remaining_percent
    elif inc.attribution.attempt < ext.attribution.attempt:
        return existing
    else:
        attr = (
            inc.attribution
            if inc.attribution.invocation >= ext.attribution.invocation
            else ext.attribution
        )
        completed = CompletedAttemptsAggregate(
            total_input_tokens=max(ext.completed_attempts.total_input_tokens, inc.completed_attempts.total_input_tokens),
            total_output_tokens=max(ext.completed_attempts.total_output_tokens, inc.completed_attempts.total_output_tokens),
            cache_read_tokens=max(ext.completed_attempts.cache_read_tokens, inc.completed_attempts.cache_read_tokens),
            cache_write_tokens=max(ext.completed_attempts.cache_write_tokens, inc.completed_attempts.cache_write_tokens),
        )
        if inc.context_used_tokens.value is not None or inc.context_used_tokens.quality != "unavailable":
            ctx_used = inc.context_used_tokens
        else:
            ctx_used = ext.context_used_tokens

        if inc.context_window_size.value is not None or inc.context_window_size.quality != "unavailable":
            ctx_win = inc.context_window_size
        else:
            ctx_win = ext.context_window_size

        if inc.context_remaining_percent.value is not None or inc.context_remaining_percent.quality != "unavailable":
            ctx_rem = inc.context_remaining_percent
        else:
            ctx_rem = ext.context_remaining_percent

    def _merge_m(m1: Measurement, m2: Measurement) -> Measurement:
        if m2.value is not None and m1.value is not None:
            return m2 if m2.value >= m1.value else m1
        if m2.value is not None:
            return m2
        if m1.value is not None:
            return m1
        return m2

    tot_in = _merge_m(ext.total_input_tokens, inc.total_input_tokens)
    tot_out = _merge_m(ext.total_output_tokens, inc.total_output_tokens)
    cr = _merge_m(ext.cache_read_tokens, inc.cache_read_tokens)
    cw = _merge_m(ext.cache_write_tokens, inc.cache_write_tokens)

    if ext.completeness == "partial" or inc.completeness == "partial":
        comp: TelemetryCompleteness = "partial"
    elif inc.completeness == "complete" or ext.completeness == "complete":
        comp = "complete"
    else:
        comp = "unavailable"

    merged = TelemetryData(
        version=max(ext.version, inc.version),
        completeness=comp,
        context_remaining_percent=ctx_rem,
        context_window_size=ctx_win,
        context_used_tokens=ctx_used,
        total_input_tokens=tot_in,
        total_output_tokens=tot_out,
        cache_read_tokens=cr,
        cache_write_tokens=cw,
        attribution=attr,
        completed_attempts=completed,
    )
    return merged.model_dump(mode="json")


def prepare_telemetry_for_retry(telemetry: dict[str, Any]) -> dict[str, Any]:
    acc = TelemetryAccumulator(telemetry)
    current_attempt = acc.snapshot().attribution.attempt
    acc.complete_attempt(current_attempt)
    return acc.snapshot().model_dump(mode="json")

