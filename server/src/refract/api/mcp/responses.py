"""One byte limit, byte-safe truncation, result files and the MCP error boundary."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, get_args

from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent
from pydantic import ValidationError

from refract.logging_setup import get_logger
from refract.models import ERROR_CODES

log = get_logger("server")
MAX_RESPONSE_BYTES = 9_000
_INVALID_TOOL_ARGUMENTS = "Tool arguments are invalid."
_INVALID_TOOL_ARGUMENTS_ACTION = "Correct the arguments using the tool schema and call the tool again."
_ERROR_FIELDS = frozenset({"code", "message", "next_action"})
_ERROR_CODES = frozenset(get_args(ERROR_CODES))
class RefractError(ToolError):
    """A safe application error represented by one compact JSON object."""

    def __init__(
        self,
        code: str,
        message: str,
        next_action: str,
        retry_after_s: int | None = None,
    ) -> None:
        self.code = code if code in _ERROR_CODES else "internal_error"
        self.message = message
        self.next_action = next_action
        self.retry_after_s = retry_after_s if self.code == "targets_unavailable" else None
        super().__init__(self.to_json())

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
            "next_action": self.next_action,
        }
        if self.code == "targets_unavailable" and self.retry_after_s is not None:
            payload["retry_after_s"] = self.retry_after_s
        return payload

    def to_json(self) -> str:
        return _json(self.to_payload())


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _result_envelope_json(text: str, *, is_error: bool = False) -> str:
    result = CallToolResult(
        content=[TextContent(type="text", text=text)],
        is_error=is_error,
    )
    return json.dumps(
        result.model_dump(by_alias=True, mode="json", exclude_none=True),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def envelope_bytes(text: str, *, is_error: bool = False) -> int:
    """Size of the wire envelope of one text result; the byte limit applies to this size."""
    return len(_result_envelope_json(text, is_error=is_error).encode("utf-8"))


def _fits_response(text: str, *, is_error: bool = False) -> bool:
    return envelope_bytes(text, is_error=is_error) < MAX_RESPONSE_BYTES


def _refract_error_result(error: RefractError) -> CallToolResult:
    text = error.to_json()
    if not _fits_response(text, is_error=True):
        text = RefractError(
            "response_too_large",
            "The error response exceeded the supported size limit.",
            "Use the dashboard to inspect or reduce the oversized data before retrying.",
        ).to_json()
    return CallToolResult(content=[TextContent(type="text", text=text)], is_error=True)


def _render_payload(
    payload: Any,
    *,
    applied: tuple[str, str, str] | None = None,
) -> str:
    text = _json(payload)
    if _fits_response(text):
        return text
    if applied is None:
        raise RefractError(
            "response_too_large",
            "The response metadata exceeds the supported size limit.",
            "Use the dashboard to inspect or reduce the oversized data, then retry.",
        )
    operation, root_id, next_action = applied
    raise RefractError(
        "response_too_large",
        f"{operation} was applied; its response was too large. ID: {root_id}.",
        next_action.format(id=root_id),
    )


def _valid_refract_error(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    optional = {"retry_after_s"} if value.get("code") == "targets_unavailable" else set()
    if not _ERROR_FIELDS <= set(value) <= _ERROR_FIELDS | optional:
        return None
    if "retry_after_s" in value and (type(value["retry_after_s"]) is not int or value["retry_after_s"] < 1):
        return None
    if (
        not isinstance(value["code"], str)
        or value["code"] not in _ERROR_CODES
        or not isinstance(value["message"], str)
        or not isinstance(value["next_action"], str)
    ):
        return None
    return value


def _recognized_sdk_error(tool_name: str, text: str) -> dict[str, Any] | None:
    """Accept only the SDK's exact tool-error prefix and a valid Refract JSON suffix."""
    prefix = f"Error executing tool {tool_name}: "
    if not text.startswith(prefix):
        return None
    try:
        return _valid_refract_error(json.loads(text[len(prefix) :]))
    except (TypeError, json.JSONDecodeError):
        return None


