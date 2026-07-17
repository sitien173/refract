---
name: executing-plans
description: "Runs or resumes a written plan one phase at a time through the coordinating workflow's Plan, Execute, and Review gates. Use when executing or resuming an implementation phase."
---

# Executing Plans

Thin phase-runner. **Load `coordinating-multi-model-work` first** — it owns the
gates, job states, review rules, integration, and handover schema. This skill
adds only what is specific to running a plan phase: setup, resume, and route
resolution.

## Use When

- An executable (folder-layout) plan exists.
- The user requests execution or resumption.

## Per-phase procedure

1. Read `PLAN.md` once; select the requested phase. Read `.handover.md` and its
   validated `read_first` paths.
2. **Project setup** (only without a `project_id`): run coordinating's *Project
   Setup* — `project_init`, commit created files, then `project_register`.
3. **Resume before routing.** Read `openmcp://projects/<project_id>/jobs`; match
   `job_refs` and `context_prefix`. For an existing phase chain, restore its
   stored nickname, execution role, workflow, and profile (recover missing
   values from the job's workflow, profile, and context key; stop if ambiguous).
   Never call `task_route` again for that phase.
4. **New phase routing.** Call `task_route` with the phase route intent and
   `project_id`. Validate any user-pinned nickname; otherwise select the
   configured recommendation. Split the phase when its use cases need different
   owners. Confirm the built-in `read`/`write` workflows against
   `openmcp://workflows/<project_id>`, and the profile against
   `openmcp://projects/<project_id>/routing-profiles`.
5. Confirm the resolved phase has one owner, one routing profile, two to four
   tasks, files, acceptance criteria, checks, and a commit message.
6. **Run the three gates per `coordinating-multi-model-work`:** Gate 1 emits
   `# ROUTE`; Gate 2 checkpoints, submits the built-in `write` workflow (using
   `implementer-prompt.md`), and waits compactly; Gate 3 verifies in a
   disposable worktree, runs independent review, and integrates on PASS.
7. Append review evidence to `journal.md`, update `.handover.md`, and commit
   coordination state as `chore(plan): record phase <N>`.
8. Advance only after Review passes. After the final phase, mark handover `DONE`
   and invoke `verifying-before-completion`.

## Skill-specific rules

- Flat plans are documentation only — never execute one.
- Existing phase chains keep stored routing decisions; only new phases reload
  routes and profiles.
- Recover ambiguous routing? Stop and ask, rather than re-routing a live chain.

(Job-state handling, worktree verification, review gate, and no-manual-Git rules
are canonical in `coordinating-multi-model-work`.)

## References

- `skills/coordinating-multi-model-work/SKILL.md`
- `skills/executing-plans/implementer-prompt.md`
- `skills/verifying-before-completion/SKILL.md`
