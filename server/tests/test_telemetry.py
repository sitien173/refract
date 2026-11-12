"""Flat token counters: six nullable integers, null when unknown, never zero-filled."""

import refract.telemetry as telemetry
from refract.telemetry import TokenCounters

KEYS = ("context_used", "context_window", "input", "output", "cache_read", "cache_write")


def test_new_counters_are_all_unknown():
    assert TokenCounters().as_dict() == dict.fromkeys(KEYS)


def test_measurement_model_is_gone():
    for name in ("Measurement", "TelemetryData", "TelemetryAccumulator", "flat_tokens"):
        assert not hasattr(telemetry, name)


def test_reported_zero_is_kept_and_unreported_field_stays_null():
    counters = TokenCounters()
    counters.record_totals(input=0, output=0)
    assert counters.as_dict()["input"] == 0
    assert counters.as_dict()["cache_write"] is None


def test_totals_are_recorded_per_field_and_a_later_value_replaces_an_earlier_one():
    counters = TokenCounters()
    counters.record_totals(input=10, output=1, cache_read=3)
    counters.record_totals(input=40, output=9)
    assert counters.as_dict() == {
        "context_used": None,
        "context_window": None,
        "input": 40,
        "output": 9,
        "cache_read": 3,
        "cache_write": None,
    }


def test_context_keeps_latest_value_and_none_leaves_it_unchanged():
    counters = TokenCounters()
    counters.record_context(used=100, window=1000)
    counters.record_context(used=250)
    assert counters.as_dict()["context_used"] == 250
    assert counters.as_dict()["context_window"] == 1000


def test_invalid_values_are_ignored():
    counters = TokenCounters()
    counters.record_totals(input=-1, output=True, cache_read="7", cache_write=2.5)
    counters.record_context(used=-5, window=float("nan"))
    assert counters.as_dict() == dict.fromkeys(KEYS)

