# Superpowers-CCG

Multi-model orchestration plugin for [Claude Code](https://docs.claude.com/docs/claude-code). Claude plans, routes, reviews, and handles simple tasks. **Codex MCP** owns back-side (backend, database, system, infra). **Gemini MCP** owns front-side (UI, CSS, motion, multimodal). New features run CROSS_VALIDATION first.

> **CCG** = **C**laude + **C**odex + **G**emini

## Workflow

Three gates: **Plan → Execute → Review**.

1. **Plan** — for new features / ideation / proposals, run CROSS_VALIDATION first (Codex + Gemini, reconcile). Otherwise Claude gathers minimum context, defines one phase (2–4 tasks, file set, Done When), picks an owner by side.
2. **Execute** — Claude (simple), Codex (back-side), or Gemini (front-side) does the work. Dispatch prompt is written to a file by default; the worker commits per task, writes a decision note per task, writes one EXTERNAL RESPONSE per phase, and emits a completion line with commit hashes + session id + artifact paths.
3. **Review** — (a) Spec: Claude runs `git show <hash>` on each commit + build/lint/test; (b) Quality scan on changed files (edge cases, error handling, security, naming, duplication, correctness). CRITICAL/HIGH → FAIL; MEDIUM → PASS_WITH_DEBT; LOW noted. Missing commits or note/response files → FAIL. Quality scan skipped for docs-only / trivial Claude edits.

Full rules: `skills/coordinating-multi-model-work/SKILL.md`.

### Per-task discipline (Codex / Gemini phases)

- **Prompts to file.** Dispatch prompt body lives at `docs/plans/<slug>/phase-<NN>/prompt.md` (zero-padded phase id); the MCP `PROMPT` field is just a pointer. Inline allowed only for one- or two-sentence asks with no context.
- **One commit per task** by the worker, message prefix `phase-<N>.task-<M>: <subject>`. Claude does not commit on the worker's behalf.
- **Decision notes — one file per phase** at `phase-<NN>/notes.md`. Worker appends a `## Task <M>` block after each task with sub-sections: Decisions, Spec deviations, Tradeoffs, Assumptions, Follow-ups. Empty sub-sections written as `- none`.
- **Phase journal** at `phase-<NN>/journal.md`. Claude writes the Route skeleton at phase start; worker appends the full `# EXTERNAL RESPONSE` block under `## External Response` at phase end. Claude finalizes Review + Squash Commit sections after Review.
- **Completion line** as the final line of the worker reply (META carries the structured fields, so the line stays terse):
  ```
  Phase <N> completed. Journal: docs/plans/<slug>/phase-<NN>/journal.md.
  ```

### Example plan layout

```
docs/plans/2026-05-21-user-auth/
  PLAN.md                            # phases, ownership, Done When
  .handover.md                       # terse resume pointer + session_refs
  phase-01/                          # created lazily when Phase 1 starts
    prompt.md                        # full dispatch spec for Phase 1 (Codex)
    notes.md                         # ## Task 1, ## Task 2, ## Task 3 decision blocks
    journal.md                       # Route + appended EXTERNAL RESPONSE + Review
  phase-02/
    prompt.md                        # Gemini dispatch
    notes.md
    journal.md
```

Phase folders are committed once the phase finishes — durable audit trail. No `.gitkeep`, no pre-scaffolded empty dirs.

### End-to-end example

User: *"Add user auth with email + password. UI on the settings page."*

1. **CROSS_VALIDATION** — Claude asks Codex and Gemini the same narrow question (bcrypt vs argon2? session vs JWT?), reconciles divergences, picks direction.
2. **`/write-plan`** — Claude writes `docs/plans/2026-05-21-user-auth/PLAN.md` with two phases:
   - Phase 1 (Codex / back-side): hash + verify, sessions table, login/logout endpoints.
   - Phase 2 (Gemini / front-side): settings-page form, validation, error states.
   Scaffolds `.handover.md` (with `session_refs`). Phase folders are created lazily when each phase starts.
3. **`/execute-plan` Phase 1** — Claude creates `phase-01/` with `journal.md` (Route skeleton), writes `phase-01/prompt.md`, calls `mcp__openmcp__run(backend="codex", PROMPT="Read spec: <ABS>/docs/plans/.../phase-01/prompt.md", cd="...")`. Codex implements three tasks, commits each (`phase-1.task-1: add bcrypt helper`, …), appends a `## Task <M>` block to `phase-01/notes.md` after each, appends the EXTERNAL RESPONSE to `phase-01/journal.md`, returns the completion line.
4. **Review Phase 1** — Claude runs `git show` per commit + integration tests, scans changed files; on PASS squashes task commits into one (`git reset --soft HEAD~N && git commit -m "phase-1: …"`), finalizes Review + Squash Commit sections of `phase-01/journal.md`, updates `.handover.md` `completed_tasks`.
5. **Phase 2** — same loop with Gemini.
6. **Verify** — `verifying-before-completion` runs the full Done When across both phases.

If a session breaks at any point, the next session reads `.handover.md` first and resumes from the listed `read_first` files.

## Routing (by side, no default)

| Phase | Owner | MCP Tool |
|---|---|---|
| Simple/trivial — one-line edit, rename, doc tweak, clarification | Claude | none |
| **Back-side**: backend, API, logic, database, system, infra, CI/CD, scripts, server-side tests | Codex | `mcp__openmcp__run(backend="codex", ...)` |
| **Front-side**: UI, CSS, layout, motion, canvas/SVG, client interactions, multimodal, large-context UI/doc sweeps | Gemini | `mcp__openmcp__run(backend="agy", ...)` |
| New feature / ideation / proposal (before plan) | Cross-Validation → assign side | both |
| Full-stack | Split into back-side + front-side sub-phases | both |

User overrides ("use Codex" / "use Gemini" / "skip cross-validation") always win.

## Install

```bash
claude plugin marketplace add https://github.com/sitien173/superpowers-ccg
claude plugin install superpowers-ccg
```

### Prerequisites

- [Claude Code](https://docs.claude.com/docs/claude-code) (`claude --version`)
- [Codex CLI](https://developers.openai.com/codex/quickstart) (`codex --version`)
- [Antigravity CLI](https://github.com/google-gemini/gemini-cli) — used as the `agy` backend for the front-side role (`agy --version`)
- `uv` / `uvx`

### MCP setup

Single unified server — [openmcp](https://github.com/sitien173/openmcp) — exposes one tool (`mcp__openmcp__run`) with a `backend` field (`"codex"` or `"agy"`):

```bash
claude mcp add openmcp -s user --transport stdio -- uvx --from "git+https://github.com/sitien173/openmcp.git#subdirectory=openmcp" openmcp
```

If you had `codexmcp` / `geminimcp` from a previous install, remove them:

```bash
claude mcp remove codex
claude mcp remove gemini
```

## Fail-Closed Rule

Any Codex/Gemini MCP failure (timeout, unavailable, session-failed, permission-blocked, prompt too long) → workflow outputs `BLOCKED` and asks for human consent before retry or alternate route. No silent fallback.

## Update

```bash
claude plugin update superpowers-ccg
```

## Support

Issues: https://github.com/sitien173/superpowers-ccg/issues

## Acknowledgments

- [obra/superpowers](https://github.com/obra/superpowers) — original Superpowers
- [BryanHoo/superpowers-ccg](https://github.com/BryanHoo/superpowers-ccg) — CCG fork
- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow) — CCG workflow
- [sitien173/openmcp](https://github.com/sitien173/openmcp) — unified Codex + Antigravity (agy) MCP server
