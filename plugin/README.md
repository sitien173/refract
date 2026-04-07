# Superpowers-CCG

Superpowers-CCG is a fork/enhanced variant of [obra/superpowers](https://github.com/obra/superpowers). It keeps the same skills-driven workflow and adds **CCG multi-model orchestration**: Claude is the **pure orchestrator** (never writes code), routing implementation to **Codex MCP** (backend and systems) and **Gemini MCP** (frontend), with **Claude CP4 final spec review** and **Haiku for trivial tasks and fast exploration**.

> **CCG** = **C**laude + **C**odex + **G**emini

## What You Get

- **Claude as pure orchestrator**: Claude routes, coordinates, and integrates. It never writes implementation code.
- **Multi-model routing (CCG)**: route tasks to Codex (backend and systems) or Gemini (frontend). Use **CROSS_VALIDATION** for full-stack or critical tasks.
- **Final spec review**: CP4 performs a pure spec check against the original request and CP1 success criteria.
- **MCP tool integration**: external calls go through `mcp__codex__codex` and `mcp__gemini__gemini`.
- **OpenCode support**: the same workflows and skills can be loaded through the OpenCode plugin entrypoint at `.opencode/plugin/superpowers.js`, with visible slash commands exposed through OpenCode's commands directory.
- **Collaboration checkpoints**: CP0/CP1/CP2/CP3/CP4 checkpoints are embedded in the main skills.
- **Smart context sharing**: CP0 produces reusable context artifacts, CP1 builds task-scoped bundles, and same-task follow-ups send deltas only.
- **Fail-closed gate**: if a required external model call cannot complete, the workflow stops with `BLOCKED`.

## Platform Support

| Platform | Entry Point | What You Install |
|---|---|---|
| Claude Code | Claude plugin | `.claude-plugin/` + hooks + skills |
| OpenCode | OpenCode plugin + command files | `plugins/superpowers-ccg.js` + `lib/skills-core.js` + skills + `commands/` symlinks |

## Quick Start

### Claude Code

#### Prerequisites

- [Claude Code](https://docs.claude.com/docs/claude-code) installed (`claude --version`)
- [Gemini CLI](https://github.com/google-gemini/gemini-cli) installed and authenticated (`gemini --version`)
- [Codex CLI](https://developers.openai.com/codex/quickstart) installed and authenticated (`codex --version`)
- `uv` / `uvx` available

#### Install

```bash
claude plugin marketplace add https://github.com/sitien173/superpowers-ccg
claude plugin install superpowers-ccg
```

#### MCP Setup

```bash
# Backend and systems specialist
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp

# Frontend specialist
claude mcp add gemini -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/geminimcp.git geminimcp
```

### OpenCode

#### Prerequisites

- [OpenCode](https://opencode.ai/docs/) installed
- Node.js available
- Git available

#### Install

```bash
mkdir -p ~/.config/opencode
cd ~/.config/opencode
npm install @opencode-ai/plugin

git clone https://github.com/sitien173/superpowers-ccg.git ~/.config/opencode/superpowers-ccg

mkdir -p ~/.config/opencode/plugins
ln -sf ~/.config/opencode/superpowers-ccg/.opencode/plugin/superpowers.js ~/.config/opencode/plugins/superpowers-ccg.js

mkdir -p ~/.config/opencode/commands
ln -sf ~/.config/opencode/superpowers-ccg/.opencode/commands/brainstorm.md ~/.config/opencode/commands/brainstorm.md
ln -sf ~/.config/opencode/superpowers-ccg/.opencode/commands/write-plan.md ~/.config/opencode/commands/write-plan.md
ln -sf ~/.config/opencode/superpowers-ccg/.opencode/commands/execute-plan.md ~/.config/opencode/commands/execute-plan.md
ln -sf ~/.config/opencode/superpowers-ccg/.opencode/commands/debug.md ~/.config/opencode/commands/debug.md
```

Restart OpenCode after creating the symlink.

#### What OpenCode Gets

- Workflow bootstrap from `superpowers-ccg.md`
- Bundled skills from `skills/`
- Shared skill resolution from `lib/skills-core.js`
- Custom tools: `use_skill` and `find_skills`
- Native slash commands linked into `~/.config/opencode/commands/`
- Skill priority: `project:` > personal > `superpowers:`

Visible commands after setup:

- `/brainstorm`
- `/write-plan`
- `/execute-plan`
- `/debug`

Detailed OpenCode usage is in `docs/README.opencode.md`.

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
| CP0 | Before CP1 | Context acquisition with Auggie for local code context and Grok Search for external research |
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

### Claude Code

```bash
./tests/claude-code/run-skill-tests.sh
```

See `tests/claude-code/README.md` for the Claude Code suite, including slower integration coverage.

### OpenCode Static Tests

These do not require the `opencode` binary:

```bash
./tests/opencode/run-tests.sh
```

### OpenCode Integration Tests

These require OpenCode to be installed:

```bash
./tests/opencode/run-tests.sh --integration
```

## Support

- Issues: https://github.com/sitien173/superpowers-ccg/issues

## Acknowledgments

- [obra/superpowers](https://github.com/obra/superpowers) - Original Superpowers project
- [BryanHoo/superpowers-ccg](https://github.com/BryanHoo/superpowers-ccg) - CCG collaboration fork
- [fengshao1227/ccg-workflow](https://github.com/fengshao1227/ccg-workflow) - CCG workflow
- [Danau5tin/multi-agent-coding-system](https://github.com/Danau5tin/multi-agent-coding-system) - Smart context-sharing inspiration
- [GuDaStudio/geminimcp](https://github.com/GuDaStudio/geminimcp) - Gemini MCP
- [GuDaStudio/codexmcp](https://github.com/GuDaStudio/codexmcp) - Codex MCP
