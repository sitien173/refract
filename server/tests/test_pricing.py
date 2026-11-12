from __future__ import annotations

import asyncio
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from refract import pricing
from refract.config import load_config
from refract.runtime import Runtime
# Bound at import time so the autouse conftest stub on `refract.pricing.fetch_pricing` does not hide it.
from refract.pricing import (
    MAX_PRICING_BYTES,
    PRICING_URL,
    ModelPricing,
    PricingConfig,
    PricingError,
    canonical_model,
    fetch_pricing,
    parse_pricing,
    parse_pricing_file,
    read_cache,
    write_cache,
)


def test_parse_pricing_none_returns_defaults() -> None:
    assert parse_pricing(None) == PricingConfig()


def test_parse_pricing_reads_currency_and_models() -> None:
    raw = {"currency": " EUR ", "models": {"m": {"input": 1, "output": 2.5, "cache_read": 0, "cache_write": 4}}}
    assert parse_pricing(raw) == PricingConfig("EUR", {"m": ModelPricing(1.0, 2.5, 0.0, 4.0)})


@pytest.mark.parametrize(
    ("raw", "aliases", "expected"),
    [
        ("openai-codex/gpt-6-luna", {}, "gpt-6-luna"),
        ("a/b/m", {}, "m"),
        ("foo/", {}, "foo/"),
        ("Claude Opus 5.5", {"Claude Opus 5.5": "claude-opus-5-5"}, "claude-opus-5-5"),
        ("x/Claude Opus 5.5", {"Claude Opus 5.5": "claude-opus-5-5"}, "claude-opus-5-5"),
        ("", {}, ""),
        ("claude opus 5.5", {"Claude Opus 5.5": "claude-opus-5-5"}, "claude opus 5.5"),
    ],
    ids=["prefix", "nested-prefix", "trailing-slash", "alias", "prefix-and-alias",
         "empty", "case-sensitive"],
)
def test_canonical_model(raw, aliases, expected) -> None:
    assert canonical_model(raw, aliases) == expected


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ([], "Invalid pricing configuration"),
        ({"currency": 1}, "pricing.currency must be a non-empty string"),
        ({"models": []}, "pricing.models must be a TOML table"),
        ({"aliases": []}, "pricing.aliases must be a TOML table"),
        ({"models": {"m": {"input": 1}}}, "Invalid pricing model settings"),
        ({"models": {"m": {"input": "bad", "output": 0, "cache_read": 0, "cache_write": 0}}},
         "Pricing values must be non-negative numbers"),
    ],
    ids=["top-level", "currency-type", "models-type", "aliases-type", "model-shape", "price-type"],
)
def test_parse_pricing_validation_errors_keep_their_messages(raw, message) -> None:
    with pytest.raises(ValueError, match=message):
        parse_pricing(raw)


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {"extra": 1},
        {"currency": " "},
        {"models": []},
        {"models": {"m": {"input": 1}}},
        {"models": {"m": {"input": -1, "output": 0, "cache_read": 0, "cache_write": 0}}},
        {"models": {"m": {"input": True, "output": 0, "cache_read": 0, "cache_write": 0}}},
        {"models": {"m": {"input": float("inf"), "output": 0, "cache_read": 0, "cache_write": 0}}},
    ],
    ids=["not-table", "extra-key", "blank-currency", "models-not-table", "missing-price",
         "negative", "boolean", "infinite"],
)
def test_parse_pricing_rejects_invalid_input(raw) -> None:
    with pytest.raises(ValueError):
        parse_pricing(raw)


_VALID = b"""
schema = 1

[pricing]
currency = "USD"

[pricing.models.m]
input = 1
output = 2
cache_read = 3
cache_write = 4
"""


_ONE_MODEL = {"m": {"input": 1, "output": 0, "cache_read": 0, "cache_write": 0}}


def test_parse_pricing_reads_aliases() -> None:
    raw = {"models": _ONE_MODEL, "aliases": {"Display M": "m"}}
    assert parse_pricing(raw) == PricingConfig(
        "USD", {"m": ModelPricing(1.0, 0.0, 0.0, 0.0)}, {"Display M": "m"})


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"models": _ONE_MODEL, "aliases": []}, "pricing.aliases must be a TOML table"),
        ({"models": _ONE_MODEL, "aliases": {"A": 1}}, "alias targets must name a priced model"),
        ({"models": _ONE_MODEL, "aliases": {"": "m"}}, "Invalid pricing alias name"),
        ({"models": _ONE_MODEL, "aliases": {"A": "missing"}},
         "alias targets must name a priced model"),
        ({"models": {**_ONE_MODEL, "n": _ONE_MODEL["m"]}, "aliases": {"n": "m"}},
         "Invalid pricing alias name"),
        ({"models": {"p/m": _ONE_MODEL["m"]}}, "model names must not contain"),
        ({"models": _ONE_MODEL, "aliases": {"p/A": "m"}}, "Invalid pricing alias name"),
    ],
    ids=["not-table", "non-string-value", "empty-key", "unpriced-target", "key-is-model",
         "slash-in-model", "slash-in-alias"],
)
def test_parse_pricing_rejects_invalid_aliases(raw, message) -> None:
    with pytest.raises(ValueError, match=message):
        parse_pricing(raw)


