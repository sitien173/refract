# Superpowers-CCG

Multi-model orchestration plugin for [Claude Code](https://docs.claude.com/docs/claude-code). Claude plans, routes, reviews, and handles simple tasks. **Codex MCP** owns back-side (backend, database, system, infra). **Gemini MCP** owns front-side (UI, CSS, motion, multimodal). New features run CROSS_VALIDATION first.

> **CCG** = **C**laude + **C**odex + **G**emini

## Workflow

Three gates: **Plan → Execute → Review**.

1. **Plan** — for new features / ideation / proposals, run CROSS_VALIDATION first (Codex + Gemini, reconcile). Otherwise Claude gathers minimum context, defines one phase (2–4 tasks, file set, Done When), picks an owner by side.
2. **Execute** — Claude (simple), Codex (back-side), or Gemini (front-side) does the work. Worker edits files via its MCP write tools and returns `## FILES MODIFIED`.
3. **Review** — (a) Spec: Claude runs build/lint/test; (b) Quality scan on changed files (edge cases, error handling, security, naming, duplication, correctness). CRITICAL/HIGH → FAIL; MEDIUM → PASS_WITH_DEBT; LOW noted. Final status: `PASS`, `PASS_WITH_DEBT`, or `FAIL`. Quality scan skipped for docs-only / trivial Claude edits.

Full rules: `skills/coordinating-multi-model-work/SKILL.md`.

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
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp
claude mcp add gemini -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/geminimcp.git geminimcp
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
- [GuDaStudio/codexmcp](https://github.com/GuDaStudio/codexmcp) — Codex MCP
- [GuDaStudio/geminimcp](https://github.com/GuDaStudio/geminimcp) — Gemini MCP
