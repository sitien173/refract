---
name: coordinating-multi-model-work
description: "Use for coordinated work: multi-phase or multi-component changes, risky or design-dependent work, or any request for a plan. Load it before any Plan, Execute, or Review action and when resuming an interrupted plan. Covers OpenMCP setup, routing, job lifecycle, independent review, Git checkpoints, and handover. Skip it for direct work."
compatibility: Requires git and a running OpenMCP server.
---

# Coordinating Multi-Model Work

## Role

You are Coordinator. You own OpenMCP orchestration, phase boundaries,
specification review, Git, and handover. Workers edit files. You judge,
commit, and report.

Apply each neighbouring policy from its owner: scope from `using-superpowers`,
design from `brainstorming`, plan format from `writing-plans`, the phase
procedure from `executing-plans`, root cause from `systematic-debugging`, test
order from `test-driven-development`, evidence from
`verifying-before-completion`, and isolation from `using-git-worktrees`.

Read [references/tool-contract.md](references/tool-contract.md) before the
first OpenMCP call in a session. When `using-superpowers` classified the
request as direct, leave this skill and do the work with your own tools.

## Terms

- **Slug**: the plan identity in `docs/plans/<slug>/`. Lowercase kebab-case,
  confirmed with the user when the first plan artifact is written, fixed once
  the plan `base` anchor exists. The slug is also the `context_key`.
- **`<N>` and `<NN>`**: the phase number, and the same number zero-padded to
  two digits.
- **Clean root**: `git status --porcelain` prints nothing.
- **Coordination files**: `PLAN.md`, `DESIGN.md`, `.handover.md`, and the
  current `phase-<NN>/` files. These are the only files you edit during a plan.
- **Phase validation**: every command under the phase `Verification Checks`.

## OpenMCP Contract

OpenMCP provides four fixed workflows: `consult`, `implement`, `other`, and
`review`. Canonical gates use `consult`, `implement`, and `review`; use `other`
only when task guidance selects its explicit profile mapping. Jobs run in the
registered directory; OpenMCP never touches Git. Admission is reader/writer/session-fair; identical sessions serialize.

Keep provider, model, configured target and native session identities private;
select only public workflows/profiles; native identity is not input. Require configured read-only targets for `consult`/`review`.

## Session Resume Key

The session key is `project_id`, `context_key`, `workflow`, and target key.
Use the plan slug as `context_key` for every phase and job. Each workflow keeps
its own resumed session.

- The first `implement` job and the first `review` job of a plan use
  `fresh_session: true` and carry their full role contracts.
- Later jobs on the same workflow omit `fresh_session`, resume that session,
  and send only the delta plus the phase prompt path.
- A retry keeps its setting, so a fresh-job retry starts fresh again.

## Git Ownership

You own the entire Git lifecycle. OpenMCP never checks cleanliness, commits,
resets, or restores. Assume it did none of these.

- Require an attached branch before every job. On detached HEAD, stop and ask
  the user which branch to create or check out.
- Record HEAD and any pre-existing dirt before each job, so you can attribute
  every change. A dirty tree does not block submission.
- Anchors and reviews require a clean root. When other files are dirty, list
  them and ask the user to commit or stash them. Leave user changes exactly as
  they are; never stash, reset, or commit them yourself.
- Anchor the plan and every phase through
  [references/git-anchors.md](references/git-anchors.md). Phase commits are
  local checkpoints. Consolidation leaves one plan commit.
- Edit coordination files only while no project job is active.
  After submission, do not edit the root until that job is terminal.
- Workers see every file. Keep secrets out of prompts and name secret-bearing
  files as out of scope in the phase prompt.
- Submit dependent jobs one at a time. Verify each result before the next.

## Setup and Resume

1. When the user wants an isolated workspace, run `using-git-worktrees` first
   and use that worktree's actual Git root.
2. Pass the actual Git root to `project_resolve(path=...)`; it must exist and
   OpenMCP does not walk up to find a Git root. Retain the returned project ID.
   If unavailable, report it once: planning continues and records a skipped
   consult reason; Execute and Review stop until service is available.
3. Resolve plan-artifact tracking as described below.
4. Reconcile with `job_list(project_id)`, handover `job_refs`, and Git; act on
   the first match:

| Handover | Jobs | Git | Action |
|---|---|---|---|
| Job ref set | That job active | Any | Wait under the waiting rule. No local edits. |
| Job ref set | That job terminal | Changes present | Read its result and resume at its gate. |
| No pending ref | None active | Clean at last checkpoint | Continue from `next_action`. |
| Any | Active job absent from handover | Any | Stop. Report the job ID and ask. |
| Any other combination | | | Stop. Report all three states and ask. |