def _validation_error_text(text: str) -> bool:
    first_line = text.splitlines()[0] if text else ""
    if first_line.startswith(("1 validation error for ", "ValidationError:")):
        return True
    count = first_line.split(" ", 1)[0]
    return count.isdigit() and " validation errors for " in first_line


def _request_id(ctx: Any) -> str:
    value = getattr(ctx, "request_id", None)
    if value is None:
        value = getattr(getattr(ctx, "request_context", None), "request_id", None)
    return str(value) if value is not None else ""


def _internal_error(request_id: str) -> RefractError:
    request_suffix = f" Request ID: {request_id[:128]}." if request_id else ""
    return RefractError(
        "internal_error",
        f"An unexpected internal error occurred.{request_suffix}",
        "Retry once, then report the request ID.",
    )


def _tool_name(ctx: Any) -> str:
    params = getattr(ctx, "params", None)
    if isinstance(params, Mapping) and isinstance(params.get("name"), str):
        return str(params["name"])
    return ""


def _raw_arguments(ctx: Any) -> Mapping[str, Any] | None:
    params = getattr(ctx, "params", None)
    if isinstance(params, Mapping):
        arguments = params.get("arguments", {})
        return arguments if isinstance(arguments, Mapping) else None
    arguments = getattr(params, "arguments", None)
    return arguments if isinstance(arguments, Mapping) else None


def _raw_argument_error(schema: Mapping[str, Any], arguments: Mapping[str, Any] | None) -> bool:
    if arguments is None:
        return False
    allowed = schema.get("properties", {})
    if any(name not in allowed for name in arguments):
        return True
    kinds = {"string": str, "integer": int, "boolean": bool}

    def scalar_kind(spec: Mapping[str, Any]) -> str | None:
        """The scalar type of a property; an optional property is `anyOf` its type and null."""
        if "type" in spec:
            return spec["type"] if spec["type"] in kinds else None
        return next((option["type"] for option in spec.get("anyOf", ()) if option.get("type") in kinds), None)

    if any(
        type(value) is not kinds[scalar_kind(allowed[name])]
        for name, value in arguments.items()
        if scalar_kind(allowed[name]) is not None and value is not None
    ):
        return True
    for name, value in arguments.items():
        spec = allowed[name]
        if spec.get("type") != "array":
            continue
        if not isinstance(value, list) or len(value) > spec.get("maxItems", len(value)):
            return True
        item = spec.get("items", {})
        if item.get("type") in kinds and any(type(entry) is not kinds[item["type"]] for entry in value):
            return True
        if item.get("type") == "string" and any(
            not item.get("minLength", 0) <= len(entry) <= item.get("maxLength", len(entry)) for entry in value
        ):
            return True
    return False


def _normalize_tool_error(wire_result: Mapping[str, Any], tool_name: str, request_id: str) -> CallToolResult:
    content = wire_result.get("content", [])
    error_text = next(
        (
            str(item.get("text", ""))
            for item in content
            if isinstance(item, Mapping) and item.get("type") == "text"
        ),
        "",
    )
    payload = _recognized_sdk_error(tool_name, error_text)
    if payload is not None:
        return _refract_error_result(RefractError(**payload))
    prefix = f"Error executing tool {tool_name}: " if tool_name else ""
    if prefix and error_text.startswith(prefix) and _validation_error_text(error_text[len(prefix) :]):
        return _refract_error_result(
            RefractError(
                "invalid_request",
                _INVALID_TOOL_ARGUMENTS,
                _INVALID_TOOL_ARGUMENTS_ACTION,
            )
        )
    if prefix and error_text.startswith(prefix) and error_text[len(prefix) :].startswith("Unknown tool"):
        return _refract_error_result(
            RefractError(
                "invalid_request",
                "The requested tool is not available.",
                "Use one of the tools returned by tools/list.",
            )
        )
    log.warning(
        "MCP tool returned an unrecognized error",
        extra={"event": "mcp.tool_error_sanitized", "request_id": request_id, "tool": tool_name},
    )
    return _refract_error_result(_internal_error(request_id))


