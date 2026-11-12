<!-- refract-shared-version: 3.0.3 -->
# External Response Protocol (ERP)

Response format for the phase implementer. The coordinator reads each section.

## Response block

Return exactly this block:

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
- Meets Spec? YES | WITH_DEBT | NO: [one line]
## CLARIFICATIONS NEEDED
None, or the exact questions
## NEXT
TASK_COMPLETE | BLOCKED | CONTINUE_CONTEXT
```

- **META:** phase number, ISO start and finish timestamps, and plan directory.
- **SUMMARY:** what the phase or fix batch delivered.
- **FILES MODIFIED:** every path you created or modified, including `notes.md`
  and `journal.md`. Use repository-relative paths from both `<code-root>` and `<records-root>`.
  Leave out coordinator files you did not edit, such as `.handover.md`.
- **NOTES:** the `notes.md` task blocks and fresh check counts.
- **SPEC COMPLIANCE:** your assessment against the phase `Done When`.
  - `YES`: every acceptance criterion passes, with behavioral RED to GREEN
    evidence and fresh checks.
  - `WITH_DEBT`: every blocking criterion passes; non-blocking follow-ups are
    in `notes.md`.
  - `NO`: a required criterion or check is unmet.

## NEXT

| `NEXT` | Requires |
|---|---|
| `TASK_COMPLETE` | `Meets Spec? YES` or `WITH_DEBT`, and `CLARIFICATIONS NEEDED: None`. |
| `BLOCKED` | Questions in `CLARIFICATIONS NEEDED`, or an environment blocker you cannot resolve. |
| `CONTINUE_CONTEXT` | A clean stop to continue in a follow-up turn. |

## Completion line

After the block, emit exactly one status line:

```text
Phase <N> completed. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
Phase <N> blocked. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
Phase <N> continuing. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
```

Use `completed` only with `TASK_COMPLETE`, `blocked` only with `BLOCKED`, and
`continuing` only with `CONTINUE_CONTEXT`.
