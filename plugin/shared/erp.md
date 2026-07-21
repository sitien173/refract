<!-- ccg-shared-version: 7.2.0 -->
# External Response Protocol (ERP)

Worker-facing contract for the implementation response. This bundled file is
read directly from the installed plugin.

## The `# EXTERNAL RESPONSE` block

Return exactly this block. Each section is what Coordinator scans for.

```text
# EXTERNAL RESPONSE
## META
- Phase / Started / Finished / Plan dir
## SUMMARY
[one sentence]
## FILES MODIFIED
| Action | Path | Change |
## NOTES
- phase-<NN>/notes.md  (## Task <M>, …)
## SPEC COMPLIANCE
- Meets Spec? YES | WITH_DEBT | NO  — [one line]
## CLARIFICATIONS NEEDED
None (or list questions; emit and stop if any)
## NEXT
TASK_COMPLETE | BLOCKED | CONTINUE_CONTEXT
```

- **META** — phase identity and timestamps.
- **SUMMARY** — one-line statement of what the phase delivered.
- **FILES MODIFIED** — every touched path; Coordinator scans exactly this set.
- **NOTES** — pointer to the per-task `notes.md` blocks (decisions, deviations, evidence).
- **SPEC COMPLIANCE** — self-assessment against the phase `Done When`.
- **CLARIFICATIONS NEEDED** — if non-empty, emit this and stop; do not guess.
- **NEXT** — whether the phase is done, blocked, or continuing.

## Completion line

After the block, emit exactly one matching status line:

```text
Phase <N> completed. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
Phase <N> blocked. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
Phase <N> continuing. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
```

Use `completed` only with `TASK_COMPLETE`. Use `blocked` when clarification is
required. Use `continuing` only with `CONTINUE_CONTEXT`.
