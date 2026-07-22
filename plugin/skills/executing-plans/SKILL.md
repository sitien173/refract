---
name: executing-plans
description: "Runs or resumes one phase of a folder-layout plan through the canonical OpenMCP gates."
---

# Executing Plans

Load `coordinating-multi-model-work` first. It owns OpenMCP lifecycle, routing,
review, and handover. This skill owns only the folder-plan phase procedure.

## Procedure

1. Read `PLAN.md`, `.handover.md`, and validated `read_first` paths. Select one
   phase and confirm its scope, checks, and commit message.
2. When `project_id` exists, reconcile handover with
   `openmcp://projects/<project_id>/jobs` before editing. If a job is active,
   return to the canonical resume flow.
3. For an active phase, reuse saved guidance. Do not re-run `task_guide` for an
   active phase. For a new phase, run canonical setup and guidance.
4. Create `phase-<NN>/prompt.md`, `notes.md`, and `journal.md` from the bundled
   templates. Commit only known plan artifacts as
   `chore(plan): prepare phase <N>`; unrelated changes block execution.
5. Run any routed consultation. Incorporate its relevant findings and commit
   only that prompt update.
6. Retain the clean HEAD before the initial implementation as `phase_base` and
   confirm it later against that job's `base_commit`.
7. Run Gate 2 with `implementer-prompt.md`, then Gate 3. A review fix starts a
   new implementation job and repeats both reviews.
8. After canonical finalization, advance one phase. After the final phase, mark
   handover `DONE` and invoke `verifying-before-completion`.

## Rules

- Execute folder-layout plans only, one phase at a time.
- New phases load current guidance; active phases keep saved guidance.
- Never infer missing scope or reconcile conflicting state by resetting files.

## References

- `skills/coordinating-multi-model-work/SKILL.md`
- `skills/executing-plans/implementer-prompt.md`
