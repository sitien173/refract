"""Best-effort ERP-aware response compression."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from openmcp.logging_setup import get_logger

log = get_logger("compression")

_AVAILABLE: bool | None = None
_ASYNC_CLIENT = None
_ENV_COMPRESS_RESPONSE = "OPENMCP_COMPRESS_RESPONSE"
_ENV_TTC_API_KEY = "OPENMCP_TTC_API_KEY"
_ENV_TTC_MODEL = "OPENMCP_TTC_MODEL"
_ENV_TTC_AGGRESSIVENESS = "OPENMCP_TTC_AGGRESSIVENESS"
_ENV_TTC_TIMEOUT_S = "OPENMCP_TTC_TIMEOUT_S"
_DEFAULT_MODEL = "bear-1.2"
_DEFAULT_AGGRESSIVENESS = 0.5
_DEFAULT_TIMEOUT_S = 10.0
_ERP_MARKER = "# EXTERNAL RESPONSE"
_SECTION_PATTERN = re.compile(r"^## ([^\n]+)\n", re.MULTILINE)
_COMPRESSIBLE_SECTIONS = {"SUMMARY", "NOTES"}


def _load_async_client() -> Any | None:
    global _AVAILABLE, _ASYNC_CLIENT

    if _AVAILABLE is not None:
        return _ASYNC_CLIENT
    try:
        from thetokencompany import AsyncTheTokenCompany
    except ImportError:
        _AVAILABLE = False
        _ASYNC_CLIENT = None
        log.info("thetokencompany is unavailable; response compression disabled")
        return None
    _AVAILABLE = True
    _ASYNC_CLIENT = AsyncTheTokenCompany
    return _ASYNC_CLIENT


def _env_truthy(name: str, env: dict[str, str]) -> bool:
    from openmcp.server import _env_truthy as server_env_truthy

    return server_env_truthy(name, env)


def _float_env(env: dict[str, str], name: str, default: float) -> float:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


async def _compress_fragment(client: Any, text: str, *, model: str, aggressiveness: float) -> str:
    if not text:
        return text
    result = await client.compress(text, model=model, aggressiveness=aggressiveness)
    return getattr(result, "output", text) or text


async def _compress_erp_text(client: Any, text: str, *, model: str, aggressiveness: float) -> str:
    marker_index = text.find(_ERP_MARKER)
    if marker_index < 0:
        return await _compress_fragment(client, text, model=model, aggressiveness=aggressiveness)

    prefix = text[:marker_index]
    erp_text = text[marker_index:]
    matches = list(_SECTION_PATTERN.finditer(erp_text))
    if not matches:
        return text

    parts: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(erp_text)
        parts.append(erp_text[cursor:body_start])
        body = erp_text[body_start:body_end]
        section_name = match.group(1).strip()
        if section_name in _COMPRESSIBLE_SECTIONS and body:
            body = await _compress_fragment(client, body, model=model, aggressiveness=aggressiveness)
        parts.append(body)
        cursor = body_end

    return prefix + "".join(parts)


async def _compress_with_client(
    client_cls: Any,
    text: str,
    *,
    api_key: str,
    model: str,
    aggressiveness: float,
) -> str:
    async with client_cls(api_key=api_key) as client:
        return await _compress_erp_text(client, text, model=model, aggressiveness=aggressiveness)


async def compress_response(text: str, env: dict[str, str]) -> str:
    if not _env_truthy(_ENV_COMPRESS_RESPONSE, env):
        return text
    api_key = env.get(_ENV_TTC_API_KEY, "").strip()
    if not api_key:
        return text
    client_cls = _load_async_client()
    if client_cls is None:
        return text
    if not text:
        return text

    model = env.get(_ENV_TTC_MODEL, "").strip() or _DEFAULT_MODEL
    aggressiveness = _float_env(env, _ENV_TTC_AGGRESSIVENESS, _DEFAULT_AGGRESSIVENESS)
    timeout_s = _float_env(env, _ENV_TTC_TIMEOUT_S, _DEFAULT_TIMEOUT_S)
    try:
        return await asyncio.wait_for(
            _compress_with_client(
                client_cls,
                text,
                api_key=api_key,
                model=model,
                aggressiveness=aggressiveness,
            ),
            timeout=timeout_s,
        )
    except asyncio.CancelledError:
        raise
    except TimeoutError:
        log.warning("Compression timed out after %.2fs; returning original response", timeout_s)
        return text
    except Exception as exc:
        log.warning("Compression failed; returning original response: %s", exc)
        return text


__all__ = ["compress_response"]
