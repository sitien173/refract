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


def test_rejects_older_context_identity_and_invalid_quality_without_mutation():
    accumulator = TelemetryAccumulator()
    accumulator.record_context_snapshot(used_tokens=200, window_size=1000, attempt=1, invocation=2)
    accumulator.record_context_snapshot(used_tokens=100, window_size=500, attempt=1, invocation=1)
    assert accumulator.snapshot().context_used_tokens.value == 200
    with pytest.raises((ValueError, ValidationError)):
        accumulator.record_context_snapshot(used_tokens=999, window_size=1000, quality="unavailable", attempt=2, invocation=1)
    snap = accumulator.snapshot()
    assert snap.attribution.attempt == 1
    assert snap.context_used_tokens.value == 200


def test_completed_attempt_counters_are_strict_nonnegative_integers():
    for value in (-1, True, 1.5):
        with pytest.raises((ValueError, ValidationError)):
            TelemetryData.model_validate({"completed_attempts": {"total_input_tokens": value}})


def test_completed_attempt_aggregate_preserves_zero_and_provenance():
    accumulator = TelemetryAccumulator()
    accumulator.record_consumption(attempt=1, invocation=1, response_id="z", input_tokens=0, output_tokens=0,
                                   source="stream", quality="estimated", observed_at="2026-10-26T09:30:00Z")
    accumulator.complete_attempt(1)
    snap = accumulator.snapshot()
    assert snap.total_input_tokens.value == 0
    assert snap.total_input_tokens.quality == "estimated"
    assert snap.total_input_tokens.source == "stream"
    assert snap.total_input_tokens.observed_at == "2026-10-26T09:30:00Z"


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


def test_accumulator_validates_before_mutating_state():
    accumulator = TelemetryAccumulator()

    # Boolean values must be rejected and not mutate state
    with pytest.raises((ValueError, ValidationError)):
        accumulator.record_consumption(
            attempt=1, invocation=1, response_id="r1", input_tokens=True, output_tokens=10
        )
    # State should remain clean and empty
    snap = accumulator.snapshot()
    assert snap.total_input_tokens.value is None
    assert snap.total_input_tokens.quality == "unavailable"
    assert snap.completeness == "unavailable"

    # Malformed negative counts must be rejected without mutating state
    with pytest.raises((ValueError, ValidationError)):
        accumulator.record_consumption(
            attempt=1, invocation=1, response_id="r1", input_tokens=-10, output_tokens=10
        )
    # Malformed floats must be rejected without mutating state
    with pytest.raises((ValueError, ValidationError)):
        accumulator.record_consumption(
            attempt=1, invocation=1, response_id="r1", input_tokens=10.5, output_tokens=10
        )
    snap2 = accumulator.snapshot()
    assert snap2.total_input_tokens.value is None


def test_availability_tracked_per_measurement_instead_of_zero():
    accumulator = TelemetryAccumulator()
    # Cumulative observation with total_input=None, total_output=4
    accumulator.reconcile_cumulative(
        attempt=1, invocation=1, total_input=None, total_output=4, source="result"
    )
    snap = accumulator.snapshot()
    # Input must remain unavailable null, not converted to reported zero
    assert snap.total_input_tokens.value is None
    assert snap.total_input_tokens.quality == "unavailable"
    # Output must be reported 4
    assert snap.total_output_tokens.value == 4
    assert snap.total_output_tokens.quality == "reported"
    # Completeness must be partial because input was missing/unavailable
    assert snap.completeness == "partial"