def test_parse_pricing_file_maps_invalid_alias_to_schema() -> None:
    data = _VALID + b'\n[pricing.aliases]\n"A" = "missing"\n'
    with pytest.raises(PricingError) as error:
        parse_pricing_file(data)
    assert error.value.reason == "schema"


def test_parse_pricing_file_reads_aliases() -> None:
    data = _VALID + b'\n[pricing.aliases]\n"A" = "m"\n'
    assert parse_pricing_file(data).aliases == {"A": "m"}


def test_parse_pricing_file_accepts_valid_file() -> None:
    assert parse_pricing_file(_VALID) == PricingConfig("USD", {"m": ModelPricing(1.0, 2.0, 3.0, 4.0)})


@pytest.mark.parametrize(
    ("data", "reason"),
    [
        (b"\xff\xfe", "toml"),
        (b"schema = [", "toml"),
        (b"schema = 2\n[pricing]\n", "schema"),
        (b"schema = true\n[pricing]\n", "schema"),
        (b"schema = 1.0\n[pricing]\n", "schema"),
        (b"[pricing]\n", "schema"),
        (b"schema = 1\n", "schema"),
        (b"schema = 1\nextra = 1\n[pricing]\n", "schema"),
        (b"schema = 1\n[pricing.models.m]\ninput = -1\noutput = 0\ncache_read = 0\ncache_write = 0\n", "schema"),
        (b"schema = 1\n[pricing.models.m]\ninput = 1\n", "schema"),
        (b'schema = 1\n[pricing]\ncurrency = ""\n', "schema"),
    ],
    ids=["invalid-utf8", "invalid-toml", "schema-2", "schema-bool", "schema-float", "missing-schema",
         "missing-pricing", "extra-key", "negative-price", "missing-price", "blank-currency"],
)
def test_parse_pricing_file_rejects_with_reason(data: bytes, reason: str) -> None:
    with pytest.raises(PricingError) as error:
        parse_pricing_file(data)
    assert error.value.reason == reason


class _Response:
    def __init__(self, status: int = 200, body: bytes = b"") -> None:
        self.status = status
        self.body = body
        self.read_sizes: list[int] = []

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self.body if size < 0 else self.body[:size]


def _opener(response: _Response | Exception, requests: list | None = None):
    def opener(request, *, timeout):
        if requests is not None:
            requests.append((request, timeout))
        if isinstance(response, Exception):
            raise response
        return response
    return opener


def test_fetch_pricing_returns_body_with_fixed_request() -> None:
    requests: list = []
    response = _Response(200, _VALID)
    assert fetch_pricing(_opener(response, requests)) == _VALID
    (request, timeout), = requests
    assert request.full_url == PRICING_URL
    assert request.get_method() == "GET"
    assert request.data is None
    assert request.get_header("User-agent") == "refract"
    assert timeout == 10
    assert response.read_sizes == [MAX_PRICING_BYTES + 1]


@pytest.mark.parametrize("status", [204, 301, 404, 500])
def test_fetch_pricing_rejects_non_200_status(status: int) -> None:
    with pytest.raises(PricingError) as error:
        fetch_pricing(_opener(_Response(status, _VALID)))
    assert error.value.reason == "http"


@pytest.mark.parametrize(
    "failure",
    [
        urllib.error.HTTPError(PRICING_URL, 302, "secret-body", {}, None),
        urllib.error.URLError("secret-body"),
        TimeoutError("secret-body"),
        ConnectionResetError("secret-body"),
    ],
    ids=["http-error", "url-error", "timeout", "connection-reset"],
)
def test_fetch_pricing_maps_transport_failures_to_http_without_detail(failure: Exception) -> None:
    with pytest.raises(PricingError) as error:
        fetch_pricing(_opener(failure))
    assert error.value.reason == "http"
    assert "secret-body" not in str(error.value)


