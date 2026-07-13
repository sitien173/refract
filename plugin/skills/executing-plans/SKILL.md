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

1. **Read the plan once.** Executable plans require folder layout. Select the requested, active, or next unstarted phase. Confirm it has 2–4 tasks, an owner, file set, acceptance criteria, and integration checks.
2. **Load resume artifacts.** Read `<plan-dir>/.handover.md`, then every file in its validated `read_first` list. If frontmatter is malformed, read `PLAN.md` and current-phase artifacts, then ask the user before execution.
3. **Plan gate.** Apply the canonical Plan gate and output `# ROUTE`. Before creating phase files, require a clean index and clean declared phase files. Record `phase_base`, set phase-scoped `session_refs`, create `<plan-dir>/phase-<NN>/`, and update handover. The worker writes `notes.md` and the implementation response. The coordinator writes `prompt.md` before dispatch.
4. **Execute gate.**
   - `coordinator` — edit directly without committing before Review.
   - `codex` (`backend="codex"`) / `agy` (`backend="agy"`) — write the dispatch prompt from `implementer-prompt.md`. Pass its repo-relative path, the repo-root `cd`, absolute bundled contract paths, and `timeout_s=900`. Reuse a cached identifier only when `session_refs.phase` matches. For same-phase fixes, send `FIX:` plus the delta. Cache only successful, non-empty identifiers and update handover after each call.
5. **Review gate.** Run integration checks and review the diff from `phase_base`. For code-changing phases, route code-quality review to codex in a fresh session using an explicit reviewer prompt, no named profile, and `timeout_s=600`. Reject missing notes blocks, implementation responses, or evidence. Append review output under `## Quality Review`, finalize `## Review Result`, and output `# REVIEW`.
6. **Commit after PASS.** Stage only approved phase files and phase artifacts. Verify the staged path set. Create one Conventional Commit. Record its hash in `journal.md` and `.handover.md`, then commit those state updates as `chore(plan): record phase <N> handover`. Never reset or squash.
7. **Handle FAIL or BLOCKED.** Do not commit implementation changes. Update handover with the blocker, next action, uncommitted files, and preserved session identifier.
8. Advance only after Review passes. Reset phase-scoped session identifiers. After the last phase, set handover status to `DONE` and invoke `verifying-before-completion`.

## Hard Rules

(Gate semantics, path rules, blocked-on-missing-artifacts, and MCP-failure handling are canonical in `coordinating-multi-model-work`. Executor specifics:)

- Phase-scoped prompts only — never re-explain the whole plan to a worker.
- Flat plans are documentation only. Convert them before execution.
- `.handover.md` is always coordinator-authored and updated after every state change.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — canonical gates, routing, worker response format, and `.handover.md` schema.
- `skills/executing-plans/implementer-prompt.md` — dispatch prompt template for codex and agy phases.
- `skills/verifying-before-completion/SKILL.md` — final verification after the last phase.