def _normalize_tool_result(result: Any, tool_name: str, request_id: str) -> Any:
    if isinstance(result, CallToolResult):
        wire_result: Mapping[str, Any] = result.model_dump(by_alias=True, mode="json", exclude_none=True)
    elif isinstance(result, Mapping):
        wire_result = result
    else:
        return result
    if wire_result.get("isError", wire_result.get("is_error", False)) is True:
        return _normalize_tool_error(wire_result, tool_name, request_id)

    serialized = json.dumps(wire_result, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) >= MAX_RESPONSE_BYTES:
        return _refract_error_result(
            RefractError(
                "response_too_large",
                "The response exceeds the supported size limit.",
                "Use the dashboard to inspect or reduce the oversized data before retrying.",
            )
        )
    return result


async def _dispatch_tool_request(
    ctx: Any, call_next: Callable[[Any], Awaitable[Any]], schemas: Mapping[str, Any],
) -> Any:
    if getattr(ctx, "method", "") != "tools/call":
        return await call_next(ctx)
    request_id = _request_id(ctx)
    tool_name = _tool_name(ctx)
    if tool_name in schemas and _raw_argument_error(schemas[tool_name], _raw_arguments(ctx)):
        return _refract_error_result(
            RefractError(
                "invalid_request",
                _INVALID_TOOL_ARGUMENTS,
                _INVALID_TOOL_ARGUMENTS_ACTION,
            )
        )
    try:
        result = await call_next(ctx)
    except asyncio.CancelledError:
        raise
    except ValidationError:
        return _refract_error_result(
            RefractError(
                "invalid_request",
                _INVALID_TOOL_ARGUMENTS,
                _INVALID_TOOL_ARGUMENTS_ACTION,
            )
        )
    except MCPError:
        raise
    except Exception as exc:
        log.warning(
            "MCP request failed before tool dispatch",
            extra={"event": "mcp.request_failed", "request_id": request_id, "error_type": type(exc).__name__},
        )
        return _refract_error_result(_internal_error(request_id))

    return _normalize_tool_result(result, tool_name, request_id)


def _error_boundary(ctx: Any, call_next: Callable[[Any], Awaitable[Any]], schemas: Mapping[str, Any]) -> Any:
    """Normalize SDK validation and ToolError results into compact JSON isError results."""
    return _dispatch_tool_request(ctx, call_next, schemas)


def materialize_result(results_dir: Path, job_id: str, text: str) -> Path:
    """Write `results/<job_id>.md` by temp-file write and rename; the path stays inside `results_dir`."""
    if not job_id or Path(job_id).name != job_id or job_id in {".", ".."}:
        raise ValueError("job_id is not a plain file name")
    results_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temp = tempfile.mkstemp(dir=results_dir, prefix=".result.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temp, results_dir / f"{job_id}.md")
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return results_dir / f"{job_id}.md"


def _prefix(data: bytes, size: int) -> str:
    """The longest whole-character prefix of at most `size` UTF-8 bytes."""
    return data[:size].decode("utf-8", errors="ignore")


def render_result(payload: dict[str, Any], full: str, results_dir: Path, job_id: str) -> str:
    """Render `payload` whose `result` is `full`; truncate to fit and add `result_path` when it does not.

    `response_too_large` only when the metadata alone, with an empty result, exceeds the byte limit.
    """
    text = _json(payload)
    if _fits_response(text):
        return text
    payload = {**payload, "result": "", "truncated": True, "result_path": str(results_dir / f"{job_id}.md")}
    if not _fits_response(_json(payload)):
        raise RefractError(
            "response_too_large",
            "The response metadata exceeds the supported size limit.",
            "Use the dashboard to inspect or reduce the oversized data, then retry.",
        )
    data = full.encode("utf-8")
    payload["result_path"] = str(materialize_result(results_dir, job_id, full))  # same path as checked above
    low, high = 0, len(data)
    while low < high:
        middle = (low + high + 1) // 2
        payload["result"] = _prefix(data, middle)
        if _fits_response(_json(payload)):
            low = middle
        else:
            high = middle - 1
    payload["result"] = _prefix(data, low)
    return _json(payload)
