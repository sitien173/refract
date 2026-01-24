# Superpowers-CCG

[中文](README-zh.md) | English

Superpowers-CCG is a fork/enhanced variant of [obra/superpowers](https://github.com/obra/superpowers). It keeps the same skills-driven workflow, and adds **CCG multi-model collaboration**: Claude orchestrates, and can route to **Codex MCP** (backend) and **Gemini MCP** (frontend) with optional cross-validation.

## What You Get

- **Multi-model routing (CCG)**: route tasks to Codex (backend) / Gemini (frontend), or use **CROSS_VALIDATION** when uncertain.
- **MCP tool integration**: external calls go through MCP tools: `mcp__codex__codex`, `mcp__gemini__gemini`.
- **Collaboration checkpoints**: CP1/CP2/CP3 checkpoints embedded in key skills to decide when to call external models.

## Quick Start (Claude Code)

### Prerequisites

- Claude Code CLI installed (`claude --version`)
- `uvx` available (used by the MCP server install commands below)

### Install

1) Add marketplace

```bash
/plugin marketplace add https://github.com/BryanHoo/superpowers-ccg
```

2) Install plugin

```bash
/plugin install superpowers-ccg@BryanHoo-superpowers-ccg
```

### MCP Setup (required)

After installation, configure Codex MCP and Gemini MCP so the orchestrator can route work to them.

```bash
claude mcp add gemini -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/geminimcp.git geminimcp
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp
```

## Using Codex / Gemini

You typically do **not** call MCP tools manually. Instead, tell Claude what you want, and the workflow will decide when to invoke external models.

- Ask for backend help: "Use Codex MCP for the API/database parts, return a patch only."
- Ask for frontend help: "Use Gemini MCP for UI/components/styles, return a patch only."
- Ask for extra confidence: "Do CROSS_VALIDATION (Codex + Gemini) for this design, and reconcile conflicts."

Note: prompts sent to Codex/Gemini are expected to be **English** for consistency (you can still chat with Claude in any language).

## Model Selection (Recommended)

| Task type | Recommended routing | Why |
|---|---|---|
| Backend (APIs, DB, auth, perf) | CODEX | strongest backend patch suggestions |
| Frontend (UI/components/styles) | GEMINI | strongest UI-centric patch suggestions |
| Full-stack / unclear / high impact | CROSS_VALIDATION | catch misses via dual review |
| Docs / simple edits | CLAUDE | fastest and sufficient |

The routing/checkpoint rules live in `skills/coordinating-multi-model-work/`.

## Differences vs Superpowers (obra/superpowers)

- **Built-in multi-model routing** via MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`).
- **CP checkpoints** (CP1/CP2/CP3) added to enforce evidence-driven collaboration.
- **Skill set changes** (additions/renames) for the CCG workflow.
- **Different marketplace source**: install from `https://github.com/BryanHoo/superpowers-ccg`.

## Update

```bash
/plugin update superpowers-ccg
```

## Testing

See `tests/claude-code/README.md` for the Claude Code skills test suite.

## License

MIT License - see `LICENSE`.

## Support

- Issues: https://github.com/BryanHoo/superpowers-ccg/issues

## Acknowledgments

- [obra/superpowers](https://github.com/obra/superpowers) - Original Superpowers project
- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow) - CCG workflow
- [GuDaStudio/geminimcp](https://github.com/GuDaStudio/geminimcp) - Gemini MCP
- [GuDaStudio/codexmcp](https://github.com/GuDaStudio/codexmcp) - Codex MCP
