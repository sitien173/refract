"""Tests for shared typed telemetry contract, reconciliation, and validation."""

import math
import pytest
from pydantic import ValidationError

from refract.telemetry import (
    Measurement,
    TelemetryAccumulator,
    TelemetryAttribution,
    TelemetryData,
)


def test_measurement_valid_values():
    # Reported zero is valid
    m_zero = Measurement.reported(0, source="provider")
    assert m_zero.value == 0
    assert m_zero.quality == "reported"
    assert m_zero.source == "provider"

    # Unavailable null is valid
    m_null = Measurement.unavailable()
    assert m_null.value is None
    assert m_null.quality == "unavailable"

    # Derived and estimated
    m_derived = Measurement.derived(100, source="derived")
    assert m_derived.value == 100
    assert m_derived.quality == "derived"

    m_estimated = Measurement.estimated(50, source="stream")
    assert m_estimated.value == 50
    assert m_estimated.quality == "estimated"


def test_measurement_rejects_invalid_types_and_values():
    # Reject booleans
    with pytest.raises((ValueError, ValidationError)):
        Measurement(value=True, source="provider", quality="reported")
    with pytest.raises((ValueError, ValidationError)):
        Measurement(value=False, source="provider", quality="reported")

    # Reject negative values
    with pytest.raises((ValueError, ValidationError)):
        Measurement(value=-1, source="provider", quality="reported")

    # Reject non-finite floats
    with pytest.raises((ValueError, ValidationError)):
        Measurement(value=float("nan"), source="provider", quality="reported")
    with pytest.raises((ValueError, ValidationError)):
        Measurement(value=float("inf"), source="provider", quality="reported")

    # Reject non-null value with unavailable quality
    with pytest.raises((ValueError, ValidationError)):
        Measurement(value=10, source="provider", quality="unavailable")

    # Reject null value with reported quality
    with pytest.raises((ValueError, ValidationError)):
        Measurement(value=None, source="provider", quality="reported")

    # Reject raw path as source
    with pytest.raises((ValueError, ValidationError)):
        Measurement(value=10, source="/home/user/session.json", quality="reported")

    # Reject raw payload as source
    with pytest.raises((ValueError, ValidationError)):
        Measurement(value=10, source='{"tokens": 10}', quality="reported")


def test_telemetry_data_validation():
    # Token measurements must be non-negative ints or None, rejecting floats
    with pytest.raises((ValueError, ValidationError)):
        TelemetryData(
            total_input_tokens=Measurement(value=10.5, source="provider", quality="reported")
        )

    # Percentage measurement must be between 0 and 100
    with pytest.raises((ValueError, ValidationError)):
        TelemetryData(
            context_remaining_percent=Measurement(value=105.0, source="provider", quality="reported")
        )
    with pytest.raises((ValueError, ValidationError)):
        TelemetryData(
            context_remaining_percent=Measurement(value=-0.1, source="provider", quality="reported")
        )

    # Valid telemetry data with zero and nulls
    data = TelemetryData(
        total_input_tokens=Measurement.reported(0, source="provider"),
        total_output_tokens=Measurement.reported(0, source="provider"),
        context_remaining_percent=Measurement.reported(100.0, source="provider"),
    )
    assert data.total_input_tokens.value == 0
    assert data.total_output_tokens.value == 0
    assert data.context_remaining_percent.value == 100.0
    assert data.context_window_size.value is None
    assert data.context_window_size.quality == "unavailable"


def test_context_snapshot_and_invalidation():
    accumulator = TelemetryAccumulator()

    # Initial context is unavailable
    snap = accumulator.snapshot()
    assert snap.context_used_tokens.value is None
    assert snap.context_window_size.value is None
    assert snap.context_remaining_percent.value is None

    # Record context snapshot: derives percentage when not supplied
    accumulator.record_context_snapshot(
        used_tokens=2000,
        window_size=10000,
        source="provider",
        quality="reported",
    )
    snap = accumulator.snapshot()
    assert snap.context_used_tokens.value == 2000
    assert snap.context_window_size.value == 10000
    assert snap.context_remaining_percent.value == 80.0
    assert snap.context_remaining_percent.quality == "derived"

    # Context invalidation clears context snapshot
    accumulator.invalidate_context()
    snap = accumulator.snapshot()
    assert snap.context_used_tokens.value is None
    assert snap.context_window_size.value is None
    assert snap.context_remaining_percent.value is None


