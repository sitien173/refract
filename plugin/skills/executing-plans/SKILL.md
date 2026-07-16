---
name: executing-plans
description: "Executes a written plan through project-scoped OpenMCP jobs with Plan, Execute, and Review gates. Use when running or resuming an implementation phase."
---

# Executing Plans

Load `coordinating-multi-model-work` first. It defines routing, gates, job
states, review rules, and the handover schema.

## Use When

- An executable plan exists.
- The user requests execution or resumption.

## Workflow

1. Read `PLAN.md` once. Select the requested phase.
2. Read `.handover.md` and validated `read_first` paths.
3. Without `project_id`, call `project_init`. Review and commit created files.
   Register only after the repository becomes clean.
4. Read `openmcp://projects/<project_id>/jobs`. Match `job_refs` and
   `context_prefix` before resolving new routing.
5. When a phase chain exists, restore its nickname, execution role, workflow,
   and profile. Recover missing values from the job workflow, profile, and
   context key. Stop when recovery is ambiguous. Never call `task_route` again
   for that phase.
6. For a new phase, call `task_route` with its route intent and `project_id`.
   Validate user-pinned nicknames. Otherwise select configured recommendations.
7. Split the phase before submission when use cases select different owners.
8. Read `openmcp://workflows/<project_id>`. Derive and validate owner,
   consultant, and reviewer workflows from their `execution_role` values.
9. Read `openmcp://projects/<project_id>/routing-profiles`. Validate a pinned
   profile. Otherwise select the returned default.
10. Confirm the resolved phase has one owner, one routing profile, two to four
   tasks, files, acceptance criteria, checks, and a commit message.
11. Run the canonical Plan gate. Output `# ROUTE`.
12. Prepare the phase checkpoint. Commit prompt and handover. Record the clean
   commit as `phase_base`.
13. Submit the derived owner write workflow.
14. Submit the prompt from `implementer-prompt.md`. Store the write job ID. Call
    `job_wait` with `include_stage_outputs: false` until terminal.
15. Read only `job.result.text`. Never append stage output.
16. Verify `job.result.commit` inside a disposable detached worktree. Remove it
    after running every declared check.
17. Complete specification review.
18. Submit the derived reviewer read workflow with the latest write job as
    parent. Use a fresh reviewer context key. Wait and inspect its result.
19. On `FAIL`, submit an owner-specific fix job. Set `parent_job_id` to the
    latest write job. Reuse the implementer context key.
20. On `PASS`, integrate only the latest write job with `job_integrate`.
21. Append review evidence to `journal.md`. Update `.handover.md`. Commit that
    coordination state as `chore(plan): record phase <N>`.
22. Advance only after Review passes. After the final phase, mark `DONE` and
    invoke `verifying-before-completion`.

## Failure Handling

- `queued` or `running`: wait again.
- `interrupted`: call `job_retry`, then wait.
- `failed` or `cancelled`: mark handover `BLOCKED`.
- `integration_conflict`: preserve branches. Ask the user.

Never stage worker changes. Never cherry-pick or merge worker branches. Never
edit the root repository while an isolated chain remains active.

## Hard Rules

- Phase prompts remain narrow.
- Flat plans are documentation only.
- OpenMCP owns active job state.
- Coordinator owns semantic agent selection.
- Existing phase chains keep stored routing decisions.
- New phases reload task routes and project profiles.
- Every job uses the stored routing profile.
- Terminal job worktrees are disposable.
- Read final output only from `job.result.text`.
- Backend-native sessions never enter prompts or handover.

## References

- `skills/coordinating-multi-model-work/SKILL.md`
- `skills/executing-plans/implementer-prompt.md`
- `skills/verifying-before-completion/SKILL.md`
