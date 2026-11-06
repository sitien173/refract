# Parallel Phase Waves Design

**Status:** Confirmed 2026-11-06
**Consultation:** consult2 job ecc50253 found seven verified gaps that shaped approach B; consult1 job 9e7d1231 failed `transient` with no `next_target`, so cross-validation is single-source.

## Purpose

Cut plan wall-clock time by implementing independent phases concurrently.
Implementation dominates job time: recent implement jobs on this repository ran
4 to 50 minutes, reviews 0.5 to 4 minutes.

## Users and Success Criteria

Users are plan authors using `writing-plans` and the Coordinator running
`/refract:execute-plan` and `/refract:execute-plan-all`.

| Criterion | Required behavior |
|---|---|
| Concurrency | A plan with two `Depends on: none` phases shows two active jobs in two projects at once in `list`. |
| Integration | Every wave phase lands on the plan branch by fast-forward and passes its checks plus baseline commands. |
| Review | Every landed phase is reviewed on the main checkout over `phase-<NN>/base..HEAD`. |
| Consolidation | The plan ends as one commit, unchanged procedure. |
| Compatibility | A plan without `Depends on:` lines produces the same refs and handover result as today. |
| Contracts | Contract and stats tests cover the template, `waves.md`, the handover schema, and the narrowed guard. |

## Constraints, Invariants, and Non-Goals

### Facts the design relies on

- Server admits at most one job per project; different projects run concurrently up to global `max_jobs` (`tool-contract.md`, Admission).
- A project is `git rev-parse --show-toplevel` (`server/src/refract/runtime.py:217`), so each linked worktree is a separate project.
- Default worker question timeout is 300 s (`server/src/refract/config.py:27`).
- Server-side `depends_on` and parallel readers were removed in `6f73b05c`.
- An overlay and `job_integrate` worktree feature was added in `296d270d` and removed in `2ce5ee48` without a recorded reason; `plugin/tests/test-contracts.sh:174` guards its vocabulary.

### Invariants

| Invariant | How it holds |
|---|---|
| Coordinator owns all Git | Only the Coordinator runs `worktree add/remove`, rebase, checkpoint commits, and fast-forward. Workers never commit. |
| Every landed change is independently reviewed | Gate 3 reviews each phase on the main checkout after it lands. |
| One plan commit | Fast-forward keeps the plan branch linear; consolidation is unchanged. |
| `impl` written once | Anchors are written only at integration; failed attempts write none. |
| Sequential plans unchanged | A single-phase wave takes today's path; `wave` stays `null`. |
| No server change | Same six tools; one job per project still holds. |
| Source freeze | After submission, do not edit that job's root until it is terminal. Exception: during a wave, the Coordinator may edit main-checkout `.handover.md` while jobs are active; the review root-unchanged check excludes it. |

### Non-goals

- Parallel jobs in one checkout.
- Overlapping review of phase N with implementation of phase N+1.
- Server admission changes.
- Automatic dependency inference from code.
- Plugin-level wave width cap; server `max_jobs` and target `max_concurrency` bound width.

## Chosen Approach

B: implement wave phases in parallel worktrees, then integrate and review each
phase serially on the main checkout in plan order.

- Rejected A, parallel review in each worktree before integration: needs attempt-scoped anchors and separate reviewed and integrated states, and reviews code outside its integrated context.
- Rejected overlapping review with the next implementation: a review fix to phase N lands under phase N+1's work.
- Rejected server-side parallel admission in one checkout: breaks file attribution and was removed in `6f73b05c`.

## Architecture and Data Flow

### Plan format, owned by `writing-plans`

- Optional `**Depends on:** Phase 1, Phase 3` or `**Depends on:** none` per phase. A missing line means the phase depends on the previous phase.
- Phases may be independent only when their `Files:` lists are disjoint and neither needs an API, schema, or fixture the other creates. Shared files such as lockfiles or `CHANGELOG.md` force a dependency.
- `writing-plans` rejects cycles and unknown phase numbers.

### Wave selection

A wave is every phase whose dependencies all have a `phase-<NN>/impl` ref.
Membership is snapshotted into handover at wave start. A single-phase wave runs
exactly as today in the main checkout without a worktree.
`/refract:execute-plan` runs one wave and stops. `/refract:execute-plan-all`
loops waves.

### Multi-phase wave

1. **Prepare.** Clean main root. Write every wave phase's `prompt.md`, `notes.md`, and `journal.md`; checkpoint under `tracked`. Record `wave.base = HEAD`.
2. **Isolate.** Per phase, create a worktree on branch `refract/<slug>/phase-<NN>` from `wave.base`, using `using-git-worktrees` directory selection and ignore check. Any creation failure runs the whole wave sequentially in the main checkout, reported once. Never fall back to a shared checkout.
3. **Implement in parallel.** One `implement` job per worktree with `path` set to the worktree. The worker edits code only in its worktree and writes `notes.md` and `journal.md` to the main checkout by absolute path; each phase owns its own `phase-<NN>/` directory.
4. **Wait fairly.** While more than one job is active, call `wait` round-robin with `timeout_s=60`; answer pending questions immediately. Up to four active jobs keeps every question inside the 300 s ask timeout. With one active job, the 3600 s rule applies.
5. **Validate in the worktree.** Scope diff against `wave.base`, phase checks, then a temporary checkpoint on the worktree branch. The Gate 2 outcome table and bounds apply per phase.
6. **Integrate serially, in plan order.** For each implemented phase:
   1. In its worktree, rebase the phase branch onto main `HEAD`, then run phase checks plus baseline commands.
   2. In the main checkout, set `phase-<NN>/base = HEAD`, then `git merge --ff-only refract/<slug>/phase-<NN>`.
   3. Run Gate 3 on the main checkout over `phase-<NN>/base..HEAD`, including the review-fix loop. Write `phase-<NN>/impl` once.
   4. Remove the worktree and branch; refs retain the commits.
