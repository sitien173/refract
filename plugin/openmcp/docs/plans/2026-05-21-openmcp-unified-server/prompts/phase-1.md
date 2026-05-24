You own Phase 1 of the openmcp unified-server plan. 3 tasks.

## Original User Request
Merge legacy `agymcp` and `codexmcp` FastMCP servers into a single new `openmcp` package exposing one tool that dispatches to either backend, with retry + SESSION_ID continuity. Legacy packages untouched.

## Phase
Scaffold the new `openmcp/` Python package and extract `agy` + `codex` backends as async `execute(params) -> BackendResult` functions. No FastMCP tool surface in this phase.

## Tasks
- task-1: Create `openmcp/pyproject.toml`, `src/openmcp/__init__.py`, `src/openmcp/backends/__init__.py`. Buildable via `uv pip install -e ./openmcp`. Deps mirror legacy packages (mcp[cli]>=1.21.2, pydantic>=2, pywinpty>=2 on win32). Entry point `openmcp = "openmcp.cli:main"` declared even though `cli.py` does not exist yet — Phase 2 adds it; for Phase 1, ensure the package itself imports cleanly without invoking the entry point.
- task-2: Create `src/openmcp/backends/agy.py`. Extract logic from `agymcp/src/agymcp/server.py` verbatim (winpty path on Windows, log-file path elsewhere, model patch, session-id extraction). Expose `async def execute(params) -> BackendResult`. Define `BackendResult` dataclass in `backends/__init__.py` (or a `_types.py`) with fields: `outcome: Literal["OK","RETRYABLE","FATAL"]`, `SESSION_ID: str`, `agent_messages: str`, `error: str`, `error_class: str`. `params` is a small dataclass/TypedDict with `PROMPT, cd, SESSION_ID, model` for agy.
- task-3: Create `src/openmcp/backends/codex.py`. Extract logic from `codexmcp/src/codexmcp/server.py` verbatim (JSON-line streaming, reconnecting tolerance, thread_id capture). Expose same `async def execute(params) -> BackendResult` shape. `params` includes `PROMPT, cd, SESSION_ID, model, profile`.

## Error Classification (apply at end of each backend)
| Condition | Class |
|---|---|
| `cd` missing, CLI not on PATH | FATAL |
| Invalid model/profile, auth errors | FATAL |
| JSON decode at frame level (codex only) | FATAL |
| Subprocess timeout, `Reconnecting...`, model rate limit / 5xx | RETRYABLE |
| No `agent_messages` returned | RETRYABLE (mark `outcome=RETRYABLE`, fill `error`) |
| No `SESSION_ID` but `agent_messages` present | OK (set `error="warning: no SESSION_ID"`, `error_class="warning"`) |
| Happy path | OK |

## Context
- Legacy source (read for verbatim extraction, do NOT modify):
  - `agymcp/src/agymcp/server.py`
  - `codexmcp/src/codexmcp/server.py`
  - `agymcp/pyproject.toml`
  - `codexmcp/pyproject.toml`
- Design doc: `docs/plans/2026-05-21-openmcp-unified-server-design.md`
- Plan: `docs/plans/2026-05-21-openmcp-unified-server/PLAN.md`

## Files
- openmcp/pyproject.toml
- openmcp/src/openmcp/__init__.py
- openmcp/src/openmcp/backends/__init__.py
- openmcp/src/openmcp/backends/agy.py
- openmcp/src/openmcp/backends/codex.py
- (optional) openmcp/src/openmcp/backends/_types.py

## Done When
- `uv pip install -e ./openmcp` succeeds from repo root.
- `python -c "from openmcp.backends import agy, codex; from openmcp.backends import BackendResult; print(agy.execute, codex.execute, BackendResult)"` runs without error.
- Each backend, when called with a non-existent `cd`, returns `BackendResult(outcome="FATAL", error_class="bad_cd", ...)` (or equivalent class label) and does not raise.
- No FastMCP imports inside `backends/*` — they must be transport-agnostic.

## Rules
- Edit files directly with your write tools; on-disk files are the source of truth.
- Do not duplicate file content in the response.
- Do not redesign the phase or produce a reference prototype.
- Do NOT modify any file inside `agymcp/` or `codexmcp/`.
- If anything is unclear, list it under CLARIFICATIONS NEEDED and stop.

## Per-Task Workflow (required)
For each task in order:
  1. Implement the task.
  2. `git add` only files you touched for this task and commit with message `phase-1.task-<M>: <one-line subject>`. Capture the commit hash.
  3. Write `docs/plans/2026-05-21-openmcp-unified-server/notes/phase-1.task-<M>.md` (decision note) with sections: Decisions made (not in spec), Spec deviations, Tradeoffs accepted, Assumptions, Follow-ups for human. Use `- none` for empty sections.
  4. Append this task's row to `## COMMITS` in your response.

## After All Tasks
- Write `docs/plans/2026-05-21-openmcp-unified-server/responses/phase-1.md` containing the full `# EXTERNAL RESPONSE` block.
- Emit the completion line as the final line of your reply.

## Report Format
# EXTERNAL RESPONSE

## SUMMARY
[one sentence]

## FILES MODIFIED
| Action  | Path     | Change |
|---------|----------|--------|

## COMMITS
- phase-1.task-1: <hash>  <subject>
- phase-1.task-2: <hash>  <subject>
- phase-1.task-3: <hash>  <subject>

## SPEC COMPLIANCE
- Meets Spec? YES | WITH_DEBT | NO
- Explanation: [one line]

## CLARIFICATIONS NEEDED
None (or list)

## NEXT
TASK_COMPLETE | CONTINUE_SESSION | HANDOVER_TO_CLAUDE

---
Phase 1 completed. Commit hashes: [...]. SessionID: "<id>". Note files: [...]. Response file: docs/plans/2026-05-21-openmcp-unified-server/responses/phase-1.md.
