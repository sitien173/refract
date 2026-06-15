---
name: executing-plans
description: "Executes a written plan one phase at a time with Plan → Execute → Review gates. Use when running a plan, advancing the current phase, or continuing implementation in this session."
---

# Executing Plans

Phase-by-phase runner. The Plan / Execute / Review gates, routing table, worker response format, and `.handover.md` schema all live in `coordinating-multi-model-work` — load it first.

## Use When

- Plan document exists, user wants execution.
- User asks to run current phase or continue active phase.

## Workflow

1. **Read the plan once.** Select the requested, active, or next unstarted phase. Confirm it has 2–4 tasks, an owner, file set, acceptance criteria, integration checks.
2. **Load resume artifacts.** For folder-layout plans, read `<plan-dir>/.handover.md` (current phase, next action, cached `session_refs`) then every file in `read_first`. Skip for flat single-file plans.
3. **Plan gate.** Apply `coordinating-multi-model-work` Plan gate to the active phase and output the `# ROUTE` block. Create `<plan-dir>/phase-<NN>/` lazily — only `journal.md` (with Route skeleton) is pre-written. Worker writes `notes.md`; the coordinator writes `prompt.md` immediately before dispatch for Codex/Gemini phases.
4. **Execute gate.**
   - `coordinator` — edit directly, commit per logical change.
   - `codex` (`backend="codex"`) / `gemini` (`backend="gemini"` or `"agy"`) — write dispatch prompt to `<plan-dir>/phase-<NN>/prompt.md` (template in `implementer-prompt.md`), pass its **absolute** path to `mcp__openmcp__run`. Every path inside the prompt body and the `cd` argument must also be absolute with forward slashes on Windows. Reuse cached `SESSION_ID` from `session_refs` if present; same-phase fix → `FIX:` + delta. Write the returned `SESSION_ID` back to `session_refs` after every MCP call.
5. **Review gate.** Run integration checks + `git show` per task commit (Spec). Reject the phase if commits, `notes.md` `## Task <M>` blocks, or `journal.md` External Response section are missing. Output `# REVIEW`. Finalize Squash Commit sections of `journal.md`. On `PASS`, squash all phase task commits per the Conventional Commits squash protocol in `coordinating-multi-model-work`: `git reset --soft HEAD~<count> && git commit -m "<type>[scope]: <description>"`.
6. **Update handover.** Rewrite `.handover.md` with current phase, status, next action, `read_first`, and one `completed_tasks` row per finished task.
7. Advance to the next phase only after Review passes. After the last phase, set `.handover.md` status to `DONE` and hand off to `verifying-before-completion`.

## Hard Rules

(Gate semantics, absolute-path rule, blocked-on-missing-artifacts, and MCP-failure handling are canonical in `coordinating-multi-model-work`. Executor specifics:)

- Phase-scoped prompts only — never re-explain the whole plan to a worker.
- Advance to the next phase only after Review passes; `.handover.md` is always coordinator-authored, rewritten on every state change.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — canonical gates, routing, worker response format, `.handover.md` schema, squash protocol.
- `skills/executing-plans/implementer-prompt.md` — dispatch prompt template for Codex / Gemini phases.
- `skills/verifying-before-completion/SKILL.md` — final verification after the last phase.
