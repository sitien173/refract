<!-- refract-shared-version: 3.0.4 -->

# Phase <N> Journal: <phase title>

<!-- Created by the worker per worker-contract.md. Append every block; keep earlier sections. -->

## META

- Plan: docs/plans/<slug>/PLAN.md
- Implementation Profile: <name or default>
- Consultation Profile: <name, default, or n/a>
- Review Profile: <name or default>
- Implementation Job: <Refract job ID or n/a>
- Review Job: <Refract job ID or n/a>
- Started: <ISO timestamp>
- Finished: <ISO timestamp>

## Implementation Response

<!-- Worker appends each full `# EXTERNAL RESPONSE` block here without overwriting prior blocks. -->

## Quality Review

<!-- Coordinator appends the independent review response here. -->

## Review Result

- Spec Status: PENDING
- Quality Status: PENDING
- Debt: none

## Final Checkpoint

- Phase base ref: refs/plans/<slug>/phase-<NN>/base
- Phase implementation ref: refs/plans/<slug>/phase-<NN>/impl
- Plan commit ref: refs/plans/<slug>/impl or `pending`
- State checkpoint: temporary commit, or `n/a (untracked)` when plan artifacts
  are excluded

Phase refs retain review evidence after checkpoint consolidation. The plan ref
names the sole commit retained on the branch.
