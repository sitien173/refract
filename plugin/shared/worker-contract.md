<!-- refract-shared-version: 2.5.0 -->
# Worker Contract

Execution contract for the phase implementer. This bundled file is read
directly from the installed plugin. The per-phase `prompt.md` carries the actual
tasks; this file defines the stable execution process.

## Per-task workflow

For each task in order:

1. Implement test-first where it applies: write the failing test against
   importable scaffolding or existing code, run it, and confirm a behavioral RED
   failure; then write minimal code to GREEN. An `ImportError`, `SyntaxError`,
   or fixture typo does not count as behavioral RED—add minimal inert
   scaffolding first so the test fails on the intended assertion. For
   behavior-preserving refactors, establish passing characterization coverage
   and keep it green.
2. Make changes directly in the `<code-root>` named by the prompt and stay strictly within the
   phase's declared file set. After each task, run the fresh verification
   command from the `Done When` section of the phase prompt. Record exact
   RED→GREEN commands and assertion outputs (or root-cause reproduction for a
   fix) in `notes.md`.
3. Append a `## Task <M>` block to `<plan-dir>/phase-<NN>/notes.md`. If the file
   is missing, create it from the bundled `notes-template.md` path in the prompt.
   Sub-sections per task: Decisions made (not in spec), Spec deviations,
   Tradeoffs accepted, Assumptions, Follow-ups for human, Test evidence
   (exact RED command/failure, then GREEN command/pass count). Empty
   sub-sections = `- none`; every task gets a block even if all `none`.
4. Add every worker-touched path to `## FILES MODIFIED` in your response.

## After all tasks (and on resumed `FIX:` batches)

- If `<plan-dir>/phase-<NN>/journal.md` is missing, create it from the
  bundled `journal-template.md` path in the prompt and fill its META.
- If `<plan-dir>/phase-<NN>/notes.md` is missing, create it from the
  bundled `notes-template.md` path in the prompt.
- On a resumed or `FIX:` batch, append a new batch section to `notes.md` and a
  new `# EXTERNAL RESPONSE` block under `## Implementation Response` in
  `journal.md`. Never overwrite earlier task notes, responses, or reviews.
- Then emit the status line selected by `erp.md`.

## Discipline

- **Test-first (TDD):** no production code without a behavioral failing test
  first. Write the test, watch the assertion fail, then write minimal code to
  pass.
- **Root-cause-first (bugs):** find the root cause before fixing; the fix starts
  from a failing test that reproduces the bug. Never fix a bug without a test.
- **Evidence before "done":** the phase `Done When` checks must pass with fresh
  output; record exact RED→GREEN and root-cause evidence in `notes.md`.

## Coordinator questions

For an unresolved decision the phase prompt does not answer, run
`refract ask "<question>"` and continue with its response. Do not ask about
routine choices already settled by the plan. The command needs the injected
`REFRACT_ASK_URL` and `REFRACT_ASK_TOKEN` environment variables; never print
their values. If the command fails, return `BLOCKED` with the question.

## Prompt and scope discipline

- Write phase records only under `<records-root>`. Outside a wave it equals
  `<code-root>`; in a wave it is the main checkout. If a sandbox means you
  cannot write under `<records-root>`, return `BLOCKED` with that error.
- Stay within the declared file set (`Files` in `prompt.md` plus `notes.md` and
  `journal.md`). Report every worker-touched path.
- Pre-existing or coordinator-updated changes to `.handover.md`, `PLAN.md`,
  `DESIGN.md`, or `prompt.md` are normal coordinator state: leave them untouched
  and never report `BLOCKED` or list them in `FILES MODIFIED` unless you edited
  them.
- Do not run Git commits, resets, stashes, branch changes, or ref writes.
- Do not duplicate file content in the response or produce a reference prototype.
- If a requirement is genuinely blocked, list it under `CLARIFICATIONS NEEDED`,
  append the partial response with `NEXT: BLOCKED` to `journal.md`, and emit the
  matching blocked status line.
