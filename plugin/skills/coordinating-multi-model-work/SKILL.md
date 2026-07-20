---
name: coordinating-multi-model-work
description: "Canonical three-gate (Plan, Execute, Review) workflow coordinating delegated OpenMCP jobs: project setup, task routing, routing profiles, isolated execution, independent review, and resumable integration. Load first for any planning, routing, execution, review, or resume action."
---

# Coordinating Multi-Model Work

You are Coordinator while this skill is active. Delegated agents use
nicknames. Provider, model, and CLI identities remain private configuration.

You are the primary workflow owner. Route phases, review specifications,
supervise jobs, verify evidence, approve integration, and maintain handover.
Delegate consultation, implementation, and independent quality review. OpenMCP
owns isolation, contexts, routing, commits, and durable jobs. Do not perform
delegated implementation. User instructions override this workflow.

Read [references/tool-contract.md](references/tool-contract.md) before the first
OpenMCP call in a session for tool signatures, workflows, resources, and states.

# Project Setup

Before the first executable repository phase:

1. Call `setup_instruction` with the repository root; follow its guidance.
2. Read `openmcp://projects`. Resolve the Git root and match it there.
3. Register only when that root is absent: call `project_register` with the
   clean repository root and an `alias`.
4. Put any project routing overrides in `.openmcp/config.toml`; keep daemon
   settings and targets in the global OpenMCP config. Commit config changes.
5. Store the returned `project_id` in `.handover.md`.
6. Run `doctor` to validate the integration before submitting jobs.

# Task Routing

Call `task_route` once before each new phase. Pass the phase request and
`project_id` when available. Do not reroute an existing phase chain. The tool
returns task-route definitions. It does not classify work.

You must:

1. Break the request into distinct use cases.
2. Read the returned template semantically.
3. Choose agent nicknames defined by that template.
4. Read each delegated route's stable `execution_role`.
5. Follow configured consultant and reviewer references.
6. Select one implementation owner per phase.
7. Split phases whose use cases need different owners.
8. Keep workflow names out of `# ROUTE`.

`recommend` is the public nickname. `role` describes responsibility.
`execution_role` labels the routing-profile role and context key; it does not
derive a workflow name. Submit the built-in `implement` workflow for code
changes, the built-in `consult` workflow for consultation, and the built-in
`review` workflow for independent quality review. OpenMCP routes each built-in
workflow through the selected profile and matches a target by capability.
Confirm `implement`, `consult`, and `review` through
`openmcp://workflows/<project_id>` before submission. A registered custom
project workflow keeps its own name. Stop when a required workflow does not
exist.

# Routing Profiles

This feature is named **Routing Profiles**. Each profile maps stable roles onto
configured routes and targets.

1. Read `openmcp://projects/<project_id>/routing-profiles` when registered.
2. Otherwise read `openmcp://routing-profiles`.
3. Honor an explicit user profile only when available.
4. Otherwise use the effective default returned by that resource.
5. Store the selected profile in `.handover.md`.
6. Pass `routing_profile` with every submitted job.

Keep one profile throughout a job chain. New phases reload configuration.
Submitted jobs retain their saved execution plans.

# Gate 1: Plan

Review the request and phase specification. Select one implementation owner
and one routing profile. Do not design complex solutions unaided.

Use the `task_route` result before selecting the owner. Make the decision.
Never expect OpenMCP to infer the owner from task words.

Select the configured consultant for non-trivial phases. Skip consultation only
for fully specified, low-risk routine work. Consultation is mandatory for
unclear, full-stack, high-impact, architectural, or tradeoff-heavy work.

## Consultation

1. Submit the built-in `consult` workflow for the consultant.
2. Use `<plan-slug>/consultant/<execution_role>` as `context_key`.
3. Ask one narrow question with constraints and desired output.
4. Call `job_wait` with `include_stage_outputs: false`.
5. Wait for terminal `succeeded` state.
6. Reconcile `job.result.text` against user requirements.

Never integrate consultation jobs. Reuse context only within the same plan.

Output:

```text
# ROUTE
- Owner: <selected nickname>
- Consultant: none | <selected nickname>
- Reviewer: <selected nickname>
- Routing Profile: <name>
- Reason: [one line]
- Done When: [fresh checks]
```

# Gate 2: Execute

## Phase checkpoint

External jobs require a clean repository.

1. Create the phase prompt and context prefix.
2. Commit preparation as `chore(plan): prepare phase <N>`.
3. Record that clean commit as `phase_base`.
4. Confirm the repository remains clean.

The preparation commit becomes the integration base. Never edit the root during
an isolated chain. Resume through
`openmcp://projects/<project_id>/jobs` and the context prefix.

