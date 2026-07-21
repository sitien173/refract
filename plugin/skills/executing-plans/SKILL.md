---
name: executing-plans
description: "Runs or resumes one phase of a folder-layout implementation plan through the canonical Plan, Execute, and Review gates."
---

# Executing Plans

Load `coordinating-multi-model-work` first. It owns OpenMCP setup, guidance,
job-state handling, verification, review, integration, and handover. This skill
only adapts that workflow to a written plan.

## Per-Phase Procedure

1. Read `PLAN.md`, `.handover.md`, and validated `read_first` paths. Select one
   phase and confirm its tasks, files, acceptance criteria, checks, and commit.
2. If `project_id` is absent, run canonical project setup.
3. Resume before resolving new guidance: read
   `openmcp://projects/<project_id>/jobs` and reconcile `job_refs` plus
   `context_prefix` with OpenMCP's records.
4. For an existing chain, restore its saved workflows and profiles. Do not
   re-run `task_guide` for an active phase chain; stop if recovery is ambiguous.
5. For a new phase, call `task_guide` with the phase's complete **Task Guide
   Input**. Validate a user-pinned profile, otherwise use each matching
   recommendation or the configured default.
6. Run Gate 1. Create `phase-<NN>/prompt.md`, `notes.md`, and `journal.md` only
   when the canonical checkpoint requires them.
7. Run Gate 2 with `implementer-prompt.md` and one linear implementation chain.
8. Run Gate 3, integrate the approved implementation, record evidence, and
   advance handover only after review passes.
9. After the final phase, mark handover `DONE` and invoke
   `verifying-before-completion`.

## Rules

- Execute folder-layout plans only.
- Run one phase at a time.
- Existing phase chains keep stored guidance decisions; new phases load current
  guidance.
- Never reconstruct or manually integrate an OpenMCP chain.
- If plan scope is incomplete or resume state conflicts with OpenMCP, stop and
  ask rather than guessing.

## References

- `skills/coordinating-multi-model-work/SKILL.md`
- `skills/executing-plans/implementer-prompt.md`
- `skills/verifying-before-completion/SKILL.md`
