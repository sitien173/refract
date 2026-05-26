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
3. **Load resume artifacts (if present)** — read `<plan-dir>/.handover.md` for current phase, next action, and cached worker `SESSION_ID`s (`session_refs` frontmatter), then `phase-<NN>/journal.md` from `read_first`. Skip if flat single-file plan with no folder.
4. **Plan gate** — apply `coordinating-multi-model-work` Plan gate to active phase; output `# ROUTE` block. Create `<plan-dir>/phase-<NN>/` directory and `journal.md` skeleton with Route section. No other files pre-created — worker writes `prompt.md`/`notes.md` lazily (Claude writes the prompt before dispatch).
5. **Execute gate** — route by side:
   - `claude` — simple tasks; edit directly. Commit per logical change.
   - `codex` (`mcp__openmcp__run(backend="codex", ...)`) — back-side phases.
   - `gemini` (`mcp__openmcp__run(backend="agy", ...)`) — front-side phases.

   For Codex / Gemini:
   1. Write dispatch prompt to `<plan-dir>/phase-<NN>/prompt.md`; pass the **absolute** path to the worker (Gemini/agy mis-resolves relative paths against unknown CWDs). Every file path inside the prompt body (inputs, outputs, plan dir, notes, journal) must also be absolute. Use forward slashes on Windows. Pass `cd` to `mcp__openmcp__run` as an absolute path too.
   2. Worker commits per task, appends a `## Task <M>` block to `phase-<NN>/notes.md` after each task, appends the full `# EXTERNAL RESPONSE` block to `phase-<NN>/journal.md` at phase end, emits the completion line. Spec in `implementer-prompt.md`.
   3. Reuse cached `SESSION_ID` from `.handover.md` frontmatter (`session_refs`) if present; same-phase fix → `FIX:` + delta. Write returned `SESSION_ID` back to `session_refs` after every MCP call.
6. **Review gate** — (a) `git show <hash>` per commit + run phase integration checks → Spec status; (b) Quality scan on `## FILES MODIFIED` (skip for trivial Claude edits / docs-only). Reject phase if commits, notes.md task blocks, or journal EXTERNAL RESPONSE section missing. Output `# REVIEW`. Finalize Review + Squash Commit sections of `phase-<NN>/journal.md`. On Review PASS, squash all phase task commits: `git reset --soft HEAD~<count> && git commit -m "phase-<N>: <summary>"` — task commits are review artifacts, squash is final history.
7. **Update handover** — rewrite `.handover.md` with current phase, status, next action, `read_first`, and append a `completed_tasks` row per finished task.
8. Move to next phase only after Review passes.
9. After last phase, set `.handover.md` status to `DONE`, hand off to `verifying-before-completion` for final verification.

## Hard Rules

- One active phase, one owner, one review.
- Route by side; no default executor.
- No re-explaining whole plan to workers — phase-scoped prompts only.
- Dispatch prompts written to `<plan-dir>/phase-<NN>/prompt.md` by default; inline allowed only for trivial one-liners.
- **Absolute paths only when talking to MCP workers.** The dispatch-prompt path passed in `PROMPT`, the `cd` arg, and every file path mentioned inside the prompt body must be absolute (forward slashes on Windows). Never pass relative paths — Gemini in particular will fall back to a device-wide scan.
- One commit per task by the worker. Missing commit hashes in `## COMMITS` blocks the Review gate. Task commits are review artifacts only — Claude squashes to one `phase-<N>: <summary>` commit after Review PASS.
- Per-phase `phase-<NN>/notes.md` (with one `## Task <M>` block per task) + appended `# EXTERNAL RESPONSE` section in `phase-<NN>/journal.md` required before phase is marked complete.
- MCP failure → output `BLOCKED`, ask human. No silent retry, switch, or Task/Agent fallback.
- MCP rejects cached `SESSION_ID` (present in `.handover.md` `session_refs` but worker says invalid/expired) → `BLOCKED`. Ask user to clear offending id (set to `null` in `session_refs`); no silent re-create.
- `.handover.md` always Claude-authored. Never delegate handover writing to hook or worker.
- Worker output is final edit. No draft handoffs.
- Final project summary only after all phases complete.

## References

- `skills/coordinating-multi-model-work/SKILL.md` — 3-gate workflow and routing.
- `skills/executing-plans/implementer-prompt.md` — phase executor prompt template.
- `skills/verifying-before-completion/SKILL.md` — final verification.