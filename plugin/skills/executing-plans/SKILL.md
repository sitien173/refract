---
name: executing-plans
description: "Executes written plans or active implementation phases one phase at a time with CP1 routing, external execution when needed, CP4 review, and integration gates. Use when executing a plan, executing a current phase, continuing a phase, or same-session implementation is requested."
---

# Executing Plans

## Use When

- User wants a written implementation plan executed in this session or a dedicated session.
- User asks to run the current phase, continue the active phase, or use same-session execution.
- Work should advance one selected implementation phase at a time.

## Workflow

1. Read the plan once and select the explicitly requested phase, active phase, or next phase not already reflected in the repo.
2. Validate only that phase: 2-4 related tasks, owner, file set, acceptance criteria, reviewer checklist, and integration checks.
3. Apply CP1 to the active phase and build one phase-scoped context bundle.
4. Route to one primary executor: Codex by default, Gemini only for UI-heavy work, or Claude when the plan or user says so.
5. Reuse the same worker `SESSION_ID` only for fixes on the same phase; send deltas only.
6. Workers edit files directly via MCP write tools and return External Response Protocol v1.1 with `## FILES MODIFIED`.
7. Claude runs CP4 phase review and returns `PASS`, `PASS_WITH_DEBT`, or `FAIL`.
8. Run integration checks after each reviewed phase and before moving on.
9. Run final integration and summary only after all phases complete.

## Hard Rules

- One active phase, one primary executor, one Claude review, one integration gate.
- Do not re-explain the whole plan to workers.
- Do not request draft handoffs; worker output must be final file edits.
- Use `CROSS_VALIDATION` only when the current phase cannot be narrowed to one owner.
- If any Codex or Gemini MCP call fails, output `BLOCKED`; do not retry or switch executors.
- Do not produce the project final summary until all phases complete.

## References

- `skills/executing-plans/implementer-prompt.md` — phase executor prompt template and ERP format.
- `skills/coordinating-multi-model-work/checkpoints.md` — phase gates and failure handling.
- `skills/coordinating-multi-model-work/context-sharing.md` — phase-scoped context and tier prompts.
- `skills/coordinating-multi-model-work/routing-decision.md` — CP1 routing.
- `skills/verifying-before-completion/SKILL.md` — final verification before completion.
