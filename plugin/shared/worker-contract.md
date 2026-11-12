<!-- refract-shared-version: 3.0.2 -->
# Worker Contract

Execution process for the phase implementer. The phase `prompt.md` lists the
tasks and the paths of the bundled `erp.md`, `notes-template.md`, and
`journal-template.md`. This file defines how to run the tasks.

## Per-task workflow

For each task in order:

1. **Test first.** Write a failing test against existing code or minimal inert
   scaffolding, run it, and confirm it fails on the intended assertion. An
   `ImportError`, `SyntaxError`, or fixture typo is not a behavioral failure.
   Then write the minimal code that passes. For a bug, the test reproduces it
   and the fix addresses the root cause. For a behavior-preserving refactor,
   keep passing characterization coverage green.
2. **Verify.** Run the targeted tests for this task. Leave the full `Done When`
   commands for the end of the phase.
3. **Record.** Append a `## Task <M>` block to `<plan-dir>/phase-<NN>/notes.md`,
   creating the file from `notes-template.md` when it is missing. Fill every
   sub-section, using `- none` when empty, and record the exact RED and GREEN
   commands and outputs.

## After all tasks

1. Run each fresh verification command from the phase `Done When` once.
2. Create `<plan-dir>/phase-<NN>/journal.md` from `journal-template.md` when it
   is missing, and fill its META.
3. Append the `# EXTERNAL RESPONSE` block from `erp.md` under
   `## Implementation Response` in `journal.md`.
4. Return that block and the matching status line from `erp.md`.

On a resumed or `FIX:` batch, append a new batch section to `notes.md` and a
new response block to `journal.md`. Keep earlier notes, responses, and reviews
intact. A `FIX:` batch runs only the checks its prompt lists.

## Scope

- Edit code only in the `<code-root>` named by the prompt, and only the paths
  under `Files` in `prompt.md`, plus `notes.md` and `journal.md`.
- Write phase records only under `<records-root>`. Outside a wave it equals
  `<code-root>`; in a wave it is the main checkout. If a sandbox means you
  cannot write under `<records-root>`, return `BLOCKED` with that error.
- Treat changes to `.handover.md`, `PLAN.md`, `DESIGN.md`, and `prompt.md` as
  coordinator state. Leave them as they are. List them in `FILES MODIFIED` only
  when you edited them, and do not return `BLOCKED` because of them.
- Leave Git to the coordinator: no commits, resets, stashes, branch changes,
  or ref writes.
- Refer to files by path in the response instead of copying their content, and
  do not write a reference prototype.

## Questions and blockers

For a decision the phase prompt leaves open, run `refract ask "<question>"` and
continue with the answer. Settle routine choices from the plan yourself. The
command reads the injected `REFRACT_ASK_URL` and `REFRACT_ASK_TOKEN`
environment variables; keep their values out of all output.

When the command fails or a requirement stays blocked, list the questions under
`CLARIFICATIONS NEEDED`, append the partial response to `journal.md`, and
return it with `NEXT: BLOCKED`.
