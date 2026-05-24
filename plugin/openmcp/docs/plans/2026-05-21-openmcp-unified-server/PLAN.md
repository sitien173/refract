# openmcp — Unified MCP Server (Implementation Plan)

- Date: 2026-05-21
- Design: `docs/plans/2026-05-21-openmcp-unified-server-design.md`
- Status: ACTIVE
- Plan dir: `docs/plans/2026-05-21-openmcp-unified-server/`

## Scope

Build new package `openmcp/` exposing single FastMCP tool `run(backend, ...)` that dispatches to `agy` or `codex` backends (extracted verbatim from legacy packages) with retry-on-error and SESSION_ID continuity. Legacy `agymcp/` and `codexmcp/` packages remain untouched.

## Routing

All phases are back-side Python (FastMCP server, subprocess CLIs, retry loop). **Owner: Codex** for every phase. No front-side work; no cross-validation needed (design already cross-validated).

## Phases

### Phase 1: Package scaffold + backend extraction

**Owner:** `codex`

**Goal:** New `openmcp/` Python package buildable via `uv pip install -e ./openmcp`, with `agy` and `codex` backends extracted as `execute(params) -> BackendResult` async functions. No tool surface yet.

**Files:**
- Create: `openmcp/pyproject.toml`
- Create: `openmcp/src/openmcp/__init__.py`
- Create: `openmcp/src/openmcp/backends/__init__.py`
- Create: `openmcp/src/openmcp/backends/agy.py` (extracted from `agymcp/src/agymcp/server.py`)
- Create: `openmcp/src/openmcp/backends/codex.py` (extracted from `codexmcp/src/codexmcp/server.py`)
- Read for reference: `agymcp/src/agymcp/server.py`, `codexmcp/src/codexmcp/server.py`, both `pyproject.toml`s

**Tasks:**
1. Create `openmcp/pyproject.toml` mirroring deps from legacy packages (fastmcp, pywinpty for agy, etc.) and entry point `openmcp = "openmcp.cli:main"`.
2. Extract `agy` backend into `backends/agy.py` exposing `async def execute(params) -> BackendResult` — keep winpty / log-tail / model-patch logic verbatim. Define `BackendResult` dataclass with fields `outcome: Literal["OK","RETRYABLE","FATAL"]`, `SESSION_ID: str`, `agent_messages: str`, `error: str`, `error_class: str`.
3. Extract `codex` backend into `backends/codex.py` with same `execute` shape — keep JSON-line streaming verbatim.
4. Add error classification at the end of each backend per design table (FATAL: bad cd, CLI missing, auth, JSON decode at frame level; RETRYABLE: timeout, reconnecting, rate limit; OK-with-warning: messages but no SESSION_ID).

**Acceptance Criteria:**
- `uv pip install -e ./openmcp` succeeds.
- `python -c "from openmcp.backends import agy, codex; print(agy.execute, codex.execute)"` resolves.
- Each backend returns a `BackendResult` for happy path and at least one fatal path (bad cd).

**Reviewer Checklist:**
- `BackendResult` shape matches design §Backend Modules exactly.
- Error classification table matches design §Error Classification (no new categories, no missing rows).
- Winpty / JSON streaming logic copied without behavior change (diff against legacy `server.py` should show only structural moves, not logic edits).
- No FastMCP imports inside `backends/*` — they must be transport-agnostic.

**Integration Checks:**
- `uv pip install -e ./openmcp`
- `python -c "import openmcp; import openmcp.backends.agy; import openmcp.backends.codex"`

---

### Phase 2: Retry layer + unified tool surface

**Owner:** `codex`

**Goal:** `retry.py` wrapping backend `execute` with exponential backoff + SESSION_ID reuse. `server.py` exposing single `@mcp.tool run(...)` dispatching by `backend` field. `cli.py` entry point running the FastMCP server.

**Files:**
- Create: `openmcp/src/openmcp/retry.py`
- Create: `openmcp/src/openmcp/server.py`
- Create: `openmcp/src/openmcp/cli.py`

