# Board Rules

## Owner

This file is the only owner of card rules. The three coordinator skills link here.

## Scope

Cards carry engineering task text only. Titles, bodies, and notes never carry personal, beneficiary, or credential data. Cards are a view. They never replace Git anchors or handover state.

## States

- `todo`: TODO.
- `in_progress`: IN PROGRESS.
- `in_review`: IN REVIEW.
- `done`: DONE.
- `cancelled`: CANCELLED.

## Allowed Moves

- `todo`: `in_progress`, `cancelled`.
- `in_progress`: `in_review`, `cancelled`.
- `in_review`: `done`, `in_progress`, `cancelled`.
- `done`: none.
- `cancelled`: none.

DONE and CANCELLED are final.

A move to the current state is a same-state call. It links new jobs only. It ignores the note. It writes no move row and leaves `updated_at` unchanged when no link is new.

## Limits

- Title: 1 to 200 characters, not blank after trimming.
- Body: at most 4,000 characters.
- Note: at most 1,000 characters, so trim findings before the call.
- Job IDs: at most 16 job IDs per call, each 1 to 64 characters.
- Links: at most 64 links per card.

## Card Calls

| Moment | Call |
|---|---|
| First Prepare of a plan | `card_list`, then `card_create` for each missing phase in TODO, with title `<slug> · Phase <N>: <phase name>` and the phase goal from `PLAN.md` as the body. Write each returned ID to `card_refs` as soon as it returns. The middle dot is U+00B7. |
| Implement job submitted | `card_move(in_progress, job_ids=[<implement job>])`. |
| Gate 3 starts | `card_move(in_review)`. After the review job is submitted, link it with a same-state call. |
| Review FAIL | `card_move(in_progress, note=<findings, up to 1,000 characters>)`. Link the fix job with a same-state call. |
| Retry or continuation job | A same-state call that links the new job. |
| Phase finalized with `PASS` or `PASS_WITH_DEBT` | `card_move(done, note=<Spec and Quality status, debt owner>)`. |
| Phase or plan abandoned | `card_move(cancelled, note=<reason>)`. |

## Best-Effort Rule

A card call is best-effort. A failed call writes one journal line and one handover `debt` entry owned by `Coordinator`. A failed card call never sets `BLOCKED` and never changes a gate outcome. Retry a failed call at most once.

## Path Rule

Create and list cards against the `main repo root`, never a worktree. Pass the main repo root as `path`.

## Wave Rule

Each phase card moves to IN PROGRESS when its worktree job is submitted. Review and integration run on the main checkout and follow the card-call table. A requeued phase keeps its card where it is.

## Reconciliation

After a lost `card_create` reply, search `card_list` by exact title before creating again.

On resume, reconcile `card_refs` with `card_list`. Recreate a missing card. Move a lagging card only along allowed edges. Journal anything else.

## Oversized Response

On `response_too_large`, the change was applied. Record the applied card ID from the error. Do not create or move again until `card_list` shows the state.

## Final Audit

A final-audit regression after DONE goes to handover and the journal. DONE stays final.
