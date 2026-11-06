# Phase Waves

This file owns wave selection, the multi-phase wave procedure, wave waiting,
wave resume, and wave errors. Every other skill links here instead of
restating these steps. Handover keys `wave_base` and `wave` follow
[handover.md](handover.md).

## Wave selection

A wave is every phase whose dependencies all have a `phase-<NN>/impl` ref.
`writing-plans` owns the `Depends on:` syntax; a missing line means the previous
phase. Snapshot wave membership into handover `wave` when the wave starts.
Dependents of a `requeued` phase wait until it has its `impl` ref.

A single-phase wave runs exactly as today in the main checkout without a
worktree. `wave_base` stays `null` and `wave` stays `[]`, so a plan without
`Depends on:` lines takes no new step.

## Multi-phase wave

Approach: implement in parallel, then integrate and review serially in plan
order on the main checkout. Never review inside a phase worktree.

1. **Prepare.** Require a clean main root. Write every wave phase's
   `prompt.md`, `notes.md`, and `journal.md`; checkpoint them under `tracked`.
   Set `wave_base` to HEAD and add one `wave` entry per phase.
2. **Isolate.** Create one worktree per phase on branch
   `refract/<slug>/phase-<NN>` from `wave_base` through `using-git-worktrees`
   wave mode, which owns directory selection and the ignore check. When any
   creation fails, remove the ones created, report once, and run the whole wave
   sequentially in the main checkout. Never share one checkout between wave jobs.
3. **Implement in parallel.** Submit one `implement` job per worktree with
   `path` set to that worktree. Set each entry's `implementation_job` and state
   `implementing`. The worker edits code only in its worktree and writes
   `notes.md` and `journal.md` to the main checkout by absolute path; each
   phase owns its own `phase-<NN>/` directory.
4. **Wait fairly.** See [Waiting](#waiting).
5. **Validate in the worktree.** Diff the worktree against `wave_base`, compare
   with ERP `FILES MODIFIED`, and run phase validation there. After it passes,
   create a temporary checkpoint commit on the phase branch and set the state
   `implemented`. The Gate 2 outcome table and bounds apply per phase.
6. **Integrate serially, in plan order.** First checkpoint main-checkout
   coordination files under `tracked`, so the main root is clean. Then for each
   `implemented` phase:
   1. Set the state `integrating`. In its worktree, rebase the phase branch
      onto main HEAD, then run phase validation plus the plan's baseline
      commands there.
   2. In the main checkout, set `refs/plans/<slug>/phase-<NN>/base` to HEAD,
      then run `git merge --ff-only refract/<slug>/phase-<NN>`.
   3. Run Gate 3 on the main checkout over
      `refs/plans/<slug>/phase-<NN>/base..HEAD`, including the review-fix loop.
      Write `phase-<NN>/impl` once.
   4. Set the state `integrated`. Run `git worktree remove <worktree>` and
      delete the phase branch; the refs retain the commits.
7. **Integration failure.** On a rebase conflict or a step 6.1 check failure,
   abort the rebase, remove the worktree and branch, and set the state
   `requeued`. No anchor exists for the failed attempt. A requeued phase runs
   sequentially in the main checkout after the wave's other phases, reusing its
   phase files.

After the last phase integrates or requeues, set `wave_base: null` and `wave: []`.

## Waiting

While more than one wave job is active, call `wait` round-robin in plan order
with `timeout_s=60`. Answer each `result.pending_question` immediately. Up to
four active jobs keeps every question inside the default 300-second ask
timeout. With more, a question can expire unanswered; the worker usually
returns `BLOCKED` and normal handling applies. With one active job, the
3600-second rule in [tool-contract.md](tool-contract.md#waiting-and-results)
applies.

Source freeze holds per job root. During a wave, the Coordinator may edit only
main-checkout `.handover.md` while wave jobs are active.

## Resume

Before any change, call `list` for the main checkout and for every recorded
worktree. The first matching row wins:

| Wave state | Observed | Action |
|---|---|---|
| `implementing` | Job active | Wait round-robin. |
| `implementing` | Job terminal | Resume that phase's Gate 2 in its worktree. |
| `implementing` or `implemented` | Worktree missing | Set `requeued`; report. |
| `integrating` | Branch tip is an ancestor of main HEAD | Fast-forward happened; continue at Gate 3. |
| `integrating` | Branch tip is not an ancestor of main HEAD | Redo step 6.1. |
| `integrated` | Worktree still exists | Finish cleanup. |
| Any | Active job in any project absent from handover | Stop, report the job ID, and ask. |

Test ancestry with `git merge-base --is-ancestor <branch tip> HEAD`.

## Errors

| Case | Handling |
|---|---|
| Worktree creation fails | Whole wave runs sequentially in the main checkout; report once. |
| Worktree directory not ignored | The `using-git-worktrees` ignore check must pass before the wave. |
| Worker cannot write main-checkout records | ERP `BLOCKED`; set `requeued`. |
| One phase fails, is cancelled, or exceeds Gate 2 bounds | Recover that phase only; the others continue and integrate. Then `executing-plans` sets `BLOCKED`; `executing-plans-autonomously` sets `requeued` and logs the decision. |
| `targets_unavailable` on a wave submit | Wait `retry_after_s`, then resubmit that phase only. |
| User changes in the main root at wave start | List them and ask; never stash or reset. |