def test_context_invalidation_preserved_and_older_invocation_rejected():
    from refract.telemetry import merge_telemetry

    # Test 1: Merging an explicitly invalidated snapshot must not resurrect prior context
    existing = {
        "version": 1,
        "completeness": "complete",
        "context_used_tokens": {"value": 1000, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T10:00:00Z"},
        "context_window_size": {"value": 8000, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T10:00:00Z"},
        "context_remaining_percent": {"value": 87.5, "source": "derived", "quality": "derived", "observed_at": "2026-10-26T10:00:00Z"},
        "total_input_tokens": {"value": 100, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T10:00:00Z"},
        "total_output_tokens": {"value": 50, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T10:00:00Z"},
        "attribution": {"attempt": 1, "invocation": 1},
    }
    # Incoming explicitly invalidated context
    incoming = {
        "version": 1,
        "completeness": "complete",
        "context_used_tokens": {"value": None, "source": None, "quality": "unavailable", "observed_at": "2026-10-26T10:05:00Z"},
        "context_window_size": {"value": None, "source": None, "quality": "unavailable", "observed_at": "2026-10-26T10:05:00Z"},
        "context_remaining_percent": {"value": None, "source": None, "quality": "unavailable", "observed_at": "2026-10-26T10:05:00Z"},
        "total_input_tokens": {"value": 150, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T10:05:00Z"},
        "total_output_tokens": {"value": 60, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T10:05:00Z"},
        "attribution": {"attempt": 1, "invocation": 1},
    }
    merged = merge_telemetry(existing, incoming)
    # Context must NOT be resurrected to 1000
    assert merged["context_used_tokens"]["value"] is None
    assert merged["context_used_tokens"]["quality"] == "unavailable"

    # Test 2: Recovery invocation (invocation=2) must not retain incompatible context from invocation 1
    incoming_recovery = {
        "version": 1,
        "completeness": "complete",
        "context_used_tokens": {"value": None, "source": None, "quality": "unavailable", "observed_at": "2026-10-26T10:06:00Z"},
        "context_window_size": {"value": None, "source": None, "quality": "unavailable", "observed_at": "2026-10-26T10:06:00Z"},
        "context_remaining_percent": {"value": None, "source": None, "quality": "unavailable", "observed_at": "2026-10-26T10:06:00Z"},
        "total_input_tokens": {"value": 200, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T10:06:00Z"},
        "total_output_tokens": {"value": 80, "source": "provider", "quality": "reported", "observed_at": "2026-10-26T10:06:00Z"},
        "attribution": {"attempt": 1, "invocation": 2},
    }
    merged_recovery = merge_telemetry(existing, incoming_recovery)
    assert merged_recovery["context_used_tokens"]["value"] is None
    assert merged_recovery["attribution"]["invocation"] == 2


def test_observation_ordering_and_invocation_finalization():
    accumulator = TelemetryAccumulator()

    # Observation at T2 (newer)
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="resp-1",
        input_tokens=50,
        output_tokens=20,
        observed_at="2026-10-26T10:02:00Z",
    )
    snap = accumulator.snapshot()
    assert snap.total_input_tokens.value == 50

    # Stale observation at T1 (older) arrives with larger counters for same response_id
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="resp-1",
        input_tokens=100,
        output_tokens=40,
        observed_at="2026-10-26T10:01:00Z",
    )
    # Stale observation must be rejected; consumption remains 50, not 100
    snap2 = accumulator.snapshot()
    assert snap2.total_input_tokens.value == 50

    # Finalize invocation 1
    accumulator.finalize_invocation(attempt=1, invocation=1)

    # Any new observation for finalized invocation must be rejected
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="resp-2",
        input_tokens=200,
        output_tokens=50,
        observed_at="2026-10-26T10:05:00Z",
    )
    snap3 = accumulator.snapshot()
    assert snap3.total_input_tokens.value == 50


def test_retain_truthful_provenance():
    accumulator = TelemetryAccumulator()
    observed_time = "2026-10-26T09:30:00Z"
    accumulator.record_consumption(
        attempt=1,
        invocation=1,
        response_id="resp-1",
        input_tokens=42,
        output_tokens=15,
        source="stream",
        quality="estimated",
        observed_at=observed_time,
    )
    snap = accumulator.snapshot()
    # Quality must remain estimated, not changed to reported
    assert snap.total_input_tokens.quality == "estimated"
    assert snap.total_output_tokens.quality == "estimated"
    # Source must remain stream, not changed to response
    assert snap.total_input_tokens.source == "stream"
    assert snap.total_output_tokens.source == "stream"
    # Observed_at must match observation, not refreshed to now
    assert snap.total_input_tokens.observed_at == observed_time
    assert snap.total_output_tokens.observed_at == observed_time


def test_merge_telemetry_validates_and_sanitizes_incoming():
    from refract.telemetry import merge_telemetry

    existing = {
        "version": 1,
        "completeness": "complete",
        "total_input_tokens": {"value": 100, "source": "provider", "quality": "reported"},
        "attribution": {"attempt": 1, "invocation": 1},
    }
    # Invalid incoming with boolean / negative values
    invalid_incoming = {
        "version": 1,
        "total_input_tokens": {"value": -50, "source": "provider", "quality": "reported"},
    }
    # Merging invalid incoming must not return invalid incoming or corrupt metadata
    res = merge_telemetry(existing, invalid_incoming)
    assert res["total_input_tokens"]["value"] == 100

