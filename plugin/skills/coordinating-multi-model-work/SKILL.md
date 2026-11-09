---
name: coordinating-multi-model-work
description: "Use for coordinated work: multi-phase or multi-component changes, risky or design-dependent work, or any request for a plan. Load it before any Plan, Execute, or Review action and when resuming an interrupted plan. Covers Refract setup, routing, job lifecycle, independent review, Git checkpoints, and handover. Skip it for direct work."
compatibility: Requires git and a running Refract server.
---

# Coordinating Multi-Model Work

## Role

You are Coordinator. This skill owns Refract orchestration, phase gates, Git,
and handover. Workers edit files. You judge, commit, and report.

## Terms

- **Slug**: the plan identity in `docs/plans/<slug>/`. Lowercase kebab-case,
  confirmed with the user when the first plan artifact is written, fixed once
  the plan `base` anchor exists. The slug is also the `session`.
- **`<N>` and `<NN>`**: the phase number, and the same number zero-padded to
  two digits.
- **Clean root**: `git status --porcelain` prints nothing.
- **Coordination files**: `PLAN.md`, `DESIGN.md`, `.handover.md`, and the
  current `phase-<NN>/` files. These are the only files you edit during a plan.
- **Phase validation**: every command under the phase `Verification Checks`.

## Refract Contract

Read [references/tool-contract.md](references/tool-contract.md) before the
first Refract call in a session. It owns routing, admission, privacy, session
reuse, waiting, result truncation, and recovery. Apply it to every submit,
wait, and recovery.

Canonical gates use `implement` and `review`; `brainstorming` uses `consult`.
Use the plan slug as `session`. Call `list(path)` once per phase.
Put the complete phase request in a self-contained `submit.prompt`:

- repository change → `implement`
- code-quality review → `review`
- analysis or advice → `consult`
- other explicitly supported work → `other`

Use a recommended profile or omit it for the default.

## Git Ownership

You own the entire Git lifecycle. Refract never checks cleanliness, commits,
resets, or restores. Assume it did none of these.

- Require an attached branch before every job. On detached HEAD, stop and ask
  the user which branch to create or check out.
- Record HEAD and any pre-existing dirt before each job, so you can attribute
  every change. A dirty tree does not block submission.
- Anchors and reviews require a clean root. When other files are dirty, list
  them and ask the user to commit or stash them. Leave user changes exactly as
  they are; the user stashes, resets, or commits them.
- Anchor the plan and every phase through
  [references/git-anchors.md](references/git-anchors.md). Phase commits are
  local checkpoints. Consolidation leaves one plan commit.
- Edit coordination files only while no project job is active.
  After submission, do not edit the root until that job is terminal.
  During a wave, you may still edit main-checkout `.handover.md`.
- Workers see every file. Keep secrets out of prompts and name secret-bearing
  files as out of scope in the phase prompt.
- Submit sequential jobs one at a time. Verify each result before the next.
  Wave implementation jobs in separate worktrees are the sole exception; see
  [references/waves.md](references/waves.md).

## Setup and Resume

1. When the user wants an isolated workspace, run `using-git-worktrees` first
   and use that worktree's actual Git root.
2. Pass the actual Git root, or any directory inside it, as `path` to
   `list(path)`. If unavailable, report it once: planning continues;
   Execute and Review stop until service is available.
3. Resolve plan-artifact tracking as described below.
4. Reconcile with `list(path)`, handover `job_refs`, and Git; act on
   the first match:

| Handover | Jobs | Git | Action |
|---|---|---|---|
| Job ref set | That job active | Any | Wait for it. No local edits. |
| Job ref set | That job terminal | Changes present | Read its result and resume at its gate. |
| No pending ref | None active | Clean at last checkpoint | Continue from `next_action`. |
| Any | Active job absent from handover | Any | Stop. Report the job ID and ask. |
| Any other combination | | | Stop. Report all three states and ask. |

### Plan-Artifact Tracking

`refract.plans.tracking` holds `tracked` or `untracked` and decides whether
anything under `docs/plans` is committed. Read and write it with
`git config --local`, so no global or system value leaks across repositories.
It lives in `.git/config`, which is never pushed and survives history rewriting
and `git clean`. Resolve it once per repository and persist it.

