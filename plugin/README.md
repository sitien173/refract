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

- **Prompts to file.** Dispatch prompt body lives at `docs/plans/<slug>/prompts/phase-<N>.md`; the MCP `PROMPT` field is just a pointer. Inline allowed only for one- or two-sentence asks with no context.
- **One commit per task** by the worker, message prefix `phase-<N>.task-<M>: <subject>`. Claude does not commit on the worker's behalf.
- **Decision note per task** at `notes/phase-<N>.task-<M>.md` — captures decisions made outside the spec, deviations, tradeoffs, assumptions, follow-ups. Empty sections written as `- none`.
- **One EXTERNAL RESPONSE per phase** at `responses/phase-<N>.md` (aggregates per-task commits, files modified, spec compliance).
- **Completion line** as the final line of the worker reply:
  ```
  Phase <N> completed. Commit hashes: ["<hash>"]. SessionID: "<id>". Note files: [...]. Response file: docs/plans/<slug>/responses/phase-<N>.md.
  ```

### Example plan layout

```
docs/plans/2026-05-21-user-auth/
  PLAN.md                            # phases, ownership, Done When
  PHASE-1.md                         # phase journal (Route → Files → Commits → Review → Decisions → Handoff)
  PHASE-2.md
  .handover.md                       # terse resume pointer (Claude-authored, ≤500 tokens)
  .sessions.json                     # gitignored — Codex/Gemini SESSION_ID cache
  prompts/
    phase-1.md                       # full dispatch spec for Phase 1 (Codex)
    phase-2.md                       # full dispatch spec for Phase 2 (Gemini)
  notes/
    phase-1.task-1.md                # per-task decision notes
    phase-1.task-2.md
    phase-2.task-1.md
  responses/
    phase-1.md                       # full EXTERNAL RESPONSE from Codex
    phase-2.md                       # full EXTERNAL RESPONSE from Gemini
```

`prompts/`, `notes/`, `responses/`, `PHASE-*.md`, `PLAN.md`, `.handover.md` are committed — durable audit trail. Only `.sessions.json` is gitignored (local worker state).

### End-to-end example

User: *"Add user auth with email + password. UI on the settings page."*

1. **CROSS_VALIDATION** — Claude asks Codex and Gemini the same narrow question (bcrypt vs argon2? session vs JWT?), reconciles divergences, picks direction.
2. **`/write-plan`** — Claude writes `docs/plans/2026-05-21-user-auth/PLAN.md` with two phases:
   - Phase 1 (Codex / back-side): hash + verify, sessions table, login/logout endpoints.
   - Phase 2 (Gemini / front-side): settings-page form, validation, error states.
   Scaffolds `.handover.md`, `.sessions.json`, and `prompts/` `notes/` `responses/` dirs.
3. **`/execute-plan` Phase 1** — Claude writes `prompts/phase-1.md`, calls `mcp__codex__codex` with the path. Codex implements three tasks, commits each (`phase-1.task-1: add bcrypt helper`, …), drops three notes in `notes/`, writes the phase response to `responses/phase-1.md`, returns the completion line.
4. **Review Phase 1** — Claude runs `git show` per commit + integration tests, scans changed files, marks PHASE-1.md `DONE`, updates `.handover.md` `completed_tasks`.
5. **Phase 2** — same loop with Gemini.
6. **Verify** — `verifying-before-completion` runs the full Done When across both phases.

If a session breaks at any point, the next session reads `.handover.md` first and resumes from the listed `read_first` files.

## Routing (by side, no default)

| Phase | Owner | MCP Tool |
|---|---|---|
| Simple/trivial — one-line edit, rename, doc tweak, clarification | Claude | none |
| **Back-side**: backend, API, logic, database, system, infra, CI/CD, scripts, server-side tests | Codex | `mcp__codex__codex` |
| **Front-side**: UI, CSS, layout, motion, canvas/SVG, client interactions, multimodal, large-context UI/doc sweeps | Gemini | `mcp__gemini__gemini` |
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
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) (`gemini --version`)
- `uv` / `uvx`

### MCP setup

```bash
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/sitien173/codexmcp.git codexmcp
claude mcp add gemini -s user --transport stdio -- uvx --from git+https://github.com/sitien173/geminimcp.git geminimcp
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
- [sitien173/codexmcp](https://github.com/sitien173/codexmcp) — Codex MCP
- [sitien173/geminimcp](https://github.com/sitien173/geminimcp) — Gemini MCP
