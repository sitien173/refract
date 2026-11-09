"""Flat token counters: six nullable integers, null when unknown, never zero-filled."""

import refract.telemetry as telemetry
from refract.telemetry import TokenCounters

KEYS = ("context_used", "context_window", "input", "output", "cache_read", "cache_write")


def test_new_counters_are_all_unknown():
    assert TokenCounters().as_dict() == dict.fromkeys(KEYS)


def test_measurement_model_is_gone():
    for name in ("Measurement", "TelemetryData", "TelemetryAccumulator", "flat_tokens"):
        assert not hasattr(telemetry, name)


def test_responses_sum_and_a_repeated_response_id_replaces_its_earlier_values():
    counters = TokenCounters()
    counters.record_response("a", input=10, output=1)
    counters.record_response("a", input=12, output=3)
    counters.record_response("b", input=5, output=2, cache_read=4)
    assert counters.as_dict() == {
        "context_used": None,
        "context_window": None,
        "input": 17,
        "output": 5,
        "cache_read": 4,
        "cache_write": None,
    }


def test_reported_zero_is_kept_and_unreported_field_stays_null():
    counters = TokenCounters()
    counters.record_response("a", input=0, output=0)
    assert counters.as_dict()["input"] == 0
    assert counters.as_dict()["cache_write"] is None


def test_backend_totals_override_summed_responses_per_field():
    counters = TokenCounters()
    counters.record_response("a", input=10, output=1, cache_read=3)
    counters.record_totals(input=40, output=9)
    assert counters.as_dict()["input"] == 40
    assert counters.as_dict()["output"] == 9
    assert counters.as_dict()["cache_read"] == 3


def test_context_keeps_latest_value_and_none_leaves_it_unchanged():
    counters = TokenCounters()
    counters.record_context(used=100, window=1000)
    counters.record_context(used=250)
    assert counters.as_dict()["context_used"] == 250
    assert counters.as_dict()["context_window"] == 1000
    counters.clear_context()
    assert counters.as_dict()["context_used"] is None
    assert counters.as_dict()["context_window"] == 1000


def test_invalid_values_are_ignored():
    counters = TokenCounters()
    counters.record_response("a", input=-1, output=True, cache_read="7", cache_write=2.5)
    counters.record_context(used=-5, window=float("nan"))
    assert counters.as_dict() == dict.fromkeys(KEYS)


def test_has_any_reports_whether_any_counter_is_known():
    counters = TokenCounters()
    assert not counters.has_any()
    counters.record_context(window=1000)
    assert counters.has_any()
