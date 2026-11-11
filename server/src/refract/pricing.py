"""Remote pricing table: fetch, validate, cache, and load."""

from __future__ import annotations

import http.client
import math
import os
import stat
import tempfile
import tomllib
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

PRICING_URL = "https://raw.githubusercontent.com/sitien173/refract/refs/heads/main/server/config/pricing.toml"
MAX_PRICING_BYTES = 64 * 1024
TIMEOUT_S = 10
_CACHE_FILE = "pricing.toml"


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Returning None makes urllib raise HTTPError for every 3xx, so the body is never resent.
        return None


PRICING_OPENER = urllib.request.build_opener(_RefuseRedirects())


class PricingError(Exception):
    """A pricing fetch or validation failure; `reason` is http, size, toml, or schema."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(slots=True, frozen=True)
class ModelPricing:
    input: float
    output: float
    cache_read: float
    cache_write: float


@dataclass(slots=True, frozen=True)
class PricingConfig:
    currency: str = "USD"
    models: dict[str, ModelPricing] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)


def canonical_model(raw: str, aliases: dict[str, str]) -> str:
    """Drop a provider prefix, then apply one exact-match alias lookup."""
    name = raw.rpartition("/")[2] or raw
    return aliases.get(name, name)


def parse_pricing(raw: Any) -> PricingConfig:
    if raw is None:
        return PricingConfig()
    if not isinstance(raw, dict) or set(raw) - {"currency", "models", "aliases"}:
        raise ValueError("Invalid pricing configuration")
    currency = raw.get("currency", "USD")
    models = raw.get("models", {})
    aliases = raw.get("aliases", {})
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("pricing.currency must be a non-empty string")
    if not isinstance(models, dict):
        raise ValueError("pricing.models must be a TOML table")
    if not isinstance(aliases, dict):
        raise ValueError("pricing.aliases must be a TOML table")
    parsed: dict[str, ModelPricing] = {}
    for model, values in models.items():
        if not isinstance(values, dict) or set(values) != {"input", "output", "cache_read", "cache_write"}:
            raise ValueError("Invalid pricing model settings")
        prices = []
        for key in ("input", "output", "cache_read", "cache_write"):
            value = values[key]
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < 0):
                raise ValueError("Pricing values must be non-negative numbers")
            prices.append(float(value))
        parsed[model] = ModelPricing(*prices)
    if any("/" in model for model in parsed):
        raise ValueError("Pricing model names must not contain '/'")
    for alias, target in aliases.items():
        if not alias or "/" in alias or alias in parsed:
            raise ValueError("Invalid pricing alias name")
        if not isinstance(target, str) or target not in parsed:
            raise ValueError("Pricing alias targets must name a priced model")
    return PricingConfig(currency=currency.strip(), models=parsed, aliases=dict(aliases))


def parse_pricing_file(data: bytes) -> PricingConfig:
    """Validate a pricing file; the reason is `toml` for syntax and `schema` for everything else."""
    try:
        raw = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as err:
        raise PricingError("toml") from err
    schema = raw.get("schema")
    if set(raw) != {"schema", "pricing"} or isinstance(schema, bool) or schema != 1 or not isinstance(schema, int):
        raise PricingError("schema")
    try:
        return parse_pricing(raw["pricing"])
    except ValueError as err:
        raise PricingError("schema") from err


def fetch_pricing(opener: Callable[..., Any] | None = None) -> bytes:
    """GET the pricing file; failures carry only a reason category, never the response body."""
    request = urllib.request.Request(PRICING_URL, headers={"User-Agent": "refract"}, method="GET")
    try:
        with (opener or PRICING_OPENER.open)(request, timeout=TIMEOUT_S) as response:
            if response.status != 200:
                raise PricingError("http")
            body = response.read(MAX_PRICING_BYTES + 1)
    except (OSError, http.client.HTTPException) as err:
        raise PricingError("http") from err
    if len(body) > MAX_PRICING_BYTES:
        raise PricingError("size")
    return body


def read_cache(home: Path) -> PricingConfig:
    """Load the cached pricing file; a missing, symlinked, non-regular, or invalid file yields empty pricing."""
    path = home / _CACHE_FILE
    try:
        if path.is_symlink():
            return PricingConfig()
        # NOFOLLOW closes the symlink race and NONBLOCK keeps a FIFO from hanging the open.
        flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                 | getattr(os, "O_BINARY", 0))
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return PricingConfig()
            data = handle.read(MAX_PRICING_BYTES + 1)
        if len(data) > MAX_PRICING_BYTES:
            return PricingConfig()
        return parse_pricing_file(data)
    except (OSError, PricingError):
        return PricingConfig()


def write_cache(home: Path, data: bytes) -> None:
    """Atomically replace the cached pricing file; callers pass only bytes that passed `parse_pricing_file`."""
    home.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=home, prefix=".pricing-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, home / _CACHE_FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
