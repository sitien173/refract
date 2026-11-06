# Phase 4 — Journal: Workers run isolated with central records

## Coordinator Direct Execution

- Direct execution by user decision; no Refract job, no independent review.
- `implementer-prompt.md`: `<code-root>` and `<records-root>` replace `<repo-root>` in the template and dispatch envelope; outside a wave both equal `<repo-root>`.
- `worker-contract.md`: records only under `<records-root>`; a sandbox write failure there returns `BLOCKED`.
- `erp.md`: `FILES MODIFIED` uses repository-relative paths from both roots.
- `using-git-worktrees`: new Wave Mode (skips the consent question and native tool, creates `refract/<slug>/phase-<NN>` from `wave_base`, runs setup, skips baseline, never falls back to the current directory); the single-worktree constraint and sandbox fallback now exclude wave mode. 172 of 180 lines.
- RED: contract tests failed at the `<code-root>`/`<records-root>` assertion. GREEN: `plugin/tests/run.sh` exit 0; `server/src` diff exit 0.
