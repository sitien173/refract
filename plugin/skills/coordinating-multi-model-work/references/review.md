# Gate 3 Review Procedure

## Specification and verification

After implementation is terminal and the validated changes have a checkpoint:

1. Require no active project job and a clean root.
2. Inspect `refs/plans/<slug>/phase-<NN>/base..HEAD`. Resolve the anchor through
   [git-anchors.md](git-anchors.md). A stale anchor halts here.
3. Check declared paths and acceptance criteria.
4. Apply `verifying-before-completion` to run every declared command fresh.
   Keep each command, exit status, counts, and failing lines for the reviewer.
5. Recheck the same HEAD and clean state.

Any scope, requirement, or evidence failure blocks quality review and enters
the review-fix loop as blocking findings.

## Independent quality review

Review only what this phase changed. Submit the first `review` job for a plan
with `fresh=true` and a full reviewer contract. Submit later review jobs
prompt-only, scoped to the phase delta with:

- the exact range `refs/plans/<slug>/phase-<NN>/base..HEAD`,
- paths in FILES MODIFIED,
- acceptance criteria and reviewer checklist,
- the selected profile and plan `session`.

Instruct the reviewer to judge only whether those changes are correct, secure,
and meet the plan. Pre-existing code outside the delta is out of scope.

Pass the step 4 check results in the prompt. The reviewer judges from the diff
and those results, runs a targeted test only to reproduce a suspected blocking
finding, and opens its response with the `# CODE QUALITY REVIEW` block from
Gate 3.

Review through a read-only target, confirm the root is unchanged afterwards,
and make no commit for review output. During a wave, the root-unchanged check
excludes main-checkout `.handover.md`; see [waves.md](waves.md).

## Review-fix loop

When specification or quality review returns blocking findings:

1. Collect every blocking finding into one fix batch.
2. Submit one `FIX:` `implement` job on the plan `session`, listing only the
   findings, allowed paths, and affected checks.
3. Run the affected checks fresh and create a temporary checkpoint commit.
4. Read the fix delta against each finding and act on the first matching rule:

| Finding or fix | Action |
|---|---|
| The finding concerns security, data loss, migration, concurrency, authentication, or a public interface | Re-review the fix delta. |
| The fix changes code beyond what the finding names | Re-review the fix delta. |
| Any other fix that addresses its finding, such as a local logic fix with a regression test, a rename, documentation, style, or a test-only change | Close the finding and record the decision in `journal.md`. |

5. Exit when no blocking findings remain.

Bound this to one automatic fix cycle. When the re-review still returns
blocking findings, set handover `BLOCKED` and return them to the user.

## Unusable output

When a `succeeded` job returns output the review cannot use, inspect its
partial local effects first. Then follow Recovery in
[tool-contract.md](tool-contract.md#recovery): call `retry(job_id)` for the next
target, or `retry(job_id, target=X)` to pin one. Require ERP only where the
workflow requires it.

## Finalize phase

After both reviews pass and no job is active:

1. When a fix cycle ran, run every declared command fresh once. Append
   evidence to `journal.md`.
2. Checkpoint final coordination state under `tracked`.
3. Set `refs/plans/<slug>/phase-<NN>/impl` to the current HEAD.
4. Update `.handover.md` with both phase refs and summaries.
5. Confirm the root is clean.

The phase checkpoint is temporary branch history. Its refs remain authoritative
after final plan consolidation.

## Finalize plan

After the final phase closes, follow the sole
[consolidation procedure](git-anchors.md#consolidation). That procedure owns
final coordination state, the replacement commit, and final verification.