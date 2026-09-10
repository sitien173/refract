# Gate 3 Review Procedure

## Specification and verification

After implementation is terminal and you have committed the validated changes:

1. Require no active project job and a clean root at your implementation commit.
2. Inspect that implementation commit and `phase_base..HEAD` for the phase.
3. Check declared paths and acceptance criteria.
4. Apply `verifying-before-completion` to run every declared command fresh.
5. Recheck the same HEAD and clean state.

Any scope, requirement, or evidence failure blocks quality review.

## Independent quality review

Review only what this phase changed; never request a full-codebase scan. Submit
the first `review` job for a plan with `fresh_session: true` and a full reviewer
contract. Submit later review jobs prompt-only, scoped to the phase delta with:

- the exact diff to review: `phase_base..HEAD` and the paths in FILES MODIFIED,
- the plan acceptance criteria and reviewer checklist as the rubric,
- the selected review profile and the plan `context_key` (`<plan-slug>`).

State the paths and range in the prompt and instruct the reviewer to judge only
whether those changes are correct, secure, and meet the plan. Pre-existing code
outside the delta is out of scope and is not a finding.

Correctness and security findings force `FAIL`. Run review against a read-only
target so it cannot mutate files; make no commit for a review.

## Review-fix loop

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

## Finalize

After both reviews pass and no job is active:

1. Append evidence to `journal.md`.
2. On `PASS_WITH_DEBT`, file one `inbox` backlog row per debt entry, source
   `<slug>/ph-NN debt`, priority `P1` when the debt carries correctness or
   security risk and `P2` otherwise. Accepted debt must never be lost.
   Blocking findings are never filed; they are fixed inside the phase.
   See `shared/backlog-contract.md`.
3. Update `.handover.md`, recording the HEAD you captured before the initial
   implementation as `phase_base`.
4. Commit coordination state and any debt rows as
   `chore(plan): record phase <N>`. Filing a row never creates its own commit.
5. Confirm the root is clean.
