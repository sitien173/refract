## Original User Request
Complete backlog item B-002 by implementing the project-context-instructions plan.

## Phase
Materialize agy instructions and document the complete feature.

## Tasks
- task-1: Generalize Phase 4 helpers for agy `GEMINI.md` without composition.
- task-2: Route agy attempts and startup sweeping through shared safety machinery.
- task-3: Document `context_init`, its resource, and every backend mechanism.

## Context
Agy reads `GEMINI.md` and `AGENTS.md` additively. Generate instruction-only `GEMINI.md`. Reuse the exact Git locking, exclusion, refusal, quarantine, and cleanup behavior. Backlog B-001 already added `--new-project` for new agy sessions, so the original plan's agy limitation is resolved. Document current behavior instead of the obsolete limitation.

## Files
- `src/openmcp/context_files.py`
- `src/openmcp/execution.py`
- `src/openmcp/runtime.py`
- `tests/test_context_files.py`
- `tests/test_execution.py`
- `CLI_ARGUMENTS.md`
- `README.md`

## Done When
- Generated `GEMINI.md` contains only marker and instruction.
- Existing `AGENTS.md` remains untouched.
- Tracked or foreign `GEMINI.md` refuses safely.
- Generated `GEMINI.md` stays Git-invisible and cleans identically.
- Documentation covers the tool, resource, and all backends.
- Documentation states new agy sessions use `--new-project`.
- `uv run pytest tests/test_context_files.py tests/test_execution.py`
- `uv run pytest`

## Rules
Follow the supplied worker contract. Stay within scope. Maintain this phase's
`notes.md` and `journal.md`.

## Response Format
Return the ERP `# EXTERNAL RESPONSE` block and matching status line.
