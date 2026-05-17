---
name: executing-plans
description: "Executes a written plan one phase at a time with Plan → Execute → Review gates. Use when running a plan, advancing the current phase, or continuing implementation in this session."
---

# Executing Plans

## Use When

- A plan document exists and user wants it executed.
- User asks to run the current phase or continue the active phase.
- Work should advance one phase at a time.

## Workflow

1. Read the plan once. Select the requested phase, active phase, or next phase not yet in the repo.
2. Validate the phase: 2–4 related tasks, owner, file set, acceptance criteria, integration checks.
3. **Plan gate** — apply `coordinating-multi-model-work` Plan gate to the active phase; output the `# ROUTE` block.
4. **Execute gate** — route by side:
   - `claude` — simple tasks; edit directly.
   - `codex` (`mcp__codex__codex`) — back-side phases.
   - `gemini` (`mcp__gemini__gemini`) — front-side phases.
   Worker edits files via its MCP write tools and returns `## FILES MODIFIED`. Reuse `SESSION_ID` for same-phase fixes; send deltas only.
5. **Review gate** — (a) run the phase's integration checks for Spec status; (b) Quality scan on `## FILES MODIFIED` (skip for trivial Claude edits / docs-only). Output `# REVIEW` with Spec Status, Quality Findings, Final Status.
6. Move to the next phase only after Review passes.
7. After the last phase, hand off to `verifying-before-completion` for final verification.

## Hard Rules

- One active phase, one owner, one review.
- Route by side; no default executor.
- Do not re-explain the whole plan to workers — phase-scoped prompts only.
- Long input (>~8KB / >1500 tokens) → write to a repo file (prefer `docs/plans/`), pass the path.
- MCP failure → output `BLOCKED`, ask the human. No silent retry, switch, or Task/Agent fallback.
- Worker output is the final edit. No draft handoffs.
- Final project summary only after all phases complete.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — 3-gate workflow and routing.
- `skills/executing-plans/implementer-prompt.md` — phase executor prompt template.
- `skills/verifying-before-completion/SKILL.md` — final verification.
