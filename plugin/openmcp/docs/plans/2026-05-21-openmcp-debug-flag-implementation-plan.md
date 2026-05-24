# openmcp — `debug` flag implementation plan

- Date: 2026-05-21
- Design: `docs/plans/2026-05-21-openmcp-debug-flag-design.md`
- Status: ACTIVE (single phase, flat plan)

## Scope

Add `debug: bool = False` to the `run` tool. Filter response to `{success, SESSION_ID, error}` when `False`; return full payload when `True`. Update tool docstring and tests.

## Routing

Single phase, ~10 LOC edit + test. Owner: **Claude** (trivial back-side change, well within "doc tweaks / one-line edits" scope per skill).

## Phase 1: Add debug flag and shape filter

**Owner:** `claude`

**Goal:** `run(..., debug=False)` returns 3-key dict; `run(..., debug=True)` returns full dict; tests pin both shapes.

**Files:**
- Modify: `openmcp/src/openmcp/server.py`
- Modify: `openmcp/tests/test_smoke.py`

**Tasks:**
1. Add `debug: bool = False` parameter to `run` (last positional/keyword, after `retry_base_ms`). Update docstring + tool `description=` to explain both shapes.
2. After `result = await run_with_retry(...)`, branch: if `debug` return `result` unchanged; else return `{"success": result.get("success", False), "SESSION_ID": result.get("SESSION_ID", "") or "", "error": result.get("error", "") or ""}`.
3. Add `test_run_signature_includes_debug` updating the existing `test_tool_signature` to include the new `debug` param at the end, OR add a separate assertion.
4. Add `test_non_debug_shape_success` and `test_non_debug_shape_failure` and `test_debug_shape_passthrough` using monkeypatch on `agy_execute` (or `run_with_retry`) to inject a fake `BackendResult` / dict — keep tests sync via `asyncio.run` like existing ones.

**Acceptance Criteria:**
- `inspect.signature(openmcp.server.run).parameters` contains `debug` with default `False`.
- Calling `run(...)` with `debug=False` returns dict with exactly the keys `{"success","SESSION_ID","error"}` (no `agent_messages`, no `attempts`).
- Calling `run(..., debug=True)` returns the same dict shape as `run_with_retry` (passthrough — at minimum includes `success`, `SESSION_ID`, `attempts`).
- `.venv/Scripts/python.exe -m pytest openmcp/tests -x` passes.

**Reviewer Checklist:**
- Tool `description` text mentions `debug` flag and notes the breaking default change to slim response.
- Filter handles missing-key cases (`result` may lack `error` on success, lack `agent_messages` on failure).
- No edits to `retry.py` or `backends/*`.
- Existing 6 tests still pass.

**Integration Checks:**
- `cd C:/Users/ngosi/.mcp-servers/openmcp && .venv/Scripts/python.exe -m pytest openmcp/tests -x`
- `.venv/Scripts/python.exe -c "import inspect, openmcp.server; print(list(inspect.signature(openmcp.server.run).parameters))"`

## Out of Scope

- Backend or retry changes.
- Per-field opt-in / verbosity levels (design §Out of Scope).
- Updating any external MCP client config.