**Tasks:**
1. Implement `retry.py` with `async run_with_retry(backend_execute, params, max_retries, retry_base_ms)`: loop on `RETRYABLE`, sleep `min(retry_base_ms * 2**attempt, 8000)` ± 20% jitter, reuse `SESSION_ID` from partial attempt into next params, terminate child process tree between attempts (Windows `taskkill /F /T` fallback for PTY orphans), discard partial stream buffers, return `{success, SESSION_ID, agent_messages, attempts}` or `{success: False, error, attempts}`.
2. Implement `server.py`: FastMCP instance + single `@mcp.tool` `run(backend: Literal["agy","codex"], PROMPT, cd, SESSION_ID="", model="", profile="mcp-execution", max_retries=1, retry_base_ms=1000)` dispatching to `backends.agy.execute` or `backends.codex.execute` via `retry.run_with_retry`. Map `model` → agy `MODEL` / codex `--model`; ignore `profile` for agy.
3. Implement `cli.py` `main()` → `server.mcp.run()`; wire `[project.scripts]` `openmcp = "openmcp.cli:main"`.

**Acceptance Criteria:**
- `openmcp` CLI starts FastMCP server without error.
- `run(backend="agy", ...)` and `run(backend="codex", ...)` produce same shape as current standalone tools' returns on happy path.
- Simulated transient (`RETRYABLE` injected) retries up to `max_retries` and then succeeds when injection clears.
- Fatal error (bad `cd`) returns immediately with `attempts=1`.
- `SESSION_ID` from attempt 1 passed into attempt 2 params on retry (verified by log or unit test).

**Reviewer Checklist:**
- Tool signature exactly matches design §Tool Signature.
- Return shape matches design (success vs failure shapes both correct, both include `attempts`).
- Backoff math: base × 2^attempt, ±20% jitter, cap 8000 ms.
- `SESSION_ID` reuse path verified.
- Subprocess cleanup between retries actually runs (no orphan PIDs left after a forced retry test).

**Integration Checks:**
- `uv pip install -e ./openmcp`
- `openmcp --help` (or whatever FastMCP exposes) returns 0
- Smoke: invoke `run` via Python harness against a no-op `cd` to confirm dispatch wiring

---

### Phase 3: End-to-end validation

**Owner:** `codex`

**Goal:** Verify all 5 design success criteria with concrete runs; write a short validation report.

**Files:**
- Create: `openmcp/tests/test_smoke.py` (or scratch script under `openmcp/scripts/`)
- Create: `docs/plans/2026-05-21-openmcp-unified-server/validation-report.md`

**Tasks:**
1. Add smoke test/script exercising both backends end-to-end (real CLI calls against a tiny prompt and a known-good `cd`).
2. Add a forced-retry test: monkeypatch backend `execute` to return `RETRYABLE` once then `OK`; assert `attempts == 2` and `SESSION_ID` from attempt 1 was forwarded.
3. Add a fatal test: pass non-existent `cd`; assert `attempts == 1`, `success == False`.
4. Write `validation-report.md` listing each of the 5 design success criteria with PASS/FAIL + evidence (command + observed output snippet).

**Acceptance Criteria:**
- All 5 design success criteria documented as PASS in `validation-report.md`.
- Smoke + retry + fatal tests pass.

**Reviewer Checklist:**
- Validation report covers each numbered success criterion from design §Success Criteria.
- Retry test actually forwards `SESSION_ID` (asserted, not just observed).
- Fatal test asserts `attempts == 1` (not `<= 1`).

**Integration Checks:**
- `cd openmcp && pytest -x` (or equivalent script run)
- `openmcp` CLI launches cleanly

## Out of Scope

- Modifying legacy `agymcp/` or `codexmcp/`.
- Auto-routing between backends.
- Streaming output to MCP caller.
- Replacing legacy entry points in user MCP config (separate manual step).
