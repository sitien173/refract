You own one implementation phase with 3 related tasks.

## Original User Request
Add a live integration test that exercises both `agy` and `codex` backends end-to-end via `openmcp.backends.{agy,codex}.execute`, filling the gap deferred in the prior unified-server plan.

## Phase
Register a pytest `live` marker (default-skipped) and add one live integration test module for both backends.

## Tasks
- task-1: In `C:/syncthing/Sync/.mcp-servers/openmcp/openmcp/pyproject.toml`, add a `[tool.pytest.ini_options]` table registering a `live` marker and `addopts = "-m 'not live'"` so default `pytest` skips it. Do not change existing tables.
- task-2: Create `C:/syncthing/Sync/.mcp-servers/openmcp/openmcp/tests/test_live_backends.py` with two `@pytest.mark.live` `@pytest.mark.asyncio` tests — one for `agy_execute(AgyParams(...))`, one for `codex_execute(CodexParams(...))`. Prompt each with "Reply with exactly the word PONG and nothing else." and `cd=Path.cwd()`. On `outcome == "FATAL"` with `error_class in {"missing_cli", "bad_cd"}` → `pytest.skip(reason)`. On any other FATAL → assertion failure. On `outcome == "OK"` → assert `agent_messages` is non-empty, contains `"PONG"` (case-insensitive), and `SESSION_ID` is non-empty.
- task-3: Sanity-check from `C:/syncthing/Sync/.mcp-servers/openmcp/openmcp/`: run `.venv/Scripts/python -m pytest -q` (must pass with 2 deselected; no `PytestUnknownMarkWarning`) and `.venv/Scripts/python -m pytest -m live -v` (must either skip with `missing_cli`/`bad_cd` reason or pass — never an unexpected fail). Record outcomes in the task-3 decision note. No code change in this task unless the runs reveal an issue.

## Context
Existing pyproject (truncated):
```
[project]
name = "openmcp"
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]
```
No `[tool.pytest.ini_options]` block exists yet — adding one is safe.

Existing test pattern (from `openmcp/tests/test_smoke.py`):
```
@pytest.mark.asyncio
async def test_bad_cd_agy_fatal() -> None:
    bad = Path("C:/definitely/not/real/path")
    out = await agy_execute(AgyParams(PROMPT="x", cd=bad))
    assert out.outcome == "FATAL"
    assert out.error_class == "bad_cd"
```

Backend signatures (from `src/openmcp/backends/{agy,codex}.py`):
- `AgyParams(PROMPT: str, cd: Path, SESSION_ID: str = "", model: str = "")`
- `CodexParams(PROMPT: str, cd: Path, SESSION_ID: str = "", model: str = "", profile: str = "mcp-execution")`
- Both `execute(params)` return `BackendResult(outcome, SESSION_ID, agent_messages, error, error_class)`.
- Missing CLI on PATH already returns `outcome="FATAL", error_class="missing_cli"`.

## Files
- C:/syncthing/Sync/.mcp-servers/openmcp/openmcp/pyproject.toml
- C:/syncthing/Sync/.mcp-servers/openmcp/openmcp/tests/test_live_backends.py

## Done When
- `cd C:/syncthing/Sync/.mcp-servers/openmcp/openmcp && .venv/Scripts/python -m pytest -q` → all existing tests pass; 2 live deselected; no PytestUnknownMarkWarning.
- `cd C:/syncthing/Sync/.mcp-servers/openmcp/openmcp && .venv/Scripts/python -m pytest -m live -v` → 2 passed or 2 skipped with a clear reason. No unexpected failures.

## Rules
- Edit files directly with your write tools; on-disk files are the source of truth.
- Do not duplicate file content in the response.
- Do not redesign the phase or produce a reference prototype.
- If anything is unclear, list it under CLARIFICATIONS NEEDED and stop.
- Context excerpts are reference only — never pre-write new file contents in the prompt.
- All file paths in this prompt are absolute — do not reinterpret them as relative.

## Per-Task Workflow (required)
For each task in order:
  1. Implement the task.
  2. `git add` only files you touched for this task and commit with message `phase-1.task-<M>: <one-line subject>`. Capture the commit hash.
  3. Write `C:/syncthing/Sync/.mcp-servers/openmcp/docs/plans/2026-05-23-openmcp-live-integration-test/notes/phase-1.task-<M>.md` (decision note) with sections: Decisions made (not in spec), Spec deviations, Tradeoffs accepted, Assumptions, Follow-ups for human. Use `- none` for empty sections.
  4. Append this task's row to `## COMMITS` in your response.

Note: task-3 is a verification task. If both pytest runs pass cleanly, the task-3 commit can be the decision-note file itself (and any small fixes if you found a defect).

## After All Tasks
- Write `C:/syncthing/Sync/.mcp-servers/openmcp/docs/plans/2026-05-23-openmcp-live-integration-test/responses/phase-1.md` containing the full `# EXTERNAL RESPONSE` block (same content you return inline).
- Emit the completion line as the final line of your reply.

## Report Format
# EXTERNAL RESPONSE

## META
- Phase: 1
- Owner: codex
- SessionID: <your current session id>
- Started: <ISO8601>
- Finished: <ISO8601>
- Plan dir: docs/plans/2026-05-23-openmcp-live-integration-test

## SUMMARY
[one sentence]

## FILES MODIFIED
| Action  | Path     | Change |
|---------|----------|--------|

## COMMITS
- phase-1.task-1: <hash>  <subject>
- phase-1.task-2: <hash>  <subject>
- phase-1.task-3: <hash>  <subject>

## NOTES
- docs/plans/2026-05-23-openmcp-live-integration-test/notes/phase-1.task-1.md
- docs/plans/2026-05-23-openmcp-live-integration-test/notes/phase-1.task-2.md
- docs/plans/2026-05-23-openmcp-live-integration-test/notes/phase-1.task-3.md

## SPEC COMPLIANCE
- Meets Spec? YES | WITH_DEBT | NO
- Explanation: [one line]

## CLARIFICATIONS NEEDED
None (or list questions; emit and stop if any)

## NEXT
TASK_COMPLETE | CONTINUE_SESSION | HANDOVER_TO_CLAUDE

---
Phase 1 completed. Response file: docs/plans/2026-05-23-openmcp-live-integration-test/responses/phase-1.md.