## Implementation

Submit the built-in `implement` workflow with:

- `project_id`: stored project identifier.
- `routing_profile`: stored phase profile.
- `inputs.prompt`: thin worker dispatch prompt.
- `inputs.commit_message`: phase Conventional Commit message.
- `context_key`: `<plan-slug>/phase-<NN>/<owner_execution_role>`.
- `parent_job_id`: empty initially.

Then call `job_wait` with `include_stage_outputs: false`.

- `queued` or `running`: wait again.
- `succeeded`: read `job.result.text`, then continue.
- `interrupted`: call `job_retry`, then wait.
- `failed` or `cancelled`: output `BLOCKED`.
- `integration_conflict`: preserve branches and block.

Never concatenate `stage.text` with `job.result.text`. Compact waits omit
intermediate outputs and prevent duplicate agent messages.

Workers never change Git history. OpenMCP commits successful implementation stages.

## Same-phase fixes

Submit the `implement` workflow and the same profile. Set `parent_job_id` to the
latest implement job. Reuse the implementer context key. Send `FIX:` plus only
delta context. Use a `fix:` commit message.

# Gate 3: Review

Perform specification review. The selected reviewer performs code-quality
review. Both must pass before integration.

## Isolated verification

Terminal jobs release their OpenMCP worktrees. Do not expect the execution
worktree to remain. Create a disposable detached worktree at
`job.result.commit`. Run every declared check there. Remove that worktree after
verification.

Review these ranges:

- Implementation: `job.integration_base..job.result.commit`.
- Whole phase: `phase_base..job.result.commit`.

Reject undeclared paths, unmet requirements, missing task notes, missing
responses, or missing evidence.

## Independent quality review

1. Submit the built-in `review` workflow with the latest implement job as parent.
2. Pass the stored routing profile.
3. Use `<phase-prefix>/reviewer/<reviewer_execution_role>/<latest-implement-job-id>`.
4. Require review of the exact implementation range.
5. Wait with `include_stage_outputs: false`.
6. Inspect only `job.result.text`.

Require:

```text
# CODE QUALITY REVIEW
- Status: PASS | PASS_WITH_DEBT | FAIL
- Findings: [severity, path, line, actionable fix]
- Scope checked: [paths]
```

Correctness and security findings force `FAIL`. Quality findings become
`PASS_WITH_DEBT`. Failed reviews return to Same-phase fixes.

## Integration

After both reviews pass, call `job_integrate` on the latest implement job. Never
merge, cherry-pick, reset, or stage worker changes manually.

Then append review evidence to `journal.md`. Update `.handover.md`. Record
integrated commits. Commit coordination state as
`chore(plan): record phase <N>`.

Output:

```text
# REVIEW
- Spec Status: PASS | PASS_WITH_DEBT | FAIL
- Quality Status: PASS | PASS_WITH_DEBT | FAIL
- Next: done | debt + owner | retry/clarify
```

# Resume Artifacts

```text
docs/plans/<slug>/
  PLAN.md
  .handover.md
  phase-01/{prompt,notes,journal}.md
```

`.handover.md` contains:

```yaml
---
status: ACTIVE | BLOCKED | DONE
topic: <one-line topic>
current_phase: <N>
owner: <nickname|null>
owner_execution_role: <role|null>
consultant: <nickname|null>
consultant_execution_role: <role|null>
reviewer: <nickname|null>
reviewer_execution_role: <role|null>
routing_profile: <name|null>
next_action: "Execute Phase <N>"
phase_base: <commit|null>
project_id: <OpenMCP project UUID|null>
context_prefix: <plan-slug>/phase-<NN>
job_refs: { phase: <N>, latest_consult: <id|null>, latest_implement: <id|null>, latest_review: <id|null> }
read_first: [ <file>, ... ]
completed_tasks: [ { phase, task, summary }, ... ]
completed_phases: [ { phase, commit, summary }, ... ]
---
```

OpenMCP remains authoritative during active chains. Rewrite handover after
integration.

# Hard Rules

- Remain the primary workflow owner.
- Use `task_route`; perform semantic routing.
- Follow `setup_instruction`; register only an absent, clean project root.
- Expose delegated agents by nickname only.
- Delegate implementation but own orchestration.
- Use configured consultant, owner, and reviewer nicknames.
- Require independent review for every code-changing phase.
- Never expose provider-native session identifiers.
- Never mutate the root during isolated chains.
- Never depend on terminal job worktrees remaining present.
- Never duplicate stage and result output.
- Never integrate read-only jobs.
- Never integrate before both reviews pass.
- Use parent jobs for reviews and fixes.
- No completion claim without fresh evidence.
