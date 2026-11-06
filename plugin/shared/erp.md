<!-- refract-shared-version: 2.5.0 -->
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

- **META** — phase identity, start/finish ISO timestamps, and plan directory.
- **SUMMARY** — one-line statement of what the phase or fix batch delivered.
- **FILES MODIFIED** — every path the worker created or modified (allowed
  production/test files plus `phase-<NN>/notes.md` and `phase-<NN>/journal.md`),
  using repository-relative paths from both `<code-root>` and `<records-root>`.
  Never list untouched coordinator files such
  as `.handover.md`.
- **NOTES** — pointer to the per-task `notes.md` blocks and fresh check counts.
- **SPEC COMPLIANCE** — self-assessment against the phase `Done When`:
  - `YES`: all acceptance criteria, behavioral RED→GREEN evidence, and fresh
    verification checks pass.
  - `WITH_DEBT`: all blocking criteria pass; non-blocking follow-ups are
    documented in `notes.md`.
  - `NO`: a required criterion or check is unmet (pair with `BLOCKED` or
    `CONTINUE_CONTEXT`).
- **CLARIFICATIONS NEEDED** — `None` when complete; if non-empty, list exact
  questions, set `NEXT: BLOCKED`, emit, and stop.
- **NEXT** — must align with `SPEC COMPLIANCE` and `CLARIFICATIONS NEEDED`:
  - `TASK_COMPLETE` requires `CLARIFICATIONS NEEDED: None` and `Meets Spec? YES`
    (or `WITH_DEBT`).
  - `BLOCKED` requires concrete questions in `CLARIFICATIONS NEEDED` or an
    unrecoverable environment blocker.
  - `CONTINUE_CONTEXT` when stopping cleanly to continue in a follow-up turn.

## Completion line

After the block, emit exactly one matching status line:

```text
Phase <N> completed. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
Phase <N> blocked. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
Phase <N> continuing. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
```

Use `completed` only with `TASK_COMPLETE`. Use `blocked` when clarification is
required. Use `continuing` only with `CONTINUE_CONTEXT`.
