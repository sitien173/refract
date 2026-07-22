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

## OpenMCP Contract

OpenMCP provides exactly `consult`, `implement`, and `review`. Each submission
is one job. Successful implementation commits land directly on the registered
branch. Same-project jobs run FIFO without overlap.

Keep provider, model, target, and native session identities private. Select only
workflows and profiles.

## Repository Safety

- Require an attached branch and a clean root before registration and every job.
- Preserve unknown changes. Never stash, reset, delete, or commit them.
- Edit or commit known coordination files only when no project job is queued or
  running.
- After submission, do not edit the root until that job is terminal.
- Ignored files are visible to workers and are never committed or restored.
  Never expose secrets or request ignored-file changes unintentionally.
- Submit dependent jobs one at a time; verify each result before the next.

## Setup and Resume

1. Call `status`; require `status="running"`. If unavailable, report
   `http://127.0.0.1:8765/mcp` and stop.
2. Resolve the Git root and read `openmcp://projects`.
3. Register an absent clean root with `project_register`; save its `project_id`.
4. Read `openmcp://projects/<project_id>/jobs` and reconcile active phase jobs
   before changing files.
5. Use `doctor` only for client integration checks. After global target or
   profile edits, use `reload` and report `restart_required`.

OpenMCP job records are authoritative. If a job is queued or running, wait
without local edits. If handover, jobs, HEAD, and cleanliness disagree, stop
rather than guessing.

## Task Guidance

For each new phase, call `task_guide` once with the complete phase request and
`project_id`:

- repository change → `implement`
- code-quality review → `review`
- analysis or advice → `consult`

Use the recommended optional profile; omit it to use the configured default.
Validate selections through `openmcp://projects/<project_id>/profiles` and
`openmcp://workflows/<project_id>`. Stop on an unavailable or mismatched route.

An active phase keeps its saved guidance. Do not call `task_guide` again until a
new phase starts.

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

- Submit one `implement` job with the saved route.
- Wait with `timeout_s: 30`; repeat only while `queued` or `running`.
- On success, inspect `result.text`, `base_commit`, and `result.commit`. The
  result commit is already on the current branch.
- On failure, cancellation, or interruption, inspect the error. Retry once only
  when the unchanged immutable job remains valid; otherwise submit a new job.
- Never recover with a local reset. OpenMCP restores started unsuccessful jobs;
  dirty-preflight changes and ignored files remain untouched.

## Gate 3: Review

### Specification and verification

After implementation is terminal:

1. Require no active project job, HEAD at `result.commit`, and a clean root.
2. Inspect `base_commit..result.commit` for the job and
   `phase_base..result.commit` for the phase.
3. Check declared paths and acceptance criteria.
4. Apply `verifying-before-completion` to run every declared command fresh.
5. Recheck the same HEAD and clean state.

Any scope, requirement, or evidence failure blocks quality review.

### Independent quality review

Submit `review` against the current repository with:

- the exact implementation commit and cumulative phase range,
- the selected review profile,
- a unique `<phase-prefix>/review/<implementation-job-id>` context key,
- no commit message.

Require:

```text
# CODE QUALITY REVIEW
- Status: PASS | PASS_WITH_DEBT | FAIL
- Findings: <severity, path, line, actionable fix>
- Scope checked: <paths>
```

Correctness and security findings force `FAIL`. A review must leave the same
clean HEAD; attempted writes make the job fail.

A fix is a new `implement` job against the current clean branch. Put the review
findings and delta requirements in its prompt, then repeat specification
verification and independent review over the cumulative phase range.

### Finalize

After both reviews pass and no job is active:

1. Append evidence to `journal.md`.
2. Update `.handover.md`, including the initial implementation `base_commit` as
   `phase_base`.
3. Commit only coordination state as `chore(plan): record phase <N>`.
4. Confirm the root is clean.

Emit:

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
context_prefix: <plan-slug>/phase-<NN>
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
