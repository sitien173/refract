---
name: executing-plans
description: "Executes written implementation plans one phase at a time with executor, reviewer, and integrator gates. Use when executing a plan in a dedicated session, continuing a saved plan, or keeping the main thread small."
---

# Executing Plans

## Use When

- User wants a written implementation plan executed in a dedicated session.
- Work should progress phase by phase without accumulating full-plan context in the main thread.
- The next active plan phase must be selected and executed.

## Workflow

1. Read the plan once and select the explicitly requested phase, or the next phase not already reflected in the repo.
2. Validate only the active phase: 2-4 related tasks, owner, file set, acceptance criteria, reviewer checklist, and integration checks.
3. Apply CP1 to the active phase and build one phase-scoped context bundle.
4. If routing is not Claude, execute CP2 with Codex by default or Gemini only for UI-heavy work.
5. Reuse worker `SESSION_ID` only for fixes on the same phase; send deltas only.
6. Claude reviews against the phase checklist and returns `PASS`, `PASS_WITH_DEBT`, or `FAIL`.
7. Run integration checks after each reviewed phase.
8. Run final integration and summary only after all phases complete.

## Hard Rules

- One active phase, one primary executor, one Claude review, one integration gate.
- Do not re-explain the whole plan to workers.
- Do not ask a worker for a prototype that Claude will later rewrite.
- Use `CROSS_VALIDATION` only when the current phase cannot be narrowed to one owner.
- If any Codex or Gemini MCP call fails, output `BLOCKED`; do not retry or switch executors.
- Do not produce the project final summary until all phases complete.

## References

- `skills/coordinating-multi-model-work/checkpoints.md` — phase gates and failure handling.
- `skills/coordinating-multi-model-work/context-sharing.md` — phase-scoped context and tier prompts.
- `skills/coordinating-multi-model-work/routing-decision.md` — CP1 routing.
- `skills/verifying-before-completion/SKILL.md` — final verification before completion.
