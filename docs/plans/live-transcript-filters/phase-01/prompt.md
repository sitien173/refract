# Phase 1 Prompt: Normalize Transcript Categories Safely

Implement Phase 1 from `docs/plans/live-transcript-filters/DESIGN.md` and
`PLAN.md`. Follow `/home/ngosi/projects/superpowers-ccg/shared/worker-contract.md`.
Do not commit.

## Objective

Add safe activity metadata to every newly normalized `tool.started` event and
extend `StreamRecorder` for future explicit reasoning-summary deltas. Do not add
frontend behavior or expose provider thinking.

## Existing dirty work

Preserve all unrelated changes. In particular, preserve the uncommitted Agy
protocol implementation and regression in:

- `src/openmcp/backends/agy.py`
- `tests/test_streaming_backends.py`

Keep current `step_update`, `agent_response`, tool parameters/output, result
response, and conversation-ID handling intact. Make only additive Phase 1 edits.

## Allowed files

- `src/openmcp/backends/__init__.py`
- `src/openmcp/backends/claude.py`
- `src/openmcp/backends/codex.py`
- `src/openmcp/backends/pi.py`
- `src/openmcp/backends/agy.py`
- `src/openmcp/streaming.py`
- `tests/test_streaming_backends.py`
- `tests/test_execution.py`
- `tests/test_streaming.py`
- `docs/plans/live-transcript-filters/phase-01/notes.md`
- `docs/plans/live-transcript-filters/phase-01/journal.md`

Do not modify frontend, database, dashboard API, model, static asset, or other
plan files.

## Contract

Keep existing event kinds. Add this field to every new `tool.started.data`:

```json
{
  "activity": "tool_call"
}
```

or:

```json
{
  "activity": "command"
}
```

Do not add activity to completion events. Historical events remain unchanged.

Add recorder support for:

```text
assistant.reasoning_summary.delta
```

with only `data.text` persisted through existing text splitting and coalescing.
No backend should emit this event during Phase 1.

## Exact classification

Add a tiny shared classifier in `src/openmcp/backends/__init__.py`. It must use
exact, case-sensitive provider and tool-name allow-lists.

Verified Command mappings:

- Claude exact `bash`.
- Codex exact `bash`.

Everything else defaults to Tool Call. Pi and Agy currently have no verified
Command aliases. `execute_code`, `exec`, and command-like substrings must remain
Tool Call unless an existing sanitized fixture proves otherwise.

Never inspect input, output, command text, or substrings. Never lowercase names.

## Provider boundaries

- Claude: classify `tool_use` starts. Keep `thinking_delta` excluded. Do not
  invent tool output from block stops.
- Codex: classify current `tool_call` starts. Preserve present input/output
  values. Keep generic `reasoning` excluded.
- Pi: classify current `tool_execution_start` and `tool_call` starts. Existing
  tools remain Tool Call. Keep `thinking_delta` excluded.
- Agy: classify both current `step_update` ACTIVE tool starts and legacy tool
  starts. Preserve current parser changes and payload boundaries. Existing tools
  remain Tool Call.

Do not refactor tool lifecycle matching in this phase.

## Recorder behavior

Generalize the current text-delta path to exactly:

- `assistant.text.delta`
- `assistant.reasoning_summary.delta`

Use existing UTF-8 splitting, limits, timer, persistence, ordering, and
truncation logic. Coalescing requires equal kind, entity ID, and parent entity
ID. Text and summary events must never cross-coalesce. Discard extra data keys
from normalized text-like events.

Do not change any quota constant.

## TDD tasks

1. Run the baseline suite and inspect existing Agy changes.
2. Add failing provider tests first.
3. Prove exact Command classification and unsafe substring rejection.
4. Strengthen negative reasoning and diagnostics tests.
5. Add failing recorder tests for summary coalescing, separation, UTF-8 splitting,
   and extra-field exclusion.
6. Extend execution persistence tests for activity and leakage boundaries.
7. Implement the exact shared classifier.
8. Add activity to all provider tool starts.
9. Generalize recorder text handling minimally.
10. Run all Phase 1 verification.

Record RED to GREEN evidence for each behavior in `notes.md`. Append the required
external response to `journal.md`.

## Security invariants

- Hidden chain-of-thought never persists.
- Generic provider thinking or reasoning never becomes a summary.
- Diagnostics and prompts never become Thinking.
- Payload content never affects activity classification.
- Raw input/output types and absent/null/falsy distinctions remain unchanged.
- Expanded history and system prompts remain excluded.
- Existing Agy protocol behavior remains intact.
- Non-streaming final results remain unchanged.
- Database, pagination, SSE, retention, and quotas remain unchanged.

## Done When

```bash
uv run pytest -q tests/test_streaming_backends.py tests/test_streaming.py tests/test_execution.py

git diff --check -- \
  src/openmcp/backends/__init__.py \
  src/openmcp/backends/claude.py \
  src/openmcp/backends/codex.py \
  src/openmcp/backends/pi.py \
  src/openmcp/backends/agy.py \
  src/openmcp/streaming.py \
  tests/test_streaming_backends.py \
  tests/test_execution.py \
  tests/test_streaming.py
```

Confirm all Phase 1 tests pass. Confirm only allowed files changed during this
phase. Report all changed files, RED and GREEN evidence, security checks,
remaining debt, and preserved pre-existing changes.
