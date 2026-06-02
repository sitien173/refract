<!-- ccg-shared-version: 5.2.0 -->
# Worker Contract

Execution contract for a Codex / Gemini phase worker. This file is materialized
into `<project>/.agents/shared/worker-contract.md` by the plugin's SessionStart
hook — do not hand-edit the copy; edit the plugin's `shared/worker-contract.md`
template. The per-phase `prompt.md` carries the actual tasks; this file is the
stable how.

## Per-task workflow

For each task in order:

1. Implement test-first where it applies: write the failing test, run it, confirm
   RED; then write minimal code to GREEN.
2. `git add` only the files touched for this task; commit with subject
   `phase-<N>.task-<M>: <one-line>`. Capture the hash.
3. Append a `## Task <M>` block to `<plan-dir>/phase-<NN>/notes.md` (create with
   heading `# Phase <N> — Decision Notes` if missing). Sub-sections: Decisions
   made (not in spec), Spec deviations, Tradeoffs accepted, Assumptions,
   Follow-ups for human, Test evidence (RED→GREEN, or root cause for a fix).
   Empty sub-sections = `- none`; every task gets a block even if all `none`.
4. Append the commit row to `## COMMITS` in your response.

## After all tasks

- Append the full `# EXTERNAL RESPONSE` block (see `erp.md`) under the
  `## External Response` heading of `<plan-dir>/phase-<NN>/journal.md`. Do not
  overwrite earlier sections.
- Then emit the single completion line from `erp.md`.

## Discipline

- **Test-first (TDD):** no production code without a failing test first. Write the
  test, watch it fail, then write minimal code to pass.
- **Root-cause-first (bugs):** find the root cause before fixing; the fix starts
  from a failing test that reproduces the bug. Never fix a bug without a test.
- **Evidence before "done":** the phase `Done When` checks must pass with fresh
  output; record RED→GREEN and root-cause evidence in `notes.md`.

## Prompt discipline

- Edit files directly with your write tools; on-disk files are the source of truth.
- Do not duplicate file content in the response.
- Do not redesign the phase or produce a reference prototype.
- If anything is unclear, list it under CLARIFICATIONS NEEDED and stop.
