---
name: executing-plans
description: "Runs or resumes one phase of a folder-layout plan through the canonical OpenMCP gates."
---

# Executing Plans

Load `coordinating-multi-model-work` first. It owns OpenMCP lifecycle, routing,
review, and handover. This skill owns only the folder-plan phase procedure.

## Procedure

1. Read `PLAN.md`, `.handover.md`, and validated `read_first` paths. Select one
   phase and confirm its scope and checks. Confirm the plan-level commit message.
2. When `project_id` exists, reconcile handover with the `active` entries from
   `openmcp://projects/<project_id>/jobs` before editing. Read a specific job
   resource only when its result is needed. If a job is active, return to the
   canonical resume flow.
3. For an active phase, reuse saved guidance. Do not re-run `task_guide` for an
   active phase. For a new phase, run canonical setup and guidance.
4. Require the plan `base` anchor created before plan authoring. Never infer a
   missing anchor from existing history. Create `phase-<NN>/prompt.md`, `notes.md`,
   and `journal.md` from the bundled templates. Under `tracked`, checkpoint only
   known plan artifacts; unrelated changes block execution. Under `untracked`,
   leave plan artifacts excluded.
5. Run any routed consultation. Incorporate its relevant findings and checkpoint
   the prompt update under `tracked`.
6. Before the initial implementation, set `refs/plans/<slug>/phase-<NN>/base` to
   the clean checkpoint HEAD and record that same HEAD as the `phase_base` cache.
   You own both, since OpenMCP tracks no base commit. See
   `skills/coordinating-multi-model-work/references/git-anchors.md`.
7. Run Gate 2 with `implementer-prompt.md`, then Gate 3. Blocking findings run
   the coordinator's bounded review-fix loop, which re-reviews only the fix
   delta. Phase commits are temporary checkpoints retained by local refs.
8. After canonical phase finalization, advance one phase. After the final phase,
   write final coordination state, consolidate every checkpoint into the sole
   plan commit, set the plan `impl` anchor, then invoke
   `verifying-before-completion`.

## Rules

- Execute folder-layout plans only, one phase at a time.
- New phases load current guidance; active phases keep saved guidance.
- Never infer missing scope or reconcile conflicting state by resetting files.

## References

- `skills/coordinating-multi-model-work/SKILL.md`
- `skills/executing-plans/implementer-prompt.md`
