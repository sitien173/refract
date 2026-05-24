You own Phase 3 of the openmcp unified-server plan. 4 tasks. Final phase.

## Phase
Validate the openmcp implementation against design's 5 success criteria. Write tests + validation report. No live CLI calls required (agy/codex CLIs may not be installed in this environment) — use stubs/monkeypatch for happy-path simulation; only bad-cd test against real `execute`.

## Tasks
- task-1: Create `openmcp/tests/__init__.py` (empty) and `openmcp/tests/test_smoke.py`. Tests:
  - `test_imports` — imports `openmcp.server`, `openmcp.retry`, `openmcp.cli`, `openmcp.backends.agy`, `openmcp.backends.codex`.
  - `test_tool_signature` — introspect `openmcp.server.run`; assert it has parameters exactly: `backend, PROMPT, cd, SESSION_ID, model, profile, max_retries, retry_base_ms`. Use `inspect.signature`.
- task-2: Add to `test_smoke.py`:
  - `test_retry_forwards_session_id` — async test using `run_with_retry` with a stub `execute_fn` returning `RETRYABLE` (with `SESSION_ID="sess-1"`) then `OK` (with `SESSION_ID="sess-2"`); assert returned `attempts==2`, `success is True`, `SESSION_ID=="sess-2"`, and that the second call received `params.SESSION_ID == "sess-1"`.
  - `test_fatal_returns_immediately` — stub returns FATAL; assert `attempts==1`, `success is False`.
  - `test_bad_cd_agy_fatal` and `test_bad_cd_codex_fatal` — await real `agy.execute` / `codex.execute` with non-existent `cd`; assert `outcome=="FATAL"` and `error_class=="bad_cd"`.
  - Use `pytest.mark.asyncio` (add `pytest-asyncio` to dev dep if missing) OR plain `asyncio.run` wrappers — your choice.
- task-3: Update `openmcp/pyproject.toml` to add `[project.optional-dependencies] dev = ["pytest>=8", "pytest-asyncio>=0.23"]` (if not already present). Reinstall venv if needed: `uv pip install --python .venv/Scripts/python.exe -e './openmcp[dev]'`. Run `.venv/Scripts/python.exe -m pytest openmcp/tests -x` and confirm all pass.
- task-4: Write `docs/plans/2026-05-21-openmcp-unified-server/validation-report.md` listing each design success criterion (numbered 1–5 from design §Success Criteria) with PASS/FAIL + evidence (command + 1-line observed output). Criteria:
  1. `uv pip install -e ./openmcp` succeeds and CLI declared.
  2. `run(backend="agy"|"codex", ...)` dispatch wired.
  3. Simulated transient → retries and recovers (`attempts==2`).
  4. Fatal `cd` → `attempts==1`.
  5. SESSION_ID from attempt 1 forwarded to attempt 2.

## Context
- Phase 1 + 2 source: `openmcp/src/openmcp/{backends,retry,server,cli}.py`.
- venv: `.venv/Scripts/python.exe` (Windows; use forward slashes in shell).
- Design: `docs/plans/2026-05-21-openmcp-unified-server-design.md`.

## Files
- openmcp/tests/__init__.py
- openmcp/tests/test_smoke.py
- openmcp/pyproject.toml (optional-dependencies update)
- docs/plans/2026-05-21-openmcp-unified-server/validation-report.md

## Done When
- `.venv/Scripts/python.exe -m pytest openmcp/tests -x` exits 0 with all tests passing.
- validation-report.md has PASS for all 5 criteria with commands + output snippets.

## Rules
- Do NOT call real `agy` / `codex` CLIs (likely missing) for happy-path; use stubs through `run_with_retry`.
- Do NOT modify legacy `agymcp/` or `codexmcp/`.
- One commit per task as before.

## Per-Task Workflow (required)
Same as prior phases. Commit messages `phase-3.task-<M>: <subject>`. Decision notes at `notes/phase-3.task-<M>.md`.

## After All Tasks
- Write `responses/phase-3.md` with full `# EXTERNAL RESPONSE` block.
- Emit completion line.
