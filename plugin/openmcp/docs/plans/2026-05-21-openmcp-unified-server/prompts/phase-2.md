You own Phase 2 of the openmcp unified-server plan. 3 tasks.

## Phase
Add retry layer + single FastMCP tool surface + CLI entry. Backends from Phase 1 are reused unchanged.

## Tasks
- task-1: Create `openmcp/src/openmcp/retry.py` exposing `async def run_with_retry(execute_fn, params, max_retries: int, retry_base_ms: int) -> dict`.
  - Loop while `result.outcome == "RETRYABLE"` and `attempts <= max_retries`.
  - Sleep `min(retry_base_ms * 2**attempt, 8000)` ms ± 20% jitter before each retry (not before attempt 1).
  - On retry, mutate `params.SESSION_ID` to the last attempt's `SESSION_ID` if non-empty (preserve agent context).
  - Between attempts: best-effort kill any leftover child subprocesses spawned by backend (on Windows, use `taskkill /F /T /PID <pid>` against tracked PIDs if backend exposes them; otherwise rely on backend's own cleanup — document as such).
  - Return success dict `{success: True, SESSION_ID, agent_messages, attempts}` when `outcome == "OK"` (treat warning as success but include `warning` field).
  - Return failure dict `{success: False, error, attempts}` on `FATAL` or exhausted retries.
- task-2: Create `openmcp/src/openmcp/server.py` exposing FastMCP instance `mcp = FastMCP("openmcp")` plus `@mcp.tool` `run(backend: Literal["agy","codex"], PROMPT: str, cd: Path, SESSION_ID: str = "", model: str = "", profile: str = "mcp-execution", max_retries: int = 1, retry_base_ms: int = 1000) -> Dict[str, Any]`.
  - Build `AgyParams` or `CodexParams` from inputs (ignore `profile` for agy).
  - Dispatch via `retry.run_with_retry`.
  - Tool description briefly notes both backends and retry/SESSION_ID behavior.
- task-3: Create `openmcp/src/openmcp/cli.py` with `def main() -> None: server.mcp.run(transport="stdio")`. Confirm `pyproject.toml` `[project.scripts]` already declares `openmcp = "openmcp.cli:main"` (added in Phase 1); fix if missing.

## Context
- Phase 1 already created `BackendResult`, `AgyParams`, `CodexParams`, and both backends' `execute` functions. Import them as `from openmcp.backends.agy import execute as agy_execute, AgyParams` and similar for codex.
- Reference legacy FastMCP wiring: `agymcp/src/agymcp/server.py`, `codexmcp/src/codexmcp/server.py` (already extracted in Phase 1 — do NOT re-touch legacy).
- Design: `docs/plans/2026-05-21-openmcp-unified-server-design.md` §Retry Loop, §Tool Signature.

## Files
- openmcp/src/openmcp/retry.py
- openmcp/src/openmcp/server.py
- openmcp/src/openmcp/cli.py
- openmcp/pyproject.toml (only if scripts entry missing)

## Done When
- `.venv/Scripts/python.exe -c "import openmcp.server; import openmcp.retry; import openmcp.cli; print(openmcp.server.run.__doc__ or 'ok')"` succeeds in the existing venv at repo root (`C:/Users/ngosi/.mcp-servers/openmcp/.venv`).
- Backoff math test: write inline test that calls `run_with_retry` with a stub `execute_fn` returning RETRYABLE then OK; assert returned `attempts == 2` and `SESSION_ID` from the first attempt is reused.
- Fatal test: stub returns FATAL once; asserts `attempts == 1`, `success == False`.
- Tool signature exactly matches design.

## Rules
- Edit files directly; on-disk source is truth.
- Reuse `BackendResult` and Param dataclasses from Phase 1; do not redefine.
- No retry logic inside backends — backends classify only, retry layer loops.
- Do NOT modify any file inside `agymcp/` or `codexmcp/`.

## Per-Task Workflow (required)
For each task in order:
  1. Implement.
  2. Commit only that task's files with message `phase-2.task-<M>: <subject>`.
  3. Write `docs/plans/2026-05-21-openmcp-unified-server/notes/phase-2.task-<M>.md` (5-section decision note; use `- none`).
  4. Append commit row to `## COMMITS`.

## After All Tasks
- Write `docs/plans/2026-05-21-openmcp-unified-server/responses/phase-2.md` with full `# EXTERNAL RESPONSE` block.
- Emit the completion line as the final line of your reply.

## Report Format
Same `# EXTERNAL RESPONSE` block and completion line format as Phase 1.
