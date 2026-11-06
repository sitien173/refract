# Phase 2 — Journal: Coordinator owns a single wave procedure

## Coordinator Direct Execution

- Direct execution by user decision; no Refract job, no independent review.
- Created `plugin/skills/coordinating-multi-model-work/references/waves.md` from DESIGN.md approach B, with one added step: checkpoint main-checkout coordination files before integration so the main root is clean.
- Wired `SKILL.md` (sole-exception sentence, handover source-freeze exception), `tool-contract.md` (round-robin exception), `review.md` (handover excluded from root-unchanged check), `git-anchors.md` (phase `base` lands-on-branch definition, kept at the 120-line cap).
- Narrowed `test-contracts.sh` guard: `git worktree` exempt only for the exact `waves.md` path; all other forbidden patterns still scan `waves.md`.
- RED: contract tests failed at the `Wave implementation jobs in separate worktrees` assertion before wiring.
- GREEN: `plugin/tests/run.sh` exit 0; `server/src` diff exit 0.
- Guard proof: appending `job_integrate` to `waves.md` -> exit 1; `git worktree` in `executing-plans/SKILL.md` -> exit 1; restored -> exit 0.
