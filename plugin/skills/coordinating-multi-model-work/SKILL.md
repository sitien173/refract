---
name: coordinating-multi-model-work
description: "Coordinates Plan → Execute → Review through OpenMCP, including setup, routing, job lifecycle, independent review, and resume. Load first for delegated plan work."
---

# Coordinating Multi-Model Work

You are Coordinator. You own OpenMCP orchestration, phase boundaries,
specification review, and handover.

Other skills have separate ownership:

- `brainstorming` — design dialogue
- `writing-plans` — plan format
- `executing-plans` — folder-plan phase procedure
- `systematic-debugging` — root-cause method
- `test-driven-development` — implementation test cycle
- `verifying-before-completion` — evidence and claim standard

Do not restate those policies here. Read
[references/tool-contract.md](references/tool-contract.md) before the first
OpenMCP call in a session.

## When to Skip Coordination

Coordination exists for multi-step, risky, or architectural work. Do not route
low-stakes requests through OpenMCP; handle them directly with your own tools and
skip all three gates. Skip when the request is:

- a single-file or trivially scoped edit,
- documentation, comments, config, or formatting,
- a rename, string change, dependency bump, or one-line fix,
- anything the user asks you to just do directly.

Coordinate only when work spans multiple phases or components, carries real
correctness or security risk, needs a design decision, or the user asks for a
plan. When the change is small and scope is obvious, do it directly and note in
one line that you skipped coordination.

## OpenMCP Contract

OpenMCP provides four fixed workflows: `consult`, `implement`, `other`, and
`review`. Canonical gates use `consult`, `implement`, and `review`. Use `other`
only when task guidance selects its explicit profile mapping. Every submission
creates one job in the registered directory. OpenMCP never touches Git; you own
every commit, reset, and cleanliness check. Same-project jobs run FIFO.

Keep provider, model, target, and native session identities private. Select only
workflows and profiles.

## Session Resume Key

Sessions use `project_id`, `context_key`, `workflow`, and target key, primarily
`context_key`. Use the plan slug for every phase and job; never derive another
key. Each workflow keeps its own resumed session.

The first `implement` and `review` jobs carry their full role contracts. Later
jobs on the same workflow and key send only the delta and phase prompt path. Do
not resend contracts, response formats, or role descriptions.

## Git Ownership

You own the entire Git lifecycle. OpenMCP never checks cleanliness, commits,
resets, or restores; assume it did none of these.

- Require an attached branch before every job so commits land; a dirty tree does
  not block submission. Record HEAD and pre-existing dirt to attribute changes.
- Edit or commit known coordination files only when no project job is active.
- After submission, do not edit the root until that job is terminal.
- Every file is visible to workers and nothing is auto-restored. Never expose
  secrets or request unintended changes.
- Submit dependent jobs one at a time; verify each result before the next.

## Setup and Resume

1. Call `status`; require `status="running"`. If unavailable, report and stop.
2. Resolve the Git root and read `openmcp://projects`.
3. Register an absent root with `project_register`; save its `project_id`.
4. Reconcile `active` from `openmcp://projects/<project_id>/jobs`. Fetch a job
   resource only for a specific result.

Job records own state; Git state lives only in the working tree. Wait on active
jobs without local edits. Stop when handover, jobs, and Git disagree.

## Task Guidance

For each new phase, call `task_guide` once with the complete phase request and
`project_id`:

- repository change → `implement`
- code-quality review → `review`
- analysis or advice → `consult`
- other explicitly supported work → `other`

Use the recommended optional profile, or omit it for the configured default.
Validate via `openmcp://projects/<project_id>/profiles` and `openmcp://workflows/<project_id>`; stop on an unavailable or mismatched route.

An active phase keeps its saved guidance; do not call `task_guide` again until a new phase starts.

## Gate 1: Plan

1. Confirm scope, acceptance criteria, risks, and fresh verification commands.
2. Split work that one implementation job cannot safely own.
3. Require consultation for unclear, architectural, cross-component,
   high-impact, or tradeoff-heavy work.
4. For consultation, first reach a clean coordination checkpoint, submit one
   narrow `consult` job, wait with a finite timeout, and use `result.text`.
   Copy relevant findings into the implementation prompt.

Emit:

```text
# ROUTE
- Sequence: consult? -> implement -> review
- Implement Profile: <name | default>
- Consult Profile: <name | default | none>
- Review Profile: <name | default>
- Reason: <one line>
- Done When: <fresh checks>
```

## Gate 2: Execute

For folder plans, `executing-plans` owns the phase-file checkpoint. Dispatch with
[implementer-prompt.md](../executing-plans/implementer-prompt.md).

- Submit one prompt-only `implement` job with the saved route.
- Wait with `timeout_s: 300`; wait for the job to finish and read `result.text` on success or `result.error` on failure.
- On success, read `result.text`, then inspect the actual filesystem changes,
  run the phase validation, and commit the reconciled diff with the phase commit
  message only after validation passes.
- On failure, cancellation, or interruption, read `result.error`. The worker's
  partial changes remain on disk; inspect, reconcile, and report what is
  retained. A retry does not reset the tree, so reconcile first, then retry once
  only when the unchanged immutable job remains valid; otherwise submit a new job.
- Never assume OpenMCP restored anything. All recovery is your own Git.

## Gate 3: Review

After implementation commits, load [references/review.md](references/review.md).
Specification failure blocks quality review. Correctness and security force
`FAIL`. Review through a read-only target; never commit a review.

```text
# CODE QUALITY REVIEW
- Status: PASS | PASS_WITH_DEBT | FAIL
- Findings: <severity, path, line, actionable fix>
- Scope checked: <paths>
```

```text
# REVIEW
- Spec Status: PASS | PASS_WITH_DEBT | FAIL
- Quality Status: PASS | PASS_WITH_DEBT | FAIL
- Next: done | debt + owner | retry/clarify
```

## Handover Contract

```text
docs/plans/<slug>/
  PLAN.md
  .handover.md
  phase-01/{prompt,notes,journal}.md
```

```yaml
---
status: ACTIVE | BLOCKED | DONE
topic: <one-line topic>
current_phase: <N>
next_action: "Execute Phase <N>"
project_id: <OpenMCP project UUID|null>
phase_base: <commit|null>
context_key: <plan-slug>
backlog_ids: [<B-NNN>, ...]
guidance:
  implement: { workflow: implement, profile: <name|null> }
  consult: { workflow: consult, profile: <name|null> }
  review: { workflow: review, profile: <name|null> }
job_refs: { phase: <N>, latest_consult: <id|null>, latest_implementation: <id|null>, latest_review: <id|null> }
read_first: [<file>, ...]
completed_tasks: [{ phase, task, summary }, ...]
completed_phases: [{ phase, commit, summary }, ...]
---
```

No phase is complete without fresh evidence and both required reviews.
