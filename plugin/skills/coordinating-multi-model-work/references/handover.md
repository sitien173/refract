# Handover Schema

This file owns the `.handover.md` front matter. The Coordinator owns every
write to it.

```yaml
---
status: ACTIVE | BLOCKED | STALE_ANCHOR | DONE
topic: <one-line topic>
current_phase: <N>
next_action: "Execute Phase <N>"
project_id: <OpenMCP project UUID|null>
plan_base_ref: <refs/plans/<slug>/base|null>
plan_impl_ref: <refs/plans/<slug>/impl|null>
phase_base: <commit|null>
phase_base_ref: <refs/plans/...|null>
context_key: <plan-slug>
guidance:
  implement: { workflow: implement, profile: <name|null> }
  consult: { workflow: consult, profile: <name|null> }
  review: { workflow: review, profile: <name|null> }
job_refs: { phase: <N>, latest_consult: <id|null>, latest_implementation: <id|null>, latest_review: <id|null> }
read_first: [<file>, ...]
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
- `read_first` lists paths a resumed session reads before acting. Drop a path
  that no longer exists and note it in the phase journal.
- Under `BLOCKED`, `next_action` states the exact question or decision needed.
