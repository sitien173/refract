# Superpowers-CCCG

Superpowers-CCCG is a fork/enhanced variant of [obra/superpowers](https://github.com/obra/superpowers). It keeps the same skills-driven workflow, and adds **CCCG multi-model orchestration**: Claude is the **pure orchestrator** (never writes code), routing all implementation to **Codex MCP** (backend), **Gemini MCP** (frontend), and **Cursor MCP** (general implementation + code quality review) with optional cross-validation.

> **CCCG** = **C**laude + **C**odex + **C**ursor + **G**emini

## What You Get

- **Claude as pure orchestrator**: Claude routes, coordinates, and integrates — it never writes implementation code.
- **Multi-model routing (CCCG)**: route tasks to Codex (backend), Gemini (frontend), or Cursor (general: debugging, refactoring, DevOps, scripts). Use **CROSS_VALIDATION** for full-stack/critical tasks.
- **Cursor dual role**: implementation agent (CURSOR routing) AND code quality reviewer (when Codex/Gemini implements). No self-review — Opus reviews Cursor's work.
- **MCP tool integration**: external calls go through MCP tools: `mcp__codex__codex`, `mcp__gemini__gemini`, `mcp__cursor__cursor`.
- **Collaboration checkpoints**: CP1/CP2/CP3 checkpoints embedded in key skills to decide when to call external models.
- **Fail-closed gate**: if a required external model call cannot complete, the workflow stops with `BLOCKED` rather than guessing. All coding tasks are BLOCKED if no external models are available.

## Quick Start (Claude Code)

### Prerequisites

- [Claude Code](https://docs.claude.com/docs/claude-code) installed (`claude --version`)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) installed and authenticated (`gemini --version`)
- [Codex CLI](https://developers.openai.com/codex/quickstart) installed and authenticated (`codex --version`)
- [Cursor Agent CLI](https://github.com/sitien173/cursormcp) — `agent` binary available in PATH (or `%LOCALAPPDATA%\cursor-agent\agent.cmd` on Windows)
- `uv` / `uvx` available — install via:
  - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`

### Install

1) Add marketplace

```bash
claude plugin marketplace add https://github.com/sitien173/superpowers-cccg
```

2) Install plugin

```bash
claude plugin install superpowers-cccg
```

### MCP Setup (required)

After installation, configure the MCP servers so the orchestrator can route work to them.

```bash
# Backend specialist
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp

# Frontend specialist
claude mcp add gemini -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/geminimcp.git geminimcp

# General implementation + code quality reviewer
claude mcp add cursor -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/cursormcp.git cursormcp
```

## Using External Models

You typically do **not** call MCP tools manually. Tell Claude what you want, and the workflow decides when to invoke external models.

- Ask for backend help: "Use Codex MCP for the API/database parts, return a patch only."
- Ask for frontend help: "Use Gemini MCP for UI/components/styles, return a patch only."
- Ask for general implementation: "Debug this flaky test" or "Refactor the logging utility" — routes to Cursor.
- Ask for extra confidence: "Do CROSS_VALIDATION (Codex + Gemini) for this design, and reconcile conflicts."
- Code quality review runs automatically after implementation — Cursor reviews Codex/Gemini work, Opus reviews Cursor's work.

Note: prompts sent to external models are expected to be **English** for consistency (you can still chat with Claude in any language).

## Model Selection

| Task type | Routing | MCP Tool |
|---|---|---|
| Backend (APIs, DB, auth, perf) | CODEX | `mcp__codex__codex` |
| Frontend (UI/components/styles) | GEMINI | `mcp__gemini__gemini` |
| General (debugging, refactoring, DevOps, scripts) | CURSOR | `mcp__cursor__cursor` |
| Full-stack / unclear / high impact | CROSS_VALIDATION | multiple |
| Orchestration only (docs, coordination) | CLAUDE | none |

The routing/checkpoint rules live in `skills/coordinating-multi-model-work/`.

## Checkpoint Protocol

| Checkpoint | When | Purpose |
|---|---|---|
| CP1 | Before first Task call | Assess routing, invoke external model early |
| CP2 | Mid-execution | Triggered by uncertainty, stalled debugging, 2+ failures |
| CP3 | Before claiming completion | Final domain + code quality review |

## Differences vs Superpowers (obra/superpowers)

- **Claude as orchestrator-only**: Claude never writes implementation code — all coding routes to external models.
- **Built-in multi-model routing** via MCP tools (Codex, Gemini, Cursor).
- **Cursor dual role**: implementation agent (CURSOR routing) + code quality reviewer (for Codex/Gemini work).
- **Deterministic reviewer rule**: `Reviewer = (Implementer == Cursor ? Opus : Cursor)` — no self-review.
- **CP checkpoints** (CP1/CP2/CP3) added to enforce evidence-driven collaboration.
- **Tiered fail-closed gate**: all implementation routes are strict-BLOCKED on failure; quality review falls back to Opus when Cursor reviews, but is BLOCKED when Opus must review Cursor's work (no self-review allowed).
- **Skill set changes** (additions/renames) for the CCCG workflow.

## Update

```bash
claude plugin update superpowers-cccg
```

## Testing

See `tests/claude-code/README.md` for the Claude Code skills test suite.

```bash
# Run all fast tests
./tests/claude-code/run-skill-tests.sh

# Run a single test
./tests/claude-code/run-skill-tests.sh --test <test-file>.sh
```

## License

MIT License - see `LICENSE`.

## Support

- Issues: https://github.com/sitien173/superpowers-cccg/issues

## Acknowledgments

- [obra/superpowers](https://github.com/obra/superpowers) - Original Superpowers project
- [BryanHoo/superpowers-ccg](https://github.com/BryanHoo/superpowers-ccg) - CCG multi-model collaboration fork (upstream)
- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow) - CCG workflow
- [GuDaStudio/geminimcp](https://github.com/GuDaStudio/geminimcp) - Gemini MCP
- [GuDaStudio/codexmcp](https://github.com/GuDaStudio/codexmcp) - Codex MCP
- [sitien173/cursormcp](https://github.com/sitien173/cursormcp) - Cursor MCP
