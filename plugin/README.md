# Superpowers-CCG

Superpowers-CCG is a fork/enhanced variant of [obra/superpowers](https://github.com/obra/superpowers). It keeps the same skills-driven workflow, and adds **CCG multi-model collaboration**: Claude orchestrates, and can route to **Codex MCP** (backend), **Gemini MCP** (frontend), and **Cursor MCP** (code quality review) with optional cross-validation.

## What You Get

- **Multi-model routing (CCG)**: route tasks to Codex (backend) / Gemini (frontend), or use **CROSS_VALIDATION** when uncertain.
- **Cursor code quality layer**: automatic code quality review via Cursor MCP after implementation, replacing the Opus quality reviewer in subagent workflows.
- **MCP tool integration**: external calls go through MCP tools: `mcp__codex__codex`, `mcp__gemini__gemini`, `mcp__cursor__cursor`.
- **Collaboration checkpoints**: CP1/CP2/CP3 checkpoints embedded in key skills to decide when to call external models.
- **Fail-closed gate**: if a required external model call cannot complete, the workflow stops with `BLOCKED` rather than guessing.

## Quick Start (Claude Code)

### Prerequisites

- Claude Code CLI installed (`claude --version`)
- `uvx` available (used by the MCP server install commands below)

### Install

1) Add marketplace

```bash
claude plugin marketplace add https://github.com/sitien173/superpowers-cccg
```

2) Install plugin

```bash
claude plugin install superpowers-ccg
```

### MCP Setup (required)

After installation, configure the MCP servers so the orchestrator can route work to them.

```bash
# Backend specialist
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp

# Frontend specialist
claude mcp add gemini -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/geminimcp.git geminimcp

# Code quality reviewer
claude mcp add cursor -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/cursormcp.git cursormcp
```

## Using External Models

You typically do **not** call MCP tools manually. Tell Claude what you want, and the workflow decides when to invoke external models.

- Ask for backend help: "Use Codex MCP for the API/database parts, return a patch only."
- Ask for frontend help: "Use Gemini MCP for UI/components/styles, return a patch only."
- Ask for extra confidence: "Do CROSS_VALIDATION (Codex + Gemini) for this design, and reconcile conflicts."
- Code quality review via Cursor runs automatically after implementation — no manual invocation needed.

Note: prompts sent to external models are expected to be **English** for consistency (you can still chat with Claude in any language).

## Model Selection

| Task type | Routing | MCP Tool |
|---|---|---|
| Backend (APIs, DB, auth, perf) | CODEX | `mcp__codex__codex` |
| Frontend (UI/components/styles) | GEMINI | `mcp__gemini__gemini` |
| Full-stack / unclear / high impact | CROSS_VALIDATION | both |
| Docs / simple edits | CLAUDE | none |
| Code quality review (automatic) | — | `mcp__cursor__cursor` |

The routing/checkpoint rules live in `skills/coordinating-multi-model-work/`.

## Checkpoint Protocol

| Checkpoint | When | Purpose |
|---|---|---|
| CP1 | Before first Task call | Assess routing, invoke external model early |
| CP2 | Mid-execution | Triggered by uncertainty, stalled debugging, 2+ failures |
| CP3 | Before claiming completion | Final domain + code quality review |

## Differences vs Superpowers (obra/superpowers)

- **Built-in multi-model routing** via MCP tools (Codex, Gemini, Cursor).
- **CP checkpoints** (CP1/CP2/CP3) added to enforce evidence-driven collaboration.
- **Cursor as code quality layer**: automatic post-implementation review replacing Opus quality reviewer.
- **Tiered fail-closed gate**: domain experts are strict-BLOCKED on failure; Cursor has graceful fallback to Opus.
- **Skill set changes** (additions/renames) for the CCG workflow.

## Update

```bash
claude plugin update superpowers-ccg
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
- [BryanHoo/superpowers-ccg](https://github.com/BryanHoo/superpowers-ccg) - CCG multi-model collaboration fork
- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow) - CCG workflow
- [GuDaStudio/geminimcp](https://github.com/GuDaStudio/geminimcp) - Gemini MCP
- [GuDaStudio/codexmcp](https://github.com/GuDaStudio/codexmcp) - Codex MCP
- [sitien173/cursormcp](https://github.com/sitien173/cursormcp) - Cursor MCP
