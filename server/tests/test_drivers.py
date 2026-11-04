from refract.backends import BackendResult
from refract.drivers import _normalize

TOKEN_KEYS = ("context_used", "context_window", "input", "output", "cache_read", "cache_write")


def test_normalize_preserves_backend_tokens() -> None:
    tokens = dict.fromkeys(TOKEN_KEYS) | {"input": 17}
    result = _normalize(BackendResult(
        outcome="OK",
        SESSION_ID="session",
        agent_messages="done",
        error="",
        error_class="",
        tokens=tokens,
    ))

    assert result.tokens == tokens


def test_driver_result_tokens_default_to_all_unknown() -> None:
    from refract.drivers import DriverResult

    result = DriverResult("SUCCESS", "", "", "", "")

    assert result.tokens == dict.fromkeys(TOKEN_KEYS)
