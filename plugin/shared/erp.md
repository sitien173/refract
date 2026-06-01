<!-- ccg-shared-version: 5.2.0 -->
# External Response Protocol (ERP)

Worker-facing contract for the response a Codex / Gemini phase worker returns to
the coordinator. This file is materialized into `<project>/.agents/shared/erp.md`
by the plugin's SessionStart hook — do not hand-edit the copy; edit the plugin's
`shared/erp.md` template.

## The `# EXTERNAL RESPONSE` block

Return exactly this block. Each section is what the coordinator scans for.

```text
# EXTERNAL RESPONSE
## META
- Phase / Owner (codex|gemini) / SessionID / Started / Finished / Plan dir
## SUMMARY
[one sentence]
## FILES MODIFIED
| Action | Path | Change |
## COMMITS
- phase-<N>.task-<M>: <hash>  <subject>
## NOTES
- phase-<NN>/notes.md  (## Task <M>, …)
## SPEC COMPLIANCE
- Meets Spec? YES | WITH_DEBT | NO  — [one line]
## CLARIFICATIONS NEEDED
None (or list questions; emit and stop if any)
## NEXT
TASK_COMPLETE | CONTINUE_SESSION | HANDOVER_TO_CLAUDE
```

- **META** — phase identity + session reuse handle the coordinator caches.
- **SUMMARY** — one-line statement of what the phase delivered.
- **FILES MODIFIED** — every touched path; the coordinator quality-scans exactly this set.
- **COMMITS** — one row per task commit with its hash; the coordinator reviews each via `git show <hash>`.
- **NOTES** — pointer to the per-task `notes.md` blocks (decisions, deviations, evidence).
- **SPEC COMPLIANCE** — self-assessment against the phase `Done When`.
- **CLARIFICATIONS NEEDED** — if non-empty, emit this and stop; do not guess.
- **NEXT** — whether the phase is done, the session continues, or it hands back to the coordinator.

## Completion line

After the block, emit exactly one completion line — the coordinator scans for it:

```text
Phase <N> completed. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
```
