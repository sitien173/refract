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


def _validate_token_count_value(val: Any) -> int | None:
    if val is None:
        return None
    if isinstance(val, bool) or type(val) is bool:
        raise ValueError("Boolean values are not permitted for measurements")
    if isinstance(val, float):
        raise ValueError("Token counts must be integers, not floats")
    if not isinstance(val, int):
        raise ValueError("Token counts must be non-negative integers")
    if val < 0:
        raise ValueError("Token count cannot be negative")
    return val


def _validate_percent_value(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, bool) or type(val) is bool:
        raise ValueError("Boolean values are not permitted for measurements")
    if not isinstance(val, (int, float)):
        raise ValueError("Percentage must be a number")
    v = float(val)
    if not math.isfinite(v) or v < 0.0 or v > 100.0:
        raise ValueError("Context remaining percentage must be between 0 and 100")
    return v



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

    total_input_tokens: int = Field(default=0, ge=0, strict=True)
    total_output_tokens: int = Field(default=0, ge=0, strict=True)
    cache_read_tokens: int = Field(default=0, ge=0, strict=True)
    cache_write_tokens: int = Field(default=0, ge=0, strict=True)


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
        # Finalized invocations
        self._finalized_invocations: set[tuple[int, int]] = set()
        self._missing_invocations: set[tuple[int, int]] = set()
        self._completed_measurements: dict[str, Measurement] = {}

        # Has missing contribution
        self._has_missing_contribution = False
        self._has_any_consumption = False
        self._loaded_total_input: int | None = None
        self._loaded_total_output: int | None = None
        self._loaded_cache_read: int | None = None
        self._loaded_cache_write: int | None = None
        self._loaded_input_meta: dict[str, Any] | None = None
        self._loaded_output_meta: dict[str, Any] | None = None
        self._loaded_cr_meta: dict[str, Any] | None = None
        self._loaded_cw_meta: dict[str, Any] | None = None

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
            self._loaded_input_meta = {
                "quality": telemetry.total_input_tokens.quality,
                "source": telemetry.total_input_tokens.source,
                "observed_at": telemetry.total_input_tokens.observed_at,
            }
        if telemetry.total_output_tokens.value is not None:
            self._has_any_consumption = True
            self._loaded_total_output = telemetry.total_output_tokens.value
            self._loaded_output_meta = {
                "quality": telemetry.total_output_tokens.quality,
                "source": telemetry.total_output_tokens.source,
                "observed_at": telemetry.total_output_tokens.observed_at,
            }
        if telemetry.cache_read_tokens.value is not None:
            self._has_any_consumption = True
            self._loaded_cache_read = telemetry.cache_read_tokens.value
            self._loaded_cr_meta = {
                "quality": telemetry.cache_read_tokens.quality,
                "source": telemetry.cache_read_tokens.source,
                "observed_at": telemetry.cache_read_tokens.observed_at,
            }
        if telemetry.cache_write_tokens.value is not None:
            self._has_any_consumption = True
            self._loaded_cache_write = telemetry.cache_write_tokens.value
            self._loaded_cw_meta = {
                "quality": telemetry.cache_write_tokens.quality,
                "source": telemetry.cache_write_tokens.source,
                "observed_at": telemetry.cache_write_tokens.observed_at,
            }
        if telemetry.completeness == "partial":
            self._has_missing_contribution = True

    def finalize_invocation(self, *, attempt: int, invocation: int) -> None:
        self._finalized_invocations.add((attempt, invocation))

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
        att = attempt if attempt is not None else self._active_attempt
        inv = invocation if invocation is not None else self._active_invocation
        if isinstance(att, bool) or not isinstance(att, int) or att < 1:
            raise ValueError("Attempt must be a positive integer")
        if isinstance(inv, bool) or not isinstance(inv, int) or inv < 1:
            raise ValueError("Invocation must be a positive integer")

        if (att, inv) in self._finalized_invocations or (att, inv) < (self._active_attempt, self._active_invocation):
            return

        used_val = _validate_token_count_value(used_tokens)
        win_val = _validate_token_count_value(window_size)
        rem_val = _validate_percent_value(remaining_percent)
        src = _validate_source(source) or "provider"
        if quality not in ("reported", "derived", "estimated", "unavailable"):
            raise ValueError(f"Invalid quality: {quality}")

        ts = observed_at or utc_now()
        # Construct every candidate before changing attribution or context.
        candidate_used = Measurement(value=used_val, source=src, quality=quality, observed_at=ts) if used_val is not None else None
        candidate_window = Measurement(value=win_val, source=src, quality=quality, observed_at=ts) if win_val is not None else None
        candidate_remaining = Measurement(value=rem_val, source=src, quality=quality, observed_at=ts) if rem_val is not None else None
        existing_ts = self._context_used_tokens.observed_at or self._context_window_size.observed_at
        if existing_ts and ts < existing_ts and att == self._active_attempt and inv == self._active_invocation:
            return

        self._active_attempt = max(self._active_attempt, att)
        self._active_invocation = max(self._active_invocation, inv)

        if candidate_used is not None:
            self._context_used_tokens = candidate_used
        if candidate_window is not None:
            self._context_window_size = candidate_window

        if candidate_remaining is not None:
            self._context_remaining_percent = candidate_remaining
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

    def invalidate_context(self, observed_at: str | None = None) -> None:
        ts = observed_at or utc_now()
        self._context_used_tokens = Measurement(
            value=None, source="derived", quality="unavailable", observed_at=ts
        )
        self._context_window_size = Measurement(
            value=None, source="derived", quality="unavailable", observed_at=ts
        )
        self._context_remaining_percent = Measurement(
            value=None, source="derived", quality="unavailable", observed_at=ts
        )

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
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ValueError("Attempt must be a positive integer")
        if isinstance(invocation, bool) or not isinstance(invocation, int) or invocation < 1:
            raise ValueError("Invocation must be a positive integer")

        if (attempt, invocation) in self._finalized_invocations:
            return

        in_val = _validate_token_count_value(input_tokens)
        out_val = _validate_token_count_value(output_tokens)
        cr_val = _validate_token_count_value(cache_read_tokens)
        cw_val = _validate_token_count_value(cache_write_tokens)
        src = _validate_source(source) or "response"
        if quality not in ("reported", "derived", "estimated", "unavailable"):
            raise ValueError(f"Invalid quality: {quality}")

        ts = observed_at or utc_now()
        resp_key = (
            attempt,
            invocation,
            response_id or f"_anon_{len(self._responses)}",
        )
        if resp_key in self._responses:
            existing = self._responses[resp_key]
            if existing.get("observed_at") and ts < existing["observed_at"]:
                return

        self._active_attempt = max(self._active_attempt, attempt)
        self._active_invocation = invocation
        self._has_any_consumption = True

        if in_val is None or out_val is None:
            self._has_missing_contribution = True

        self._responses[resp_key] = {
            "input": in_val,
            "output": out_val,
            "cache_read": cr_val,
            "cache_write": cw_val,
            "source": src,
            "quality": quality,
            "observed_at": ts,
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
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ValueError("Attempt must be a positive integer")
        if isinstance(invocation, bool) or not isinstance(invocation, int) or invocation < 1:
            raise ValueError("Invocation must be a positive integer")

        if (attempt, invocation) in self._finalized_invocations:
            return

        in_val = _validate_token_count_value(total_input)
        out_val = _validate_token_count_value(total_output)
        cr_val = _validate_token_count_value(cache_read)
        cw_val = _validate_token_count_value(cache_write)
        src = _validate_source(source) or "result"
        if quality not in ("reported", "derived", "estimated", "unavailable"):
            raise ValueError(f"Invalid quality: {quality}")

        ts = observed_at or utc_now()
        key = (attempt, invocation)
        if key in self._cumulative_invocations:
            existing = self._cumulative_invocations[key]
            if existing.get("observed_at") and ts < existing["observed_at"]:
                return

        self._active_attempt = max(self._active_attempt, attempt)
        self._active_invocation = invocation
        self._has_any_consumption = True

        if in_val is None or out_val is None:
            self._has_missing_contribution = True

        self._cumulative_invocations[key] = {
            "total_input": in_val,
            "total_output": out_val,
            "cache_read": cr_val,
            "cache_write": cw_val,
            "source": src,
            "quality": quality,
            "observed_at": ts,
        }

    def record_missing_contribution(self, *, attempt: int, invocation: int) -> None:
        self._missing_invocations.add((attempt, invocation))
        self._has_missing_contribution = True
        self._active_attempt = max(self._active_attempt, attempt)
        self._active_invocation = invocation

    def complete_attempt(self, attempt: int) -> None:
        attempt_input, attempt_output, attempt_cr, attempt_cw = self._calculate_attempt_totals(attempt)
        metric_names = ("total_input_tokens", "total_output_tokens", "cache_read_tokens", "cache_write_tokens")
        values = (attempt_input, attempt_output, attempt_cr, attempt_cw)
        invocations = {inv for (att, inv, _) in self._responses if att == attempt}
        invocations |= {inv for (att, inv) in self._cumulative_invocations if att == attempt}
        for name, value in zip(metric_names, values):
            if value is not None:
                prior = self._completed_measurements.get(name)
                qualities = [prior.quality] if prior else []
                sources = [prior.source] if prior and prior.source else []
                times = [prior.observed_at] if prior and prior.observed_at else []
                loaded_meta = {
                    "total_input_tokens": self._loaded_input_meta,
                    "total_output_tokens": self._loaded_output_meta,
                    "cache_read_tokens": self._loaded_cr_meta,
                    "cache_write_tokens": self._loaded_cw_meta,
                }[name]
                if loaded_meta:
                    if loaded_meta.get("quality"):
                        qualities.append(loaded_meta["quality"])
                    if loaded_meta.get("source"):
                        sources.append(loaded_meta["source"])
                    if loaded_meta.get("observed_at"):
                        times.append(loaded_meta["observed_at"])
                for inv in invocations:
                    measurement = self._calculate_invocation_measurements(attempt, inv)[metric_names.index(name)]
                    if measurement.value is not None:
                        qualities.append(measurement.quality)
                        if measurement.source: sources.append(measurement.source)
                        if measurement.observed_at: times.append(measurement.observed_at)
                quality = "estimated" if "estimated" in qualities else "derived" if "derived" in qualities else "reported"
                source = sources[0] if sources and len(set(sources)) == 1 else "derived" if sources else "response"
                self._completed_measurements[name] = Measurement(value=(prior.value if prior else 0) + value,
                    quality=quality, source=source, observed_at=max(times) if times else None)

        if attempt_input is None and attempt_output is None:
            self._has_missing_contribution = True
        else:
            self._completed_attempts = CompletedAttemptsAggregate(
                total_input_tokens=self._completed_attempts.total_input_tokens + (attempt_input or 0),
                total_output_tokens=self._completed_attempts.total_output_tokens + (attempt_output or 0),
                cache_read_tokens=self._completed_attempts.cache_read_tokens + (attempt_cr or 0),
                cache_write_tokens=self._completed_attempts.cache_write_tokens + (attempt_cw or 0),
            )
        for name in metric_names:
            measurement = self._completed_measurements.get(name)
            if measurement is not None:
                self._completed_measurements[name] = measurement.model_copy(
                    update={"value": getattr(self._completed_attempts, name)}
                )

        self._responses = {k: v for k, v in self._responses.items() if k[0] != attempt}
        self._cumulative_invocations = {
            k: v for k, v in self._cumulative_invocations.items() if k[0] != attempt
        }

        self.invalidate_context()
        self._active_attempt = attempt + 1
        self._active_invocation = 1

    def _calculate_attempt_totals(self, attempt: int) -> tuple[int | None, int | None, int | None, int | None]:
        invocations = {inv for (att, inv, _) in self._responses if att == attempt}
        invocations |= {inv for (att, inv) in self._cumulative_invocations if att == attempt}

        if not invocations:
            if self._has_any_consumption and self._loaded_total_input is not None:
                inp = max(0, self._loaded_total_input - self._completed_attempts.total_input_tokens)
                out = max(0, (self._loaded_total_output or 0) - self._completed_attempts.total_output_tokens)
                cr = max(0, (self._loaded_cache_read or 0) - self._completed_attempts.cache_read_tokens)
                cw = max(0, (self._loaded_cache_write or 0) - self._completed_attempts.cache_write_tokens)
                return inp, out, cr, cw
            return None, None, None, None

        tot_in: int | None = None
        tot_out: int | None = None
        tot_cr: int | None = None
        tot_cw: int | None = None

        invocations |= {inv for (att, inv) in self._missing_invocations if att == attempt}
        for inv in invocations:
            m_in, m_out, m_cr, m_cw = self._calculate_invocation_measurements(attempt, inv)
            if m_in.value is not None:
                tot_in = (tot_in or 0) + int(m_in.value)
            if m_out.value is not None:
                tot_out = (tot_out or 0) + int(m_out.value)
            if m_cr.value is not None:
                tot_cr = (tot_cr or 0) + int(m_cr.value)
            if m_cw.value is not None:
                tot_cw = (tot_cw or 0) + int(m_cw.value)

        return tot_in, tot_out, tot_cr, tot_cw

    def _calculate_invocation_measurements(
        self, attempt: int, invocation: int
    ) -> tuple[Measurement, Measurement, Measurement, Measurement]:
        cum = self._cumulative_invocations.get((attempt, invocation))
        resp_list = [
            v for (att, inv, _), v in self._responses.items()
            if att == attempt and inv == invocation
        ]

        def _calc_field(field_key: str, cum_key: str) -> Measurement:
            resp_vals = [d[field_key] for d in resp_list if d[field_key] is not None]
            resp_sum = sum(resp_vals) if resp_vals else None

            cum_val = cum.get(cum_key) if cum else None

            if cum is not None:
                if cum_val is not None:
                    final_val = max(resp_sum or 0, cum_val)
                elif resp_sum is not None:
                    final_val = resp_sum
                else:
                    final_val = None
            elif resp_sum is not None:
                final_val = resp_sum
            else:
                final_val = None

            if final_val is None:
                return Measurement.unavailable()

            qualities = [d["quality"] for d in resp_list if d.get(field_key) is not None]
            sources = [d["source"] for d in resp_list if d.get(field_key) is not None]
            timestamps = [d["observed_at"] for d in resp_list if d.get(field_key) is not None and d.get("observed_at")]

            if cum is not None and cum.get(cum_key) is not None:
                qualities.append(cum["quality"])
                sources.append(cum["source"])
                if cum.get("observed_at"):
                    timestamps.append(cum["observed_at"])

            if any(q == "estimated" for q in qualities):
                fin_qual: TelemetryQuality = "estimated"
            elif any(q == "derived" for q in qualities):
                fin_qual = "derived"
            else:
                fin_qual = "reported"

            uniq_sources = set(sources)
            if len(uniq_sources) == 1:
                fin_src = next(iter(uniq_sources))
            elif len(uniq_sources) > 1:
                fin_src = "derived"
            else:
                fin_src = "response"

            fin_ts = max(timestamps) if timestamps else None
            return Measurement(value=final_val, quality=fin_qual, source=fin_src, observed_at=fin_ts)

        return (
            _calc_field("input", "total_input"),
            _calc_field("output", "total_output"),
            _calc_field("cache_read", "cache_read"),
            _calc_field("cache_write", "cache_write"),
        )

    def snapshot(self) -> TelemetryData:
        active_invocations = {inv for (att, inv, _) in self._responses if att == self._active_attempt}
        active_invocations |= {inv for (att, inv) in self._cumulative_invocations if att == self._active_attempt}

        active_in: int | None = None
        active_out: int | None = None
        active_cr: int | None = None
        active_cw: int | None = None

        qualities_in: list[TelemetryQuality] = []
        sources_in: list[str] = []
        ts_in: list[str] = []

        qualities_out: list[TelemetryQuality] = []
        sources_out: list[str] = []
        ts_out: list[str] = []

        qualities_cr: list[TelemetryQuality] = []
        sources_cr: list[str] = []
        ts_cr: list[str] = []

        qualities_cw: list[TelemetryQuality] = []
        sources_cw: list[str] = []
        ts_cw: list[str] = []

        for inv in active_invocations:
            m_in, m_out, m_cr, m_cw = self._calculate_invocation_measurements(self._active_attempt, inv)
            if m_in.value is not None:
                active_in = (active_in or 0) + int(m_in.value)
                qualities_in.append(m_in.quality)
                if m_in.source:
                    sources_in.append(m_in.source)
                if m_in.observed_at:
                    ts_in.append(m_in.observed_at)
            if m_out.value is not None:
                active_out = (active_out or 0) + int(m_out.value)
                qualities_out.append(m_out.quality)
                if m_out.source:
                    sources_out.append(m_out.source)
                if m_out.observed_at:
                    ts_out.append(m_out.observed_at)
            if m_cr.value is not None:
                active_cr = (active_cr or 0) + int(m_cr.value)
                qualities_cr.append(m_cr.quality)
                if m_cr.source:
                    sources_cr.append(m_cr.source)
                if m_cr.observed_at:
                    ts_cr.append(m_cr.observed_at)
            if m_cw.value is not None:
                active_cw = (active_cw or 0) + int(m_cw.value)
                qualities_cw.append(m_cw.quality)
                if m_cw.source:
                    sources_cw.append(m_cw.source)
                if m_cw.observed_at:
                    ts_cw.append(m_cw.observed_at)

        def _resolve_total(
            active_val: int | None,
            completed_val: int,
            loaded_val: int | None,
            loaded_meta: dict[str, Any] | None,
            qualities: list[TelemetryQuality],
            sources: list[str],
            ts_list: list[str],
            completed_measurement: Measurement | None = None,
        ) -> Measurement:

            if active_val is not None:
                tot = completed_val + active_val
            elif completed_measurement is not None:
                # The serialized aggregate can lag the completed-attempt counter
                # after an accumulator is reloaded and rolls over again.
                tot = max(completed_val, completed_measurement.value or 0)
            elif completed_val > 0:
                tot = completed_val
            elif loaded_val is not None:
                tot = loaded_val
            else:
                return Measurement.unavailable()

            if completed_measurement is not None:
                qualities.append(completed_measurement.quality)
                if completed_measurement.source:
                    sources.append(completed_measurement.source)
                if completed_measurement.observed_at:
                    ts_list.append(completed_measurement.observed_at)
            if loaded_meta:
                if loaded_meta.get("quality"):
                    qualities.append(loaded_meta["quality"])
                if loaded_meta.get("source"):
                    sources.append(loaded_meta["source"])
                if loaded_meta.get("observed_at"):
                    ts_list.append(loaded_meta["observed_at"])

            if any(q == "estimated" for q in qualities):
                q_fin: TelemetryQuality = "estimated"
            elif any(q == "derived" for q in qualities):
                q_fin = "derived"
            else:
                q_fin = "reported"

            s_uniq = set(sources)
            if len(s_uniq) == 1:
                s_fin = next(iter(s_uniq))
            elif len(s_uniq) > 1:
                s_fin = "derived"
            else:
                s_fin = "response"

            t_fin = max(ts_list) if ts_list else None
            return Measurement(value=tot, quality=q_fin, source=s_fin, observed_at=t_fin)

        m_input = _resolve_total(
            active_in, self._completed_attempts.total_input_tokens,
            self._loaded_total_input, self._loaded_input_meta,
            qualities_in, sources_in, ts_in, self._completed_measurements.get("total_input_tokens")
        )
        m_output = _resolve_total(
            active_out, self._completed_attempts.total_output_tokens,
            self._loaded_total_output, self._loaded_output_meta,
            qualities_out, sources_out, ts_out, self._completed_measurements.get("total_output_tokens")
        )
        m_cr = _resolve_total(
            active_cr, self._completed_attempts.cache_read_tokens,
            self._loaded_cache_read, self._loaded_cr_meta,
            qualities_cr, sources_cr, ts_cr, self._completed_measurements.get("cache_read_tokens")
        )
        m_cw = _resolve_total(
            active_cw, self._completed_attempts.cache_write_tokens,
            self._loaded_cache_write, self._loaded_cw_meta,
            qualities_cw, sources_cw, ts_cw, self._completed_measurements.get("cache_write_tokens")
        )

        has_any = (
            m_input.value is not None
            or m_output.value is not None
            or m_cr.value is not None
            or m_cw.value is not None
        )

        if not has_any:
            completeness: TelemetryCompleteness = "partial" if self._has_missing_contribution else "unavailable"
        elif self._has_missing_contribution or m_input.value is None or m_output.value is None:
            completeness = "partial"
        else:
            completeness = "complete"

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
    if not incoming:
        return existing

    try:
        inc = TelemetryData.model_validate(incoming)
    except Exception:
        return existing

    if not existing:
        return inc.model_dump(mode="json")

    try:
        ext = TelemetryData.model_validate(existing)
    except Exception:
        return inc.model_dump(mode="json")

    if inc.attribution.attempt < ext.attribution.attempt:
        return ext.model_dump(mode="json")
    elif inc.attribution.attempt > ext.attribution.attempt:
        attr = inc.attribution
        completed = inc.completed_attempts
        ctx_used = inc.context_used_tokens
        ctx_win = inc.context_window_size
        ctx_rem = inc.context_remaining_percent
    else:
        if inc.attribution.invocation > ext.attribution.invocation:
            attr = inc.attribution
            ctx_used = inc.context_used_tokens
            ctx_win = inc.context_window_size
            ctx_rem = inc.context_remaining_percent
        elif inc.attribution.invocation < ext.attribution.invocation:
            attr = ext.attribution
            ctx_used = ext.context_used_tokens
            ctx_win = ext.context_window_size
            ctx_rem = ext.context_remaining_percent
        else:
            attr = inc.attribution
            inc_ts = inc.context_used_tokens.observed_at or inc.context_window_size.observed_at
            ext_ts = ext.context_used_tokens.observed_at or ext.context_window_size.observed_at
            if inc_ts and ext_ts:
                if inc_ts >= ext_ts:
                    ctx_used = inc.context_used_tokens
                    ctx_win = inc.context_window_size
                    ctx_rem = inc.context_remaining_percent
                else:
                    ctx_used = ext.context_used_tokens
                    ctx_win = ext.context_window_size
                    ctx_rem = ext.context_remaining_percent
            else:
                if inc.context_used_tokens.quality != "unavailable" or "context_used_tokens" in incoming:
                    ctx_used = inc.context_used_tokens
                    ctx_win = inc.context_window_size
                    ctx_rem = inc.context_remaining_percent
                else:
                    ctx_used = ext.context_used_tokens
                    ctx_win = ext.context_window_size
                    ctx_rem = ext.context_remaining_percent

        completed = CompletedAttemptsAggregate(
            total_input_tokens=max(ext.completed_attempts.total_input_tokens, inc.completed_attempts.total_input_tokens),
            total_output_tokens=max(ext.completed_attempts.total_output_tokens, inc.completed_attempts.total_output_tokens),
            cache_read_tokens=max(ext.completed_attempts.cache_read_tokens, inc.completed_attempts.cache_read_tokens),
            cache_write_tokens=max(ext.completed_attempts.cache_write_tokens, inc.completed_attempts.cache_write_tokens),
        )

    def _merge_m(m1: Measurement, m2: Measurement) -> Measurement:
        if m2.value is not None and m1.value is not None:
            if m2.observed_at and m1.observed_at:
                return m2 if m2.observed_at >= m1.observed_at else m1
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

