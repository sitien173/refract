# Handover Schema

This file owns the `.handover.md` front matter. The Coordinator owns every
write to it.

```yaml
---
status: ACTIVE | BLOCKED | STALE_ANCHOR | DONE
topic: <one-line topic>
current_phase: <N>
next_action: "Execute Phase <N>"
project_id: <Refract project UUID|null>
plan_base_ref: <refs/plans/<slug>/base|null>
plan_impl_ref: <refs/plans/<slug>/impl|null>
phase_base: <commit|null>
phase_base_ref: <refs/plans/...|null>
context_key: <plan-slug>
guidance:
  implement: { workflow: implement, profile: <name|null> }
  review: { workflow: review, profile: <name|null> }
job_refs: { phase: <N>, latest_implementation: <id|null>, latest_review: <id|null> }
read_first: [<file>, ...]
checklist: [{ phase, step, status: todo|doing|done|blocked }, ...]
completed_tasks: [{ phase, task, summary }, ...]
completed_phases: [{ phase, base_ref, impl_ref, summary }, ...]
debt: [{ phase, item, owner }, ...]
---
```

## Initial values

`writing-plans` initializes the file with `status: ACTIVE`, `current_phase: 0`,
`next_action: "Execute Phase 1"`, null project and job fields, and empty lists.
`current_phase: 0` means no phase has started.

## Field rules

- `context_key` equals the slug and never changes.
- `job_refs` names the latest job per workflow for `job_refs.phase`. Set it
  immediately after `job_submit` returns, before waiting.
- `phase_base` and other commit fields are advisory caches. Refs win.
- `phase_base_ref` names the current phase `base` ref, never an `impl` ref.
- `read_first` lists paths a resumed session reads before acting. Drop a path
  that no longer exists and note it in the phase journal.
- Under `BLOCKED`, `next_action` states the exact question or decision needed.

## Checklist

`checklist` tracks the steps of the current phase only. Write it when the
phase starts, before the first job: one entry per `PLAN.md` task, then one per
gate step such as implement job, spec review, quality review, and checkpoint.
Write `step` as a short quoted imperative.

- Keep at most one step `doing`. Set it before starting the step.
- Set a step `done` as soon as its evidence exists, not at phase end.
- Set a step `blocked` when handover `status` becomes `BLOCKED` because of it.
- Add a step discovered mid-phase, such as a fix cycle, as `todo`.
- When the phase finalizes, record it in `completed_phases` and replace
  `checklist` with the next phase's steps, or `[]` after the final phase.
- A resumed session continues from the first step that is not `done`.