def test_fetch_pricing_accepts_body_at_the_limit_and_rejects_one_byte_more() -> None:
    assert len(fetch_pricing(_opener(_Response(200, b"x" * MAX_PRICING_BYTES)))) == MAX_PRICING_BYTES
    with pytest.raises(PricingError) as error:
        fetch_pricing(_opener(_Response(200, b"x" * (MAX_PRICING_BYTES + 1))))
    assert error.value.reason == "size"


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_pricing_opener_refuses_redirects(status: int, monkeypatch) -> None:
    requested_paths: list[str] = []

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            requested_paths.append(self.path)
            self.send_response(status if self.path == "/first" else 200)
            if self.path == "/first":
                self.send_header("Location", "/second")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setattr(pricing, "PRICING_URL", f"http://127.0.0.1:{server.server_port}/first")
        handlers = [h for h in pricing.PRICING_OPENER.handlers if isinstance(h, pricing._RefuseRedirects)]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), *handlers)
        with pytest.raises(PricingError) as error:
            fetch_pricing(opener.open)
        assert error.value.reason == "http"
        assert requested_paths == ["/first"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_conftest_blocks_module_level_fetch_pricing() -> None:
    with pytest.raises(PricingError) as error:
        pricing.fetch_pricing()
    assert error.value.reason == "http"


def test_read_cache_returns_defaults_when_missing(tmp_path) -> None:
    assert read_cache(tmp_path) == PricingConfig()
    assert read_cache(tmp_path / "absent") == PricingConfig()


def test_read_cache_loads_a_valid_file(tmp_path) -> None:
    (tmp_path / "pricing.toml").write_bytes(_VALID)
    assert read_cache(tmp_path) == PricingConfig("USD", {"m": ModelPricing(1.0, 2.0, 3.0, 4.0)})


@pytest.mark.parametrize(
    "data",
    [b"\xff", b"schema = [", b"schema = 2\n[pricing]\n", b"x" * (MAX_PRICING_BYTES + 1)],
    ids=["invalid-utf8", "invalid-toml", "wrong-schema", "oversize"],
)
def test_read_cache_returns_defaults_for_a_corrupt_file(tmp_path, data: bytes) -> None:
    (tmp_path / "pricing.toml").write_bytes(data)
    assert read_cache(tmp_path) == PricingConfig()


def test_read_cache_returns_defaults_for_a_directory(tmp_path) -> None:
    (tmp_path / "pricing.toml").mkdir()
    assert read_cache(tmp_path) == PricingConfig()


def test_read_cache_skips_a_symlinked_file(tmp_path) -> None:
    target = tmp_path / "elsewhere.toml"
    target.write_bytes(_VALID)
    try:
        (tmp_path / "pricing.toml").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not supported here")
    assert read_cache(tmp_path) == PricingConfig()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="named pipes are not supported here")
def test_read_cache_does_not_block_on_a_fifo(tmp_path) -> None:
    fifo = tmp_path / "pricing.toml"
    os.mkfifo(fifo)
    result: list[PricingConfig] = []
    reader = threading.Thread(target=lambda: result.append(read_cache(tmp_path)), daemon=True)
    reader.start()
    reader.join(2)
    blocked = reader.is_alive()
    if blocked:
        # Open the write end so the blocked reader returns and the thread does not leak.
        os.close(os.open(fifo, os.O_WRONLY))
        reader.join(2)
    assert not blocked
    assert result == [PricingConfig()]


def test_write_cache_round_trips_and_leaves_no_temp_file(tmp_path) -> None:
    home = tmp_path / "home"
    write_cache(home, _VALID)
    assert (home / "pricing.toml").read_bytes() == _VALID
    assert [path.name for path in home.iterdir()] == ["pricing.toml"]
    write_cache(home, _VALID + b"\n")
    assert [path.name for path in home.iterdir()] == ["pricing.toml"]
    assert read_cache(home).models["m"] == ModelPricing(1.0, 2.0, 3.0, 4.0)


def test_write_cache_failure_removes_temp_file_and_keeps_previous_cache(tmp_path, monkeypatch) -> None:
    write_cache(tmp_path, _VALID)

    def fail(*_args, **_kwargs):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="replace failed"):
        write_cache(tmp_path, b"new")
    assert [path.name for path in tmp_path.iterdir()] == ["pricing.toml"]
    assert (tmp_path / "pricing.toml").read_bytes() == _VALID


_RUNTIME_CONFIG = """[daemon]
default_profile = "test"
[[targets]]
id = "a"
backend = "codex"
[profiles.test]
consult = ["a"]
"""
_NEW = _VALID.replace(b"input = 1", b"input = 9")


def _runtime(tmp_path) -> Runtime:
    path = tmp_path / "config.toml"
    path.write_text(_RUNTIME_CONFIG)
    return Runtime(load_config(path))


