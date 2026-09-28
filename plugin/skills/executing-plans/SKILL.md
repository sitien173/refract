---
name: executing-plans
description: "Use when the user asks to run, continue, or resume a plan or its next phase, even without naming the plan. Runs one phase of a folder-layout plan under docs/plans/ through consult, implement, and review, then stops."
compatibility: Requires git and a running OpenMCP server.
---

# Executing Plans

## Role

This skill owns only the folder-plan phase procedure. Load
`coordinating-multi-model-work` first; it owns OpenMCP lifecycle, routing,
review, Git, and handover.

## Constraints

- Execute folder-layout plans only, one phase per invocation. Send a flat plan
  back through `writing-plans` for conversion.
- Never infer missing scope or reconcile conflicting state by resetting files.
- Keep existing phase files. Create only the missing ones.

## Workflow

1. **Resolve target.** A path or slug argument names the plan. A number names
   the phase. With no argument, use the single plan whose status is `ACTIVE`.
   With zero or several candidates, list them and ask.
2. **Check status.**

   | Status | Action |
   |---|---|
   | `ACTIVE` | Continue. |
   | `BLOCKED` | Show `next_action`. Continue once the user resolves it. |
   | `STALE_ANCHOR` | Stop and report the unresolved anchor. |
   | `DONE` | Report completion and stop. |

   A requested phase other than `current_phase` needs user confirmation.
3. **Read** `PLAN.md`, `.handover.md`, and the `read_first` paths that exist.
   Confirm the phase scope, its checks, and the plan-level commit message.
4. **Reconcile.** When `project_id` exists, apply the Coordinator's resume
   table before any edit. An active job is waited on, then resumed at its gate.
5. **Guidance.** For an active phase, reuse saved guidance. Do not re-run `task_guide` for an
   active phase. For a new phase, run Coordinator setup and task guidance.
6. **Prepare.** Require the plan `base` anchor. When it is missing, set
   `STALE_ANCHOR` and stop; never infer it from history. Create missing
   `phase-<NN>/prompt.md`, `notes.md`, and `journal.md` from the bundled
   templates. Under `tracked`, checkpoint coordination files only; any other
   change blocks execution until the user resolves it. Under `untracked`, leave
   plan artifacts excluded.
7. **Consult** when routed. Copy relevant findings into `prompt.md` and
   checkpoint it under `tracked`.
8. **Anchor.** Set `refs/plans/<slug>/phase-<NN>/base` to the clean checkpoint
   HEAD and record that HEAD as the `phase_base` cache. See
   [git-anchors.md](../coordinating-multi-model-work/references/git-anchors.md).
9. **Execute and review.** Run Gate 2 with `implementer-prompt.md`, then Gate
   3 with its bounded review-fix loop.
10. **Finalize phase** per the Coordinator review procedure. Set handover
    `current_phase` and `next_action` to the next phase, emit the phase report,
    and stop.
11. **Finalize plan** after the final phase: write final coordination state,
    consolidate every checkpoint into the sole plan commit, set the plan `impl`
    anchor, then invoke `verifying-before-completion`.

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

## References

- [coordinating-multi-model-work](../coordinating-multi-model-work/SKILL.md)
- [implementer-prompt.md](implementer-prompt.md)
