<!-- ccg-shared-version: 7.1.0 -->
# Worker Contract

Execution contract for the phase owner. This bundled file is read
directly from the installed plugin. The per-phase `prompt.md` carries the actual
tasks; this file defines the stable execution process.

## Per-task workflow

For each task in order:

1. Implement test-first where it applies: write the failing test, run it, confirm
   RED; then write minimal code to GREEN. For behavior-preserving refactors,
   establish passing characterization coverage and keep it green.
2. Do not stage, commit, reset, squash, merge, or integrate. Do not use Git mutation commands. All changes are made directly to the files in
   the phase directory. After each task, run the fresh verification command from
   the `Done When` section of the phase prompt. Record RED→GREEN or root-cause
   evidence in `notes.md`.
3. Append a `## Task <M>` block to `<plan-dir>/phase-<NN>/notes.md`. If the file
   is missing, create it from the bundled `notes-template.md` path in the prompt.
   Sub-sections per task: Decisions made (not in spec), Spec deviations,
   Tradeoffs accepted, Assumptions, Follow-ups for human, Test evidence
   (RED→GREEN, or root cause for a fix). Empty sub-sections = `- none`; every
   task gets a block even if all `none`.
4. Add every touched path to `## FILES MODIFIED` in your response.

## After all tasks

- If `<plan-dir>/phase-<NN>/journal.md` is missing, create it from the
  bundled `journal-template.md` path in the prompt and fill its META.
- If `<plan-dir>/phase-<NN>/notes.md` is missing, create it from the
  bundled `notes-template.md` path in the prompt.
- Append the full `# EXTERNAL RESPONSE` block (see `erp.md`) under the
  `## Implementation Response` heading of `<plan-dir>/phase-<NN>/journal.md`. Do not
  overwrite earlier sections.
- Then emit the status line selected by `erp.md`.

## Discipline

- **Test-first (TDD):** no production code without a failing test first. Write the
  test, watch it fail, then write minimal code to pass.
- **Root-cause-first (bugs):** find the root cause before fixing; the fix starts
  from a failing test that reproduces the bug. Never fix a bug without a test.
- **Evidence before "done":** the phase `Done When` checks must pass with fresh
  output; record RED→GREEN and root-cause evidence in `notes.md`.

## Prompt discipline

- Stay within the declared file set. Report every changed path.
- Do not duplicate file content in the response.
- Do not redesign the phase or produce a reference prototype.
- If anything is unclear, list it under CLARIFICATIONS NEEDED and stop.
- Before stopping, append the partial response with `NEXT: BLOCKED` to the journal
  and emit the matching blocked status line.
