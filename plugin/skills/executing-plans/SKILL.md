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
4. **Plan gate** — apply `coordinating-multi-model-work` Plan gate to active phase; output `# ROUTE` block. Create `PHASE-<N>.md` skeleton with Route section. Ensure `<plan-dir>/prompts/`, `notes/`, `responses/` dirs exist.
5. **Execute gate** — route by side:
   - `claude` — simple tasks; edit directly. Commit per logical change.
   - `codex` (`mcp__openmcp__run(backend="codex", ...)`) — back-side phases.
   - `gemini` (`mcp__openmcp__run(backend="agy", ...)`) — front-side phases.

   For Codex / Gemini:
   1. Write dispatch prompt to `<plan-dir>/prompts/phase-<N>.md`; pass the path.
   2. Worker commits per task, writes one decision note per task (`notes/phase-<N>.task-<M>.md`), writes the phase response file (`responses/phase-<N>.md`), emits the completion line. Spec in `implementer-prompt.md`.
   3. Reuse cached `SESSION_ID` from `.sessions.json` if present; same-phase fix → `FIX:` + delta. Write returned `SESSION_ID` back after every MCP call.
6. **Review gate** — (a) `git show <hash>` per commit + run phase integration checks → Spec status; (b) Quality scan on `## FILES MODIFIED` (skip for trivial Claude edits / docs-only). Reject phase if commits or note/response files missing. Output `# REVIEW`. Finalize `PHASE-<N>.md`.
7. **Update handover** — rewrite `.handover.md` with current phase, status, next action, `read_first`, and append a `completed_tasks` row per finished task.
8. Move to next phase only after Review passes.
9. After last phase, set `.handover.md` status to `DONE`, hand off to `verifying-before-completion` for final verification.

## Hard Rules

- One active phase, one owner, one review.
- Route by side; no default executor.
- No re-explaining whole plan to workers — phase-scoped prompts only.
- Dispatch prompts written to `<plan-dir>/prompts/<task-id>.md` by default; inline allowed only for trivial one-liners.
- One commit per task by the worker. Missing commit hashes in `## COMMITS` blocks the Review gate.
- Per-task decision note (`notes/phase-<N>.task-<M>.md`) + per-phase response file (`responses/phase-<N>.md`) required before phase is marked complete.
- MCP failure → output `BLOCKED`, ask human. No silent retry, switch, or Task/Agent fallback.
- MCP rejects cached `SESSION_ID` (`.sessions.json` present but worker says invalid/expired) → `BLOCKED`. Ask user to clear offending id; no silent re-create.
- `.handover.md` always Claude-authored. Never delegate handover writing to hook or worker.
- Worker output is final edit. No draft handoffs.
- Final project summary only after all phases complete.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — 3-gate workflow and routing.
- `skills/executing-plans/implementer-prompt.md` — phase executor prompt template.
- `skills/verifying-before-completion/SKILL.md` — final verification.