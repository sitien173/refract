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

OpenMCP provides exactly `consult`, `implement`, and `review`, one job per
submission, run in the registered directory. OpenMCP never touches Git; you own
every commit, reset, and cleanliness check. Same-project jobs run FIFO without overlap.

Keep provider, model, target, and native session identities private. Select only
workflows and profiles.

## Session Resume Key

OpenMCP resumes a worker session by the combination of `project_id`,
`context_key`, `workflow`, and target key. `context_key` is the primary key.

Use one stable `context_key` for the whole plan: the plan id (`<plan-slug>`).
Submit every `consult`, `implement`, and `review` job, across every phase, with
that same key; the differing `workflow` keeps each session distinct while phases
continue the same worker session. Never derive a per-phase or per-job key.

The session persists per workflow, so keep prompts thin on resume. The first
`implement` and first `review` job on the plan carry the full contract for their
role. Every later job of that same workflow on the same key resumes the live
session and already knows its role and output format: send only the new delta
(tasks, findings, or scope) plus the phase prompt path to read. Do not resend the
worker contract, ERP format, response template, or role description.

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

1. Call `status`; require `status="running"`. If unavailable, report
   `http://127.0.0.1:8765/mcp` and stop.
2. Resolve the Git root and read `openmcp://projects`.
3. Register an absent Git root with `project_register`; save its `project_id`.
4. Read `openmcp://projects/<project_id>/jobs` and reconcile active phase jobs
   before changing files.
5. Use `doctor` only for client integration checks. After global target or
   profile edits, use `reload` and report `restart_required`.

OpenMCP job records are authoritative for job state, but Git state lives only in
your working tree. If a job is queued or running, wait without local edits; if
handover, jobs, and the working tree disagree, stop rather than guessing.

## Task Guidance

For each new phase, call `task_guide` once with the complete phase request and
`project_id`:

- repository change → `implement`
- code-quality review → `review`
- analysis or advice → `consult`

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
- Wait with `timeout_s: 30`; repeat only while `queued` or `running`.
- On success, read `result.text`, then inspect the actual filesystem changes,
  run the phase validation, and commit the reconciled diff with the phase commit
  message only after validation passes.
- On failure, cancellation, or interruption, read `result.error`. The worker's
  partial changes remain on disk; inspect, reconcile, and report what is
  retained. A retry does not reset the tree, so reconcile first, then retry once
  only when the unchanged immutable job remains valid; otherwise submit a new job.
- Never assume OpenMCP restored anything. All recovery is your own Git.

## Gate 3: Review

### Specification and verification

After implementation is terminal and you have committed the validated changes:

1. Require no active project job and a clean root at your implementation commit.
2. Inspect that implementation commit and `phase_base..HEAD` for the phase.
3. Check declared paths and acceptance criteria.
4. Apply `verifying-before-completion` to run every declared command fresh.
5. Recheck the same HEAD and clean state.

Any scope, requirement, or evidence failure blocks quality review.

### Independent quality review

Review only what this phase changed; never request a full-codebase scan. Submit a
prompt-only `review` scoped to the phase delta with:

- the exact diff to review: `phase_base..HEAD` and the paths in FILES MODIFIED,
- the plan acceptance criteria and reviewer checklist as the rubric,
- the selected review profile and the plan `context_key` (`<plan-slug>`).

State the paths and range in the prompt and instruct the reviewer to judge only
whether those changes are correct, secure, and meet the plan. Pre-existing code
outside the delta is out of scope and is not a finding.

Require:

```text
# CODE QUALITY REVIEW
- Status: PASS | PASS_WITH_DEBT | FAIL
- Findings: <severity, path, line, actionable fix>
- Scope checked: <paths>
```

Correctness and security findings force `FAIL`. Run review against a read-only
target so it cannot mutate files; make no commit for a review.

### Review–fix loop

When review returns blocking findings, iterate until it passes or you stop for
the user:

1. Collect the blocking findings — every correctness and security finding, plus
   any the user requires — into one fix batch.
2. Submit one `FIX:` `implement` job on the plan `context_key`, listing only the
   findings, the allowed paths, and the checks to rerun. The worker resumes its
   session, so send no contract or ERP restatement.
3. Validate and commit the fix yourself with a `fix:` message.
4. Re-review only the fix delta: submit a `review` scoped to the paths the fix
   touched and the findings it must clear, not the whole phase again. Re-run only
   the checks the fix affected.
5. Exit when review returns no blocking findings.

Bound this to two automatic fix cycles. If blocking findings remain after the
second cycle, stop and hand the open findings back to the user instead of looping
further.

### Finalize

After both reviews pass and no job is active:

1. Append evidence to `journal.md`.
2. Update `.handover.md`, recording the HEAD you captured before the initial
   implementation as `phase_base`.
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
context_key: <plan-slug>
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
