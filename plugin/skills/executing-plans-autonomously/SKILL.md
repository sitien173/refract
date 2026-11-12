---
name: executing-plans-autonomously
description: "Use when the user asks to execute an entire plan autonomously, through every phase, final audit, and consolidation, without pausing for permission. Makes engineering and deferral decisions itself and logs them to .handover.md."
compatibility: Requires git and a running Refract server.
---

# Executing Plans Autonomously

## Role

This skill owns the no-pause policy for a full plan run. Load
`coordinating-multi-model-work` and `executing-plans` first. Run their
procedures unchanged, except that every point where they stop for the user
becomes a logged decision under the policy below.

## Decision Policy

Treat this skill's invocation as maintainer authorization to decide, fix, and
defer. Run from the current phase through consolidation in one pass, emitting
each phase report and continuing. Stop for the user only at a hard stop.

| Stop point | Decision |
|---|---|
| Worker `BLOCKED`, `result.pending_question`, or handover `BLOCKED` | Answer from the plan, design, and code. Set `status: ACTIVE` and continue. |
| Test, lint, review, or audit failure | Fix the root cause in code or tests, re-verify, and re-review where the review-fix loop requires it. |
| Findings remaining after the review-fix loop | Run one more fix cycle under the same re-review rule. |
| Live or smoke check hits an environment limit, mock discrepancy, or nondeterminism | Investigate. When it cannot be resolved within the repository's constraints, such as read-only checkouts or secret handling, defer it with the exact finding. |
| `PASS_WITH_DEBT` or deferred scope awaiting sign-off | Accept it with a named owner. |

Log every decision with its finding and rationale in the phase's
`completed_phases` summary in `.handover.md`. Record each deferral as a `debt`
entry with an owner.

## Hard Stops

These protect the user's work and Git state, so the run stops and reports
instead of deciding:

- Detached HEAD before a job.
- User changes that block an anchor or review, per Git Ownership in
  `coordinating-multi-model-work`.
- Handover `status: STALE_ANCHOR`.
- Blocking findings still open after the second fix cycle.
- Refract server unavailable.

After the user resolves the stop, invoking this skill again resumes from the
current phase.

## Workflow

1. **Resolve target.** Use the named plan path or `<plan-slug>`, or the single
   `ACTIVE` plan in `docs/plans/`. Read `PLAN.md`, `DESIGN.md` if present,
   `.handover.md`, and existing `read_first` paths.
2. **Reconcile.** Run Coordinator setup and job reconciliation. Resolve a
   `BLOCKED` handover under the policy and continue from the current
   unfinished phase.
3. **Run waves.** Loop waves until every phase has its `impl` ref, selecting
   each per [waves.md](../coordinating-multi-model-work/references/waves.md).
   A single-phase wave runs the `executing-plans` phase steps unchanged; a
   multi-phase wave runs through `waves.md`. When a wave phase fails,
   set it `requeued` and log the decision to `.handover.md` instead of blocking.
   Make card calls at the moments listed in
   [board.md](../coordinating-multi-model-work/references/board.md).
4. **Final audit.** After the final phase closes, check every plan acceptance
   criterion and run every verification command at HEAD. Fix regressions; log
   unresolvable environment items as debt.
5. **Consolidate** through the sole
   [consolidation procedure](../coordinating-multi-model-work/references/git-anchors.md#consolidation).
   It owns the `DONE` status, the plan commit, the plan `impl` ref, and final
   verification.
