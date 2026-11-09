---
name: executing-plans
description: "Use when the user asks to run, continue, or resume a plan or its next phase, even without naming the plan. Runs one wave of a folder-layout plan under docs/plans/ through implement and review, emits a phase report per phase, then stops. Without a plan, use `writing-plans` first."
compatibility: Requires git and a running Refract server.
---

# Executing Plans

## Role

This skill owns the folder-plan phase procedure. Load
`coordinating-multi-model-work` first.

## Constraints

- Execute folder-layout plans only, one wave per invocation. Send a flat plan
  back through `writing-plans` for conversion.
- Ask about missing scope or conflicting state; leave files as they are.
- Keep existing phase files. Create only the missing ones.

## Workflow

1. **Resolve target.** A path or slug argument names the plan. A number names
   the phase. With no argument, use the single plan whose status is `ACTIVE`.
   With zero or several candidates, list them and ask. Then select the next
   wave from `Depends on:` lines and phase `impl` refs per [waves.md](../coordinating-multi-model-work/references/waves.md).
   A single-phase wave runs steps 2 to 10 unchanged. A multi-phase wave runs
   through `waves.md`, emits one phase report per phase, and
   sets `BLOCKED` for a failed wave phase after the other phases integrate.
2. **Check status.** Act on handover `status` per the Coordinator's Handover
   table. A requested phase other than `current_phase` needs user
   confirmation.
3. **Read** `PLAN.md`, `.handover.md`, and the `read_first` paths that exist.
   Confirm the phase scope, its checks, and the plan-level commit message.
4. **Reconcile.** When the handover names a job, apply the Coordinator's resume
   table before any edit.
5. **Guidance.** Do not call `list` for guidance during an active phase; reuse
   its saved guidance. For a new phase, run Coordinator setup and call `list`
   once.
6. **Prepare.** Require the plan `base` anchor. When it is missing, set
   `STALE_ANCHOR` and stop; an anchor comes only from its ref. Create missing
   `phase-<NN>/prompt.md`, `notes.md`, and `journal.md` from the bundled
   templates. Write the phase `checklist` in handover per
   [handover.md](../coordinating-multi-model-work/references/handover.md#checklist)
   and keep it current through steps 8 and 9. Make card calls at the moments
   listed in [board.md](../coordinating-multi-model-work/references/board.md). Under
   `tracked`, checkpoint coordination files only; any other change blocks
   execution until the user resolves it. Under `untracked`, leave plan
   artifacts excluded.
7. **Anchor.** Set `refs/plans/<slug>/phase-<NN>/base` to the clean checkpoint
   HEAD and record that HEAD as the `phase_base` cache. See
   [git-anchors.md](../coordinating-multi-model-work/references/git-anchors.md).
8. **Execute and review.** Emit the Gate 1 route, run Gate 2 with
   `implementer-prompt.md`, then Gate 3 with its bounded review-fix loop.
9. **Finalize phase** per
    [review.md](../coordinating-multi-model-work/references/review.md#finalize-phase). Set handover
    `current_phase` and `next_action` to the next phase, emit the phase report,
    and stop after the last phase of the wave.
10. **Finalize plan** after the final phase using the sole
    [consolidation procedure](../coordinating-multi-model-work/references/git-anchors.md#consolidation).

## Gotchas

- A phase you implement yourself, for example after the user cancels its job,
  has no independent review. Record Quality as open debt, never as `PASS`.
- A phase that routes no worker still gets its `phase-<NN>/` files. Without
  them, closeout rebuilds follow-ups from memory.

## Output Format

```text
# PHASE REPORT
- Plan: docs/plans/<slug>
- Phase: <N> <outcome> - DONE | BLOCKED | FAILED
- Checkpoint: refs/plans/<slug>/phase-<NN>/impl | none
- Checks: <command> -> <result>
- Review: Spec <status>, Quality <status>
- Debt: <item and owner> | none
- Next: <next_action>
```
