# Gate 3 Review Procedure

## Specification and verification

After implementation is terminal and the validated changes have a checkpoint:

1. Require no active project job and a clean root.
2. Inspect `refs/plans/<slug>/phase-<NN>/base..HEAD`. Resolve the anchor through
   [git-anchors.md](git-anchors.md). A stale anchor halts here.
3. Check declared paths and acceptance criteria.
4. Apply `verifying-before-completion` to run every declared command fresh.
5. Recheck the same HEAD and clean state.

Any scope, requirement, or evidence failure blocks quality review.

## Independent quality review

Review only what this phase changed. Submit the first `review` job for a plan
with `fresh_session: true` and a full reviewer contract. Submit later review jobs
prompt-only, scoped to the phase delta with:

- the exact range `refs/plans/<slug>/phase-<NN>/base..HEAD`,
- paths in FILES MODIFIED,
- acceptance criteria and reviewer checklist,
- the selected profile and plan `context_key`.

Instruct the reviewer to judge only whether those changes are correct, secure,
and meet the plan. Pre-existing code outside the delta is out of scope.

Correctness and security findings force `FAIL`. Review through a read-only target
and make no commit for review output.

## Review-fix loop

When review returns blocking findings:

1. Collect every blocking finding into one fix batch.
2. Submit one `FIX:` `implement` job on the plan `context_key`, listing only the
   findings, allowed paths, and checks to rerun.
3. Validate the fix and create a temporary checkpoint commit.
4. Re-review only the fix delta and rerun affected checks.
5. Exit when no blocking findings remain.

Bound this to two automatic fix cycles. Return remaining findings after the
second cycle.

## Finalize phase

After both reviews pass and no job is active:

1. Append evidence to `journal.md`.
2. Checkpoint final coordination state under `tracked`.
3. Set `refs/plans/<slug>/phase-<NN>/impl` to the current HEAD.
4. Update `.handover.md` with both phase refs and summaries.
5. Confirm the root is clean.

The phase checkpoint is temporary branch history. Its refs remain authoritative
after final plan consolidation.

## Finalize plan

After the final phase closes:

1. Mark handover `DONE` and finish every journal.
2. Checkpoint final coordination state under `tracked`.
3. Follow [git-anchors.md](git-anchors.md) to consolidate all plan checkpoints.
4. Use the single plan-level Conventional Commit message from `PLAN.md`.
5. Set the plan `impl` ref and run final verification at that exact HEAD.
6. Confirm the root is clean and HEAD equals the plan `impl` ref.

The completed branch contains one commit for the plan. Phase refs retain the
reviewable implementation and fix checkpoints.