Take the first rung that matches. Rung 2 precedes rung 3, so a repository that
commits plans and later ignores the path stays `tracked`:

| Rung | Condition | Mode | Ask |
|---|---|---|---|
| 1 | The key is already set | Its stored value | No |
| 2 | `git ls-files docs/plans` returns rows | `tracked` | No |
| 3 | `git check-ignore -q docs/plans` succeeds | `untracked` | No |
| 4 | Neither signal | The user's answer | Once, then persist |

In `untracked` mode, append `docs/plans/` to `.git/info/exclude` unless rung 3
matched, and warn once that `git clean -fdx` destroys the plan directory and a
fresh checkout starts without it. Leave `.gitignore` to the project; a
committed ignore file imposes one contributor's choice on everyone.

Tracking mode governs plan-artifact checkpoints alone. Anchors and the
clean-root requirement are identical in both modes.

## Gate 1: Plan

1. Confirm scope, acceptance criteria, risks, and fresh verification commands.
2. Split work that one implementation job cannot safely own.

Emit:

```text
# ROUTE
- Sequence: implement -> review
- Implement Profile: <name | default>
- Review Profile: <name | default>
- Reason: <one line>
- Done When: <fresh checks>
```

## Gate 2: Execute

For folder plans, `executing-plans` owns the phase-file checkpoint.

1. Submit one prompt-only `implement` job with the saved route, built from
   [implementer-prompt.md](../executing-plans/implementer-prompt.md). Its
   prompt names the absolute `phase-<NN>/prompt.md` path.
2. Wait for the terminal result. Answer each `result.pending_question` from
   the plan or the user.
3. Diff the working tree against the recorded HEAD. Compare it with ERP
   `FILES MODIFIED` and the phase file set. An undeclared or out-of-scope path
   is a specification failure for Gate 3.
4. Act on the ERP `NEXT` line, not on the job state:

| Outcome | Action |
|---|---|
| `TASK_COMPLETE` | Run phase validation. Create a temporary checkpoint commit only after it passes. |
| `BLOCKED` | No checkpoint. Answer each `CLARIFICATIONS NEEDED` item from the plan or the user, then submit one resumed job carrying only the answers. |
| `CONTINUE_CONTEXT` | Validate what exists and checkpoint if it passes. Submit one resumed job saying "Continue Phase <NN>". |
| ERP block or `NEXT` missing | Submit one resumed job asking for the ERP response of the current state. |
| Job failed, cancelled, or interrupted | Partial changes remain on disk. Reconcile and report them, then read `result.failure_kind` and apply [Recovery](references/tool-contract.md#recovery): `retry(job_id)` once onto `result.next_target` if the prompt and file set still hold; otherwise submit a new job. |

Bounds: two `BLOCKED` rounds, two continuations, and one ERP re-request per
phase. Past a bound, or on any unanswerable clarification, set handover
`BLOCKED` and report. A retry does not reset the tree. All recovery is your own
Git.

## Gate 3: Review

After the implementation checkpoint, run
[references/review.md](references/review.md): specification review, then
independent quality review, then the bounded review-fix loop.

Derive each status by the first matching rule:

| Findings | Status |
|---|---|
| Any correctness or security finding | `FAIL` |
| Any other blocking finding | `FAIL` |
| Only non-blocking findings, each with a named owner | `PASS_WITH_DEBT` |
| None | `PASS` |

Record debt with its owner in the journal `Review Result` and in handover.

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

## Handover

Read [references/handover.md](references/handover.md) before creating or
editing `.handover.md`. Make card calls at the moments listed in
[references/board.md](references/board.md).

| Status | Meaning | Action |
|---|---|---|
| `ACTIVE` | `next_action` is runnable. | Continue. |
| `BLOCKED` | Waiting on the user. `next_action` names what is needed. | Show `next_action`; continue once the user resolves it. |
| `STALE_ANCHOR` | An anchor failed to resolve. | Stop and report the anchor until the user resolves it. |
| `DONE` | Plan consolidated and verified. | Report completion and stop. |
