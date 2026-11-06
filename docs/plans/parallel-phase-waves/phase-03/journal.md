# Phase 3 — Journal: Execution skills and commands run waves

## Coordinator Direct Execution

- Direct execution by user decision; no Refract job, no independent review.
- `executing-plans`: one wave per invocation; step 1 selects the wave and links `waves.md`; single-phase wave runs steps 2 to 10 unchanged; multi-phase wave emits one report per phase and sets `BLOCKED` for a failed phase after the others integrate; step 9 stops after the wave. Kept at the 90-line cap.
- `executing-plans-autonomously`: step 3 loops waves until every phase has `impl`; failed wave phase is `requeued` and logged instead of blocking.
- Commands: `execute-plan.md` says one wave; `execute-plan-all.md` says all waves.
- RED: contract tests failed at the `waves.md` link assertion. GREEN: `plugin/tests/run.sh` exit 0; `server/src` diff exit 0.
