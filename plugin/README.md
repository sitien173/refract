# Superpowers-CCG

[中文](README-zh.md) | English

Superpowers-CCG is a fork/enhanced variant of [obra/superpowers](https://github.com/obra/superpowers) that adds CCG multi-model collaboration (Claude + Codex + Gemini) to the same “skills-driven” development workflow.

## Quick Install (Claude Code)

1. Add marketplace

```bash
/plugin marketplace add https://github.com/BryanHoo/superpowers-ccg
```

2. Install plugin

```bash
/plugin install superpowers-ccg@BryanHoo-superpowers-ccg
```

After installation, `codeagent-wrapper` is configured into `~/.claude/bin/` automatically (no manual copying).

### Verify

- Confirm the wrapper exists: `~/.claude/bin/codeagent-wrapper`

## Differences vs Superpowers (obra/superpowers)

- **Multi-model routing (CCG)**: Superpowers-CCG can route work to **Codex** (backend) and **Gemini** (frontend), with optional dual-model cross-validation for complex cases.
- **`codeagent-wrapper` included**: This repo/plugin ships a wrapper tool used to invoke external models; upstream Superpowers does not include it.
- **Extra multi-model “checkpoints”**: Key skills are enhanced with CP1/CP2/CP3 collaboration checkpoints so the orchestrator can decide when to invoke Codex/Gemini.
- **Skill set differs (additions/renames)**: Includes `coordinating-multi-model-work` and other CCG-oriented skill changes compared to upstream naming and content.
- **Inter-model prompts in English**: Prompts sent to Codex/Gemini are expected to be English for consistency (you can still chat with the agent in your own language).
- **Different marketplace source**: Install from `https://github.com/BryanHoo/superpowers-ccg` instead of `obra/superpowers-marketplace`.

## How It Works (Short)

- Claude orchestrates the workflow (requirements clarification -> plan -> execution -> review).
- For eligible tasks, it can invoke Codex/Gemini via `codeagent-wrapper`.
- External models return patches; the orchestrator reviews and applies changes.

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
- [cexll/myclaude](https://github.com/cexll/myclaude) - codeagent-wrapper
