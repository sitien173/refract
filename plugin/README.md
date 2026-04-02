# Superpowers-CCG

Superpowers-CCG is a fork/enhanced variant of [obra/superpowers](https://github.com/obra/superpowers). It keeps the same skills-driven workflow and adds **CCG multi-model orchestration**: Claude is the **pure orchestrator** (never writes code), routing implementation to **Codex MCP** (backend and systems) and **Gemini MCP** (frontend), with **Claude CP4 final spec review** and **Haiku for trivial tasks and fast exploration**.

> **CCG** = **C**laude + **C**odex + **G**emini

## What You Get

- **Claude as pure orchestrator**: Claude routes, coordinates, and integrates. It never writes implementation code.
- **Multi-model routing (CCG)**: route tasks to Codex (backend and systems) or Gemini (frontend). Use **CROSS_VALIDATION** for full-stack or critical tasks.
- **Final spec review**: CP4 performs a pure spec check against the original request and CP1 success criteria.
- **MCP tool integration**: external calls go through `mcp__codex__codex` and `mcp__gemini__gemini`.
- **Collaboration checkpoints**: CP0/CP1/CP2/CP3/CP4 checkpoints are embedded in the main skills.
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

- Backend or systems: "Use Codex MCP for the API/database/CI parts and return the final files directly."
- Frontend: "Use Gemini MCP for UI/components/styles and return the final files directly."
- Cross-validation: "Do CROSS_VALIDATION for this design and reconcile conflicts."
- CP4 final spec review runs automatically at the end of the workflow.

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
| CP0 | Before CP1 | Context acquisition / retrieval using the Hybrid Context Engine |
| CP1 | Immediately after CP0, before first Task call | Task assessment and routing using the CP1 routing matrix |
| CP2 | After CP1 when routed externally | External execution via Gemini/Codex/Cross-Validation with final file output |
| CP3 | After CP2 when reconciliation is needed | Resolve external-model conflicts, gaps, and clarifications before CP4 |
| CP4 | Final step of every workflow | Pure spec review against the original request and CP1 success criteria |

## Differences vs Superpowers (obra/superpowers)

- **Claude as orchestrator-only**: Claude never writes implementation code.
- **Built-in multi-model routing** via MCP tools (Codex, Gemini).
- **Codex covers systems work**: scripts, CI/CD, Dockerfiles, and infrastructure route to Codex.
- **CP4 final spec review is spec-only**: no automatic style, redundancy, or best-practice review is part of the checkpoint flow.
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
