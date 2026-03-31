# Superpowers-CCG

Superpowers-CCG is a fork/enhanced variant of [obra/superpowers](https://github.com/obra/superpowers). It keeps the same skills-driven workflow and adds **CCG multi-model orchestration**: Claude is the **pure orchestrator** (never writes code), routing implementation to **Codex MCP** (backend and systems) and **Gemini MCP** (frontend), with **Opus as the reviewer** for every code-changing path.

> **CCG** = **C**laude + **C**odex + **G**emini

## What You Get

- **Claude as pure orchestrator**: Claude routes, coordinates, and integrates. It never writes implementation code.
- **Multi-model routing (CCG)**: route tasks to Codex (backend and systems) or Gemini (frontend). Use **CROSS_VALIDATION** for full-stack or critical tasks.
- **Opus reviewer**: Opus reviews all code-changing paths directly.
- **MCP tool integration**: external calls go through `mcp__codex__codex` and `mcp__gemini__gemini`.
- **Collaboration checkpoints**: CP1/CP2/CP3 checkpoints are embedded in the main skills.
- **Fail-closed gate**: if a required external model call cannot complete, the workflow stops with `BLOCKED`.

## Quick Start (Claude Code)

### Prerequisites

- [Claude Code](https://docs.claude.com/docs/claude-code) installed (`claude --version`)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) installed and authenticated (`gemini --version`)
- [Codex CLI](https://developers.openai.com/codex/quickstart) installed and authenticated (`codex --version`)
- `uv` / `uvx` available

### Install

```bash
claude plugin marketplace add https://github.com/sitien173/superpowers-ccg
claude plugin install superpowers-ccg
```

### MCP Setup

```bash
# Backend and systems specialist
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp

# Frontend specialist
claude mcp add gemini -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/geminimcp.git geminimcp
```

## Using External Models

You normally do **not** call MCP tools manually. Tell Claude what you want, and the workflow decides when to invoke external models.

- Backend or systems: "Use Codex MCP for the API/database/CI parts, return a patch only."
- Frontend: "Use Gemini MCP for UI/components/styles, return a patch only."
- Cross-validation: "Do CROSS_VALIDATION for this design and reconcile conflicts."
- Code review runs automatically after implementation.

## Model Selection

| Task type | Routing | MCP Tool |
|---|---|---|
| Backend, systems, scripts, CI/CD, Docker, infrastructure | CODEX | `mcp__codex__codex` |
| Frontend (UI/components/styles) | GEMINI | `mcp__gemini__gemini` |
| Full-stack / unclear / high impact | CROSS_VALIDATION | multiple |
| Orchestration only (docs, coordination) | CLAUDE | none |

The routing and checkpoint rules live in `skills/coordinating-multi-model-work/`.

## Checkpoint Protocol

| Checkpoint | When | Purpose |
|---|---|---|
| CP1 | Before first Task call | Assess routing, invoke external model early |
| CP2 | Mid-execution | Triggered by uncertainty, stalled debugging, or repeated failures |
| CP3 | Before claiming completion | Final domain review and verification |

## Differences vs Superpowers (obra/superpowers)

- **Claude as orchestrator-only**: Claude never writes implementation code.
- **Built-in multi-model routing** via MCP tools (Codex, Gemini).
- **Codex covers systems work**: scripts, CI/CD, Dockerfiles, and infrastructure route to Codex.
- **Opus reviews all code** directly.
- **CP checkpoints** enforce evidence-driven collaboration.
- **Skill set changes** align the plugin with the CCG workflow.

## Update

```bash
claude plugin update superpowers-ccg
```

## Testing

See `tests/claude-code/README.md` for the Claude Code skills test suite.

```bash
./tests/claude-code/run-skill-tests.sh
```

## Support

- Issues: https://github.com/sitien173/superpowers-ccg/issues

## Acknowledgments

- [obra/superpowers](https://github.com/obra/superpowers) - Original Superpowers project
- [BryanHoo/superpowers-ccg](https://github.com/BryanHoo/superpowers-ccg) - CCG collaboration fork
- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow) - CCG workflow
- [GuDaStudio/geminimcp](https://github.com/GuDaStudio/geminimcp) - Gemini MCP
- [GuDaStudio/codexmcp](https://github.com/GuDaStudio/codexmcp) - Codex MCP