7. **Integration failure.** On rebase conflict or a 6.1 check failure, abort the rebase, remove the worktree, and set the phase `requeued`. It runs sequentially in the main checkout after the wave's other phases. No anchor exists for the failed attempt.

`phase-<NN>/base` now means HEAD before the phase landed on the plan branch.
For sequential phases this is the same commit as today.

### Handover schema additions

```yaml
wave:                      # null outside a multi-phase wave
  base: <commit>
  phases:
    - phase: <N>
      state: implementing | implemented | integrating | integrated | requeued
      worktree: <absolute path|null>
      branch: refract/<slug>/phase-<NN>
      implementation_job: <id|null>
```

- `current_phase` and `job_refs` keep describing the phase running gates on the main checkout.
- `checklist` allows at most one `doing` step per phase.
- `implementation_job` is written immediately after `submit` returns, before waiting.

### Resume additions

Before any mutation, call `list` for the main checkout and every recorded
worktree. First matching row wins.

| Wave phase state | Observed | Action |
|---|---|---|
| `implementing` | Job active | Wait round-robin. |
| `implementing` | Job terminal | Resume that phase's Gate 2 in its worktree. |
| `implementing` or `implemented` | Worktree missing | Set `requeued`; report. |
| `integrating` | Branch tip is an ancestor of main `HEAD` | Fast-forward happened; continue at Gate 3. |
| `integrating` | Branch tip is not an ancestor of main `HEAD` | Redo step 6.1. |
| `integrated` | Worktree still exists | Finish cleanup. |
| Any | Active job in any project absent from handover | Stop, report the job ID, and ask. |

## Errors and Edge Cases

| Case | Handling |
|---|---|
| Worktree creation fails | Whole wave runs sequentially in the main checkout; reported once. |
| Worktree directory not ignored | Existing `using-git-worktrees` ignore check must pass before the wave. |
| Worker cannot write main-checkout records | ERP `BLOCKED`; set `requeued`. |
| One phase fails, is cancelled, or exceeds Gate 2 bounds | Recovery for that phase only; other phases continue and integrate. Then `/refract:execute-plan` sets `BLOCKED`; `/refract:execute-plan-all` sets `requeued` and logs the decision. |
| `targets_unavailable` on a wave submit | Wait `retry_after_s`, then resubmit that phase only. |
| More than four active jobs | A question can expire unanswered; the worker typically returns `BLOCKED`; normal handling applies. Documented limit. |
| Dependent of a `requeued` phase | Wave selection holds it until the requeued phase has `impl`. |
| User changes in the main root at wave start | Existing rule: list them and ask; never stash or reset. |

## Migration

- Existing plans and handovers need no change. No `Depends on:` means sequential; a missing `wave` field reads as `null`.
- Wave mechanics live in one new reference, `plugin/skills/coordinating-multi-model-work/references/waves.md`; other skills link to it.
- `plugin/tests/test-contracts.sh:174` exempts only `waves.md` from the `git worktree` pattern. `job_integrate`, `integration_base`, `integration_conflict`, and the other patterns stay forbidden.
- The guarded sentence "Submit sequential jobs one at a time" stays; one added sentence names wave implementation jobs in separate worktrees as the sole exception.
- Version 2.5.0 in every manifest and every `refract-shared-version` marker, plus a `CHANGELOG.md` entry.

## Testing

- `plugin/tests/test-contracts.sh`: the `Depends on:` template line and rules; `waves.md` key rules (single-phase fast path, no shared-checkout fallback, 60 s round-robin, `--ff-only`, requeue on failure); the `wave` handover schema; the narrowed guard.
- `plugin/tests/test-stats.sh`: a fixture with an active wave shows each wave phase and state; the existing fixture without a wave produces byte-identical output.
- `plugin/tests/run.sh` passes, including `claude plugin validate`.
- Manual smoke on a scratch repository with two `Depends on: none` phases: two concurrent active jobs in two projects, both phases fast-forwarded and reviewed on the main checkout, one consolidated commit.

## Risks and Open Questions

- The reason the earlier overlay feature was removed is unknown and may apply here.
- Contract tests check documents, not Coordinator behavior; only the manual smoke exercises the real flow.
- Rebasing onto main `HEAD` changes the code a worker produced against `wave.base`; checks in step 6.1 and Gate 3 are the only guard against semantic drift.
