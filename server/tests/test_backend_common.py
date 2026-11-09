"""Shared backend token helpers used by the Claude parser."""

from refract.backends._common import as_int, read_usage


def test_read_usage_normalizes_input_and_keeps_malformed_components_visible():
    usage = read_usage({
        "input_tokens": 10, "cache_read_input_tokens": 20,
        "cache_creation_input_tokens": 3, "output_tokens": 4,
    })
    assert (usage.input, usage.output, usage.cache_read, usage.cache_write, usage.observed) == (33, 4, 20, 3, True)

    no_input = read_usage({"cache_read_input_tokens": 5})
    assert no_input.input is None
    assert no_input.cache_read == 5
    assert no_input.observed is True

    malformed = read_usage({"input_tokens": "x", "output_tokens": 2})
    assert malformed.input is None
    assert malformed.output == 2
    assert malformed.observed is True

    assert read_usage({}).observed is False


def test_as_int_rejects_bool_negative_and_non_int():
    assert as_int(3) == 3
    assert as_int(True) is None
    assert as_int(-1) is None
    assert as_int("3") is None
