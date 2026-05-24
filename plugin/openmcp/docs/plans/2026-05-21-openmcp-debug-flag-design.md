# openmcp — `debug` flag for `run` tool (Design)

- Date: 2026-05-21
- Status: CONFIRMED (design)
- Sources: cross-validated via Codex + Gemini (narrow non-debug field-set question)

## Goal

Add `debug: bool = False` parameter to the unified `run` MCP tool. When `False` (default), return a token-light response with only essential control-flow fields. When `True`, return the full response (current behavior). Motivation: detailed agent output is already persisted by callers to `responses/phase-N.md`, so inline `agent_messages` is redundant token cost on most calls.

## Non-goals

- No change to backend `execute()` contract or `BackendResult`.
- No change to retry layer's internal return shape.
- No change to logging or persistence — only the dict returned to the MCP caller is filtered.

## Tool Signature (updated)

```python
run(
  backend: Literal["agy", "codex"],
  PROMPT: str,
  cd: Path,
  SESSION_ID: str = "",
  model: str = "",
  profile: str = "mcp-execution",
  max_retries: int = 1,
  retry_base_ms: int = 1000,
  debug: bool = False,   # NEW
) -> Dict[str, Any]
```

## Response shapes

### `debug=False` (default, token-light)

Always exactly three keys, on success and on failure:

```python
{
  "success": bool,
  "SESSION_ID": str,   # "" if backend produced none
  "error": str,        # "" on success, populated on failure
}
```

### `debug=True` (current behavior)

Full payload as today:

- Success: `{success: True, SESSION_ID, agent_messages, attempts, warning?}`
- Failure: `{success: False, error, attempts}`

## Implementation Sketch

Single change point in `openmcp/src/openmcp/server.py`:

```python
result = await run_with_retry(execute, params, max_retries, retry_base_ms)
if debug:
    return result
return {
    "success": result.get("success", False),
    "SESSION_ID": result.get("SESSION_ID", "") or "",
    "error": result.get("error", "") or "",
}
```

Retry layer (`retry.py`) and backends are untouched. The filter is applied at the tool surface only.

## Rationale (from CV)

- `success` (bool) is the stable control-flow primitive for orchestrating LLM callers — more robust than parsing an `outcome` string enum.
- `error` must remain in-band on failure; otherwise the caller cannot decide retry-vs-fix-input-vs-abort without reading external files.
- `SESSION_ID` is required for multi-turn continuity.
- `agent_messages` is the largest token contributor and the redundant one (already persisted to `responses/phase-N.md` by the orchestration workflow). Dropping it in non-debug realizes the token saving.
- `attempts` and `warning` are diagnostic; useful when debugging, noise otherwise → debug-only.

## Success Criteria

1. `run(..., debug=False)` returns exactly the 3-key dict for both success and failure paths, for both `agy` and `codex` backends.
2. `run(..., debug=True)` returns the same dict as today (no field drift).
3. Default behavior of existing calls (no `debug` argument) becomes the token-light shape — this is an intentional breaking change to the response contract; document in the tool description and changelog.
4. Tool description mentions the flag and lists both shapes.
5. Existing pytest suite still passes; one new test asserts the non-debug shape and one asserts the debug shape.

## Out of Scope

- No per-field opt-in (e.g., `include_messages=True`). A single bool keeps the surface minimal; if needed later, expand to a `verbosity: Literal["minimal","standard","full"]`.
- No change to backend modules or retry layer.