Use `job_wait` for the full result. Job records own job state; Git state lives
only in the working tree.

### Plan-Artifact Tracking

`ccg.plans.tracking` holds `tracked` or `untracked` and decides whether anything
under `docs/plans` is committed. Read and write it with `git config --local`, so
no global or system value leaks across repositories. It lives in `.git/config`,
which is never pushed, survives history rewriting and `git clean`, and so cannot
exclude itself. Resolve it once per repository and persist it.

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
fresh checkout starts without it. Leave `.gitignore` untouched; a committed
ignore file imposes one contributor's choice on everyone.

Tracking mode governs plan-artifact checkpoints alone. Plan and phase anchors
are written in both modes, and the clean-root requirement is identical in both.

## Task Guidance

For each new phase, call `task_guide(project_id)` once. Put the complete phase
request in self-contained `job_submit.prompt`:

- repository change → `implement`
- code-quality review → `review`
- analysis or advice → `consult`
- other explicitly supported work → `other`

Use a recommended profile or omit it for the default. Validate public names
only; use actual guidance/errors for unsupported mappings and never invent
fields or substitute an unapproved route.

An active phase keeps its saved guidance.

## Gate 1: Plan

1. Confirm scope, acceptance criteria, risks, and fresh verification commands.
2. Split work that one implementation job cannot safely own.
3. Consult when the work is unclear, architectural, cross-component,
   high-impact, or tradeoff-heavy and OpenMCP is running. Otherwise record the
   skipped consult under `Reason`.
4. To consult: reach a clean root with coordination files checkpointed under
   `tracked`, submit one narrow `consult` job, wait under the waiting rule, and
   read the result in the wait response. Copy relevant findings into the implementation prompt.
5. After the consult, confirm the root is unchanged. A changed root or a failed
   consult goes into `Reason`; ask the user whether to proceed without it.

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

## Waiting Rule

Start one sequential `job_wait` per job with the default 3600-second heartbeat;
never poll, sleep, use a short hardcoded timeout, or overlap replacement waits.
Repeat only after nonterminal output; after disconnect reuse the same ID. A
timeout is normal, not failure. Terminal paging uses `result.next_offset` as
`result_offset`, `timeout_s=0`, until null, preserving all text. A saved job
missing from the ten terminal entries requires `job_wait(saved_id, timeout_s=0)`
before it can be called unknown; absence never permits duplicate submission.

## Gate 2: Execute

For folder plans, `executing-plans` owns the phase-file checkpoint. Dispatch with
[implementer-prompt.md](../executing-plans/implementer-prompt.md).

1. Submit one prompt-only `implement` job with the saved route.
2. Wait using the default heartbeat rule. Read the complete result from the
   wait response.
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
| Job failed, cancelled, or interrupted | Partial changes remain on disk. Reconcile and report them. Then `job_retry` once if the prompt and file set still hold; otherwise submit a new job. |

Bounds: two `BLOCKED` rounds, two continuations, and one ERP re-request per
phase. Past a bound, or on any unanswerable clarification, set handover
`BLOCKED` and report. A retry does not reset the tree. All recovery is your own
Git.

## Gate 3: Review

After the implementation checkpoint, load
[references/review.md](references/review.md). Review through a read-only target
and confirm the root is unchanged afterwards. Never commit a review.

Specification failures and blocking quality findings both enter the bounded
review-fix loop in `review.md`. A specification failure blocks quality review
until it is fixed.

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

## Handover Contract

```text
docs/plans/<slug>/
  PLAN.md
  DESIGN.md
  .handover.md
  phase-01/{prompt,notes,journal}.md
```

Read [references/handover.md](references/handover.md) before creating or editing
`.handover.md`. Status values:

| Status | Meaning |
|---|---|
| `ACTIVE` | `next_action` is runnable. |
| `BLOCKED` | Waiting on the user. `next_action` names what is needed. |
| `STALE_ANCHOR` | An anchor failed to resolve. Stop until the user resolves it. |
| `DONE` | Plan consolidated and verified. |

Refs are authoritative. Commit fields are advisory caches. Resolve both through
[references/git-anchors.md](references/git-anchors.md) before use. A phase is
complete after fresh evidence and both reviews. A plan is complete only after
all phase checkpoints are consolidated into its single branch commit.
