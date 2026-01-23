# Superpowers-CCG

[中文](README-zh.md) | English

Superpowers-CCG is a fork/enhanced variant of [obra/superpowers](https://github.com/obra/superpowers) that adds CCG multi-model collaboration (Claude + Codex MCP + Gemini MCP) to the same “skills-driven” development workflow.

## Quick Install (Claude Code)

1. Add marketplace

```bash
/plugin marketplace add https://github.com/BryanHoo/superpowers-ccg
```

2. Install plugin

```bash
/plugin install superpowers-ccg@BryanHoo-superpowers-ccg
```

After installation, you MUST configure Codex MCP and Gemini MCP for external model routing.

### MCP Setup (required)

```bash
claude mcp add gemini -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/geminimcp.git geminimcp
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp
```

## Differences vs Superpowers (obra/superpowers)

- **Multi-model routing (CCG)**: Superpowers-CCG can route work to **Codex MCP** (backend) and **Gemini MCP** (frontend), with optional dual-model cross-validation for complex cases.
- **MCP tool integration**: External model calls are made through MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`); upstream Superpowers does not include this routing.
- **Extra multi-model “checkpoints”**: Key skills are enhanced with CP1/CP2/CP3 collaboration checkpoints so the orchestrator can decide when to invoke Codex MCP/Gemini MCP.
- **Skill set differs (additions/renames)**: Includes `coordinating-multi-model-work` and other CCG-oriented skill changes compared to upstream naming and content.
- **Inter-model prompts in English**: Prompts sent to Codex MCP/Gemini MCP are expected to be English for consistency (you can still chat with the agent in your own language).
- **Different marketplace source**: Install from `https://github.com/BryanHoo/superpowers-ccg` instead of `obra/superpowers-marketplace`.

## How It Works (Short)

- Claude orchestrates the workflow (requirements clarification -> plan -> execution -> review).
- For eligible tasks, it can invoke Codex MCP/Gemini MCP via MCP tools.
- External MCP tools return patches; the orchestrator reviews and applies changes.

## Update

```bash
/plugin update superpowers-ccg
```

## License

MIT License - see `LICENSE`.

## Support

- Issues: https://github.com/BryanHoo/superpowers-ccg/issues

## Acknowledgments

- [obra/superpowers](https://github.com/obra/superpowers) - Original Superpowers project
- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow) - CCG workflow
- [GuDaStudio/geminimcp](https://github.com/GuDaStudio/geminimcp) - Gemini MCP
- [GuDaStudio/codexmcp](https://github.com/GuDaStudio/codexmcp) - Codex MCP