def test_consumption_reconciliation_and_snapshots():
    accumulator = TelemetryAccumulator()

    # Response 1 streaming snapshot 1
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="resp-1",
        input_tokens=100,
        output_tokens=20,
        cache_read_tokens=10,
        cache_write_tokens=5,
        is_snapshot=True,
    )
    snap = accumulator.snapshot()
    assert snap.total_input_tokens.value == 100
    assert snap.total_output_tokens.value == 20
    assert snap.cache_read_tokens.value == 10
    assert snap.cache_write_tokens.value == 5

    # Response 1 streaming snapshot 2 replaces snapshot 1 (not added)
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="resp-1",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=10,
        cache_write_tokens=5,
        is_snapshot=True,
    )
    snap = accumulator.snapshot()
    assert snap.total_input_tokens.value == 100
    assert snap.total_output_tokens.value == 50

    # Duplicate observation for response 1 does not inflate consumption
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="resp-1",
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=10,
        cache_write_tokens=5,
        is_snapshot=False,
    )
    snap = accumulator.snapshot()
    assert snap.total_input_tokens.value == 100
    assert snap.total_output_tokens.value == 50

    # Response 2 adds to consumption
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="resp-2",
        input_tokens=200,
        output_tokens=80,
        cache_read_tokens=20,
        cache_write_tokens=0,
        is_snapshot=False,
    )
    snap = accumulator.snapshot()
    assert snap.total_input_tokens.value == 300
    assert snap.total_output_tokens.value == 130
    assert snap.cache_read_tokens.value == 30
    assert snap.cache_write_tokens.value == 5
    assert snap.completeness == "complete"


def test_cumulative_reconciliation_does_not_double_count():
    accumulator = TelemetryAccumulator()

    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="resp-1",
        input_tokens=100,
        output_tokens=50,
    )
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="resp-2",
        input_tokens=100,
        output_tokens=50,
    )
    assert accumulator.snapshot().total_input_tokens.value == 200

    # Cumulative reconciliation with total 200 does not add 200
    accumulator.reconcile_cumulative(
        attempt=1,
        invocation=1,
        total_input=200,
        total_output=100,
    )
    snap = accumulator.snapshot()
    assert snap.total_input_tokens.value == 200
    assert snap.total_output_tokens.value == 100


def test_attempts_and_retry_aggregation():
    accumulator = TelemetryAccumulator()

    # Attempt 1 consumes tokens and sets context
    accumulator.record_context_snapshot(used_tokens=1500, window_size=8000)
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="resp-1",
        input_tokens=150,
        output_tokens=60,
    )
    snap = accumulator.snapshot()
    assert snap.total_input_tokens.value == 150
    assert snap.context_used_tokens.value == 1500

    # Complete attempt 1 (e.g. on retry)
    accumulator.complete_attempt(1)

    # Completed attempt aggregate is stored, context is cleared
    snap = accumulator.snapshot()
    assert snap.completed_attempts.total_input_tokens == 150
    assert snap.completed_attempts.total_output_tokens == 60
    assert snap.total_input_tokens.value == 150
    assert snap.context_used_tokens.value is None

    # Attempt 2 starts and records new consumption and context
    accumulator.record_context_snapshot(used_tokens=500, window_size=8000, attempt=2)
    accumulator.record_consumption(
        attempt=2,
        invocation=1,
        response_id="resp-1",
        input_tokens=50,
        output_tokens=20,
    )
    snap = accumulator.snapshot()
    # Total input tokens includes attempt 1 (150) + attempt 2 (50) = 200
    assert snap.total_input_tokens.value == 200
    assert snap.total_output_tokens.value == 80
    # Context snapshot reflects attempt 2 only, not attempt 1
    assert snap.context_used_tokens.value == 500
    assert snap.attribution.attempt == 2


def test_session_recovery_invocations():
    accumulator = TelemetryAccumulator()

    # Invocation 1: initial attempt
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="turn-1",
        input_tokens=100,
        output_tokens=40,
    )
    # Invocation 2: reconstruct recovery
    accumulator.record_consumption(
        attempt=1,
        invocation=2,
        response_id="turn-2",
        input_tokens=120,
        output_tokens=50,
    )
    snap = accumulator.snapshot()
    assert snap.total_input_tokens.value == 220
    assert snap.total_output_tokens.value == 90
    assert snap.attribution.invocation == 2


def test_completeness_tracking():
    accumulator = TelemetryAccumulator()
    assert accumulator.snapshot().completeness == "unavailable"

    # Known observation -> complete
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="turn-1",
        input_tokens=100,
        output_tokens=40,
    )
    assert accumulator.snapshot().completeness == "complete"

    # Incomplete invocation -> partial
    accumulator.record_missing_contribution(attempt=1, invocation=2)
    assert accumulator.snapshot().completeness == "partial"
