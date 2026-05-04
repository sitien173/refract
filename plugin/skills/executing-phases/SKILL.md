---
name: executing-phases
description: "Executes one active implementation phase in the current session by routing to Codex or Gemini, then running Claude review and integration gates. Use when executing-phases, phase execution, run this phase, continue current phase, or same-session implementation is requested."
---

# Executing Phases

## Use When

- User asks to execute a current or active phase in the same session.
- A written plan phase has 2-4 related tasks and clear checks.
- Work should advance one implementation phase at a time.

## Workflow

1. Select exactly one implementation phase from the plan.
2. Confirm the phase has 2-4 related tasks, file set, acceptance criteria, reviewer checklist, and integration checks.
3. Route to one primary executor per phase: Codex by default, Gemini only for UI-heavy work, or Claude when the plan explicitly routes to `claude` or the user overrides routing.
4. Reuse the same worker `SESSION_ID` only for fixes on the same phase; send deltas only.
5. Workers edit files directly via MCP write tools and return External Response Protocol v1.1 with `## FILES MODIFIED`.
6. Claude runs CP4 phase review and returns `PASS`, `PASS_WITH_DEBT`, or `FAIL`.
7. Run integration checks after every phase and before moving on.

## Hard Rules

- Execute one phase at a time.
- Use one primary executor; do not send multiple workers the same implementation phase unless cross-validation is explicitly selected.
- Cross-validation is rare and only for unresolved architecture or true multi-domain ambiguity.
- Do not request draft handoffs; worker output must be final file edits.
- If any Codex or Gemini MCP call fails, output `BLOCKED`; do not retry, do not switch executors, and do not use fallback execution.
- Do not produce the project final summary until all phases and final checks pass.

## References

- `skills/coordinating-multi-model-work/checkpoints.md` — CP1-CP4 phase gates.
- `skills/coordinating-multi-model-work/context-sharing.md` — `SESSION_ID`, `SESSION_POLICY`, tier prompts, and delta rules.
- `skills/coordinating-multi-model-work/GATE.md` — `BLOCKED` behavior for MCP failures.
- `skills/shared/protocol-threshold.md` — exact CP response blocks.
