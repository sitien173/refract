---
name: executing-plans
description: "Executes a written plan one phase at a time with Plan → Execute → Review gates. Use when running a plan, advancing the current phase, or continuing implementation in this session."
---

# Executing Plans

## Use When

- Plan document exists, user wants execution.
- User asks to run current phase or continue active phase.
- Work advances one phase at a time.

## Workflow

1. Read plan once. Select requested, active, or next unstarted phase.
2. Validate phase: 2–4 related tasks, owner, file set, acceptance criteria, integration checks.
3. **Load resume artifacts (if present)** — read `<plan-dir>/.sessions.json` for worker `SESSION_ID`s, `<plan-dir>/.handover.md` for current phase + next action, and `PHASE-<N>.md` from `read_first`. Skip if flat single-file plan with no folder.
4. **Plan gate** — apply `coordinating-multi-model-work` Plan gate to active phase; output `# ROUTE` block. Create `PHASE-<N>.md` skeleton with Route section.
5. **Execute gate** — route by side:
   - `claude` — simple tasks; edit directly.
   - `codex` (`mcp__codex__codex`) — back-side phases.
   - `gemini` (`mcp__gemini__gemini`) — front-side phases.
   Worker edits files via MCP write tools, returns `## FILES MODIFIED`. Reuse cached `SESSION_ID` from `.sessions.json` if present; send `FIX:` + delta for same-phase fixes. After every MCP call, write returned `SESSION_ID` back to `.sessions.json`.
6. **Review gate** — (a) run phase integration checks for Spec status; (b) Quality scan on `## FILES MODIFIED` (skip for trivial Claude edits / docs-only). Output `# REVIEW` with Spec Status, Quality Findings, Final Status. Finalize `PHASE-<N>.md` with Files / Review / Decisions / Handoff sections.
7. **Update handover** — rewrite `<plan-dir>/.handover.md` with current phase, status, next action, updated `read_first`. Required end of every turn changing plan state.
8. Move to next phase only after Review passes.
9. After last phase, set `.handover.md` status to `DONE`, hand off to `verifying-before-completion` for final verification.

## Hard Rules

- One active phase, one owner, one review.
- Route by side; no default executor.
- No re-explaining whole plan to workers — phase-scoped prompts only.
- Long input (>~8KB / >1500 tokens) → write to repo file (prefer `docs/plans/`), pass path.
- MCP failure → output `BLOCKED`, ask human. No silent retry, switch, or Task/Agent fallback.
- MCP rejects cached `SESSION_ID` (`.sessions.json` present but worker says invalid/expired) → `BLOCKED`. Ask user to clear offending id; no silent re-create.
- `.handover.md` always Claude-authored. Never delegate handover writing to hook or worker.
- Worker output is final edit. No draft handoffs.
- Final project summary only after all phases complete.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — 3-gate workflow and routing.
- `skills/executing-plans/implementer-prompt.md` — phase executor prompt template.
- `skills/verifying-before-completion/SKILL.md` — final verification.