async def _run_cycles(runtime: Runtime, monkeypatch, cycles: int) -> list[float]:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) >= cycles:
            raise asyncio.CancelledError

    monkeypatch.setattr("refract.runtime.asyncio.sleep", fake_sleep)
    with pytest.raises(asyncio.CancelledError):
        await runtime._refresh_pricing()
    return delays


def test_runtime_prices_from_the_cache_at_construction(tmp_path) -> None:
    home = tmp_path / "home"
    write_cache(home, _VALID)
    path = tmp_path / "config.toml"
    path.write_text(_RUNTIME_CONFIG)
    config = replace(load_config(path), home=home)
    runtime = Runtime(config)
    assert runtime.pricing.models["m"] == ModelPricing(1.0, 2.0, 3.0, 4.0)


@pytest.mark.asyncio
async def test_pricing_refresh_success_updates_cache_and_runtime(tmp_path, monkeypatch) -> None:
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(pricing, "fetch_pricing", lambda: _NEW)
    delays = await _run_cycles(runtime, monkeypatch, 1)
    assert delays == [24 * 3600]
    assert runtime.pricing.models["m"].input == 9.0
    assert read_cache(runtime.config.home).models["m"].input == 9.0


@pytest.mark.asyncio
async def test_pricing_refresh_failure_keeps_cache_and_runtime(tmp_path, monkeypatch) -> None:
    runtime = _runtime(tmp_path)
    write_cache(runtime.config.home, _VALID)
    runtime.pricing = read_cache(runtime.config.home)
    before = runtime.pricing
    for error in (pricing.PricingError("http"), ValueError("boom")):
        def failing(error=error):
            raise error
        monkeypatch.setattr(pricing, "fetch_pricing", failing)
        assert await _run_cycles(runtime, monkeypatch, 1) == [3600]
        assert runtime.pricing is before
        assert read_cache(runtime.config.home) == before
    monkeypatch.setattr(pricing, "fetch_pricing", lambda: b"schema = 2\n")
    assert await _run_cycles(runtime, monkeypatch, 1) == [3600]
    assert runtime.pricing is before


@pytest.mark.asyncio
async def test_pricing_refresh_logs_the_failure_reason(tmp_path, monkeypatch, caplog) -> None:
    runtime = _runtime(tmp_path)

    def failing():
        raise pricing.PricingError("size")

    monkeypatch.setattr(pricing, "fetch_pricing", failing)
    with caplog.at_level("WARNING"):
        await _run_cycles(runtime, monkeypatch, 1)
    record = next(r for r in caplog.records if getattr(r, "event", "") == "pricing.fetch_failed")
    assert record.reason == "size"


@pytest.mark.asyncio
async def test_pricing_refresh_swaps_runtime_when_the_cache_write_fails(tmp_path, monkeypatch) -> None:
    runtime = _runtime(tmp_path)
    monkeypatch.setattr(pricing, "fetch_pricing", lambda: _NEW)

    def failing_write(home, data):
        raise OSError("disk full")

    monkeypatch.setattr(pricing, "write_cache", failing_write)
    assert await _run_cycles(runtime, monkeypatch, 1) == [24 * 3600]
    assert runtime.pricing.models["m"].input == 9.0


@pytest.mark.asyncio
async def test_pricing_env_opt_out_makes_no_fetch_calls(tmp_path, monkeypatch) -> None:
    runtime = _runtime(tmp_path)
    calls = []
    monkeypatch.setattr(pricing, "fetch_pricing", lambda: calls.append(1) or _NEW)
    monkeypatch.setenv("REFRACT_PRICING_FETCH", "0")
    await runtime.start()
    try:
        await asyncio.sleep(0.05)
        assert runtime._pricing_task is None
    finally:
        await runtime.close()
    assert calls == []


@pytest.mark.asyncio
async def test_pricing_task_starts_and_close_does_not_wait_for_a_blocked_fetch(
    tmp_path, monkeypatch
) -> None:
    runtime = _runtime(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def blocked():
        entered.set()
        release.wait(10)
        return _NEW

    monkeypatch.setattr(pricing, "fetch_pricing", blocked)
    await runtime.start()
    try:
        assert runtime._pricing_task is not None
        await asyncio.wait_for(asyncio.to_thread(entered.wait, 5), 6)
        started = time.monotonic()
        await runtime.close()
        assert time.monotonic() - started < 2
        assert runtime._pricing_task is None
    finally:
        release.set()


def test_repository_pricing_file_is_valid_and_prices_a_model() -> None:
    path = Path(__file__).resolve().parents[1] / "config" / "pricing.toml"
    config = parse_pricing_file(path.read_bytes())
    assert config.models
    assert canonical_model("Claude Opus 5.5", config.aliases) == "claude-opus-5-5"
    assert canonical_model("openai-codex/gpt-6-luna", config.aliases) in config.models
