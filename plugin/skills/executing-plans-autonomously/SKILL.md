---
name: executing-plans-autonomously
description: "Use when the user asks to autonomously execute an entire plan across all phases through final audit and consolidation without pausing for permission. Runs Phase 1 through the final phase continuously, makes autonomous engineering and deferral decisions, logs them to .handover.md, and completes final consolidation."
compatibility: Requires git and a running Refract server.
---

# Executing Plans Autonomously

## Role

This skill owns the continuous, zero-pause full-plan execution policy across all
phases through final audit and consolidation. Load
`coordinating-multi-model-work` and `executing-plans` first; they own Refract
lifecycle, routing, review, Git anchors, handover schema, and the per-phase
procedure.

## Zero-Pause & Autonomous Decision Policy (CRITICAL)

- **NO PAUSING FOR PERMISSION OR APPROVAL:** Execute all phases from the
  starting phase through the final phase and the final completion audit
  continuously in a single autonomous run. Do NOT stop between phases, do NOT
  ask for confirmation to proceed, and do NOT ask for authorization to
  investigate, fix, or defer issues.
- **NEVER STOP IN A `BLOCKED` STATE FOR USER INPUT:** You are pre-authorized to
  make all engineering, testing, live-smoke, and audit decisions autonomously.
  If a worker job returns `BLOCKED`, `pending_question`, or remaining review
  findings after the standard loop, resolve the ambiguity or fix the code
  autonomously and continue.
- **AUTO-DECIDE & LOG TO `.handover.md`:**
  - **Test, lint, review, or audit failure:** Automatically investigate and fix
    the root cause in code or tests, then re-verify and re-review until checks
    pass.
  - **Live/smoke or environmental limitation:** When a live or smoke check
    encounters an external environment limitation, mock discrepancy, or
    non-deterministic behavior, investigate it first. If it cannot be resolved
    within repository constraints, such as without modifying read-only checkouts
    or leaking secrets, make the pragmatic decision automatically, document the
    exact finding, rationale, and resolution or deferral in the `debt` list and
    `completed_phases` summary of `.handover.md`, and proceed.
  - **`PASS_WITH_DEBT` or deferred scope:** When a reviewer or completion
    auditor flags `PASS_WITH_DEBT` or requests user sign-off on deferred scope,
    treat this policy as explicit maintainer authorization: log the decision and
    named owner in `.handover.md` (`debt` and `completed_phases`) and continue
    through final consolidation.

## Workflow

1. **Resolve target.** Use the named plan path or `<plan-slug>`, or the active
   plan in `docs/plans/`. Read `PLAN.md`, `DESIGN.md` if present, `.handover.md`,
   and existing `read_first` paths.
2. **Reconcile and resume.** Run Coordinator setup and job reconciliation. If
   `.handover.md` is `BLOCKED`, resolve the pending question or blocker
   autonomously, set `status: ACTIVE`, record the rationale in `.handover.md`,
   and continue from the current unfinished phase.
3. **Loop across all remaining phases.** For each phase from the current active
   phase through the final phase in `PLAN.md`:
   - Run the `executing-plans` phase preparation, `phase-<NN>/base` anchor,
     Gate 1 route, Gate 2 implementation with
     [implementer-prompt.md](../executing-plans/implementer-prompt.md), and
     Gate 3 specification and independent quality reviews.
   - Apply the Zero-Pause & Autonomous Decision Policy to resolve any
     clarification, test failure, review finding, environmental blocker, or
     `PASS_WITH_DEBT` outcome without stopping.
   - Finalize the phase (`journal.md`, `refs/plans/<slug>/phase-<NN>/impl`, and
     `.handover.md` `completed_phases` and `debt`), emit the phase report, and
     immediately advance `current_phase` and `next_action` to the next phase
     without pausing.
4. **Final completion audit and consolidation.** After the final phase closes:
   - Run a final completion audit across the full plan criteria and verification
     commands. Fix any regressions or log non-blocking environmental/deferred
     items to `.handover.md` under `debt` and `completed_phases`.
   - Execute the sole
     [consolidation procedure](../coordinating-multi-model-work/references/git-anchors.md#consolidation)
     to replace phase checkpoints with the single plan commit, set
     `refs/plans/<slug>/impl`, verify the final HEAD with
     `verifying-before-completion`, and mark `.handover.md` `status: DONE`.

## References

- [coordinating-multi-model-work](../coordinating-multi-model-work/SKILL.md)
- [executing-plans](../executing-plans/SKILL.md)
- [implementer-prompt.md](../executing-plans/implementer-prompt.md)
