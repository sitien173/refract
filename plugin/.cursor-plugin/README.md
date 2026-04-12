# Superpowers-CCG Cursor Plugin

Skills-driven development with CCG multi-model orchestration: Claude orchestrates, Codex handles backend/systems, Gemini handles frontend.

## Installation

1. Open Cursor Settings → Plugins
2. Install this plugin from the local directory pointing to this repository

## Components

### Rules (Always Applied)

- **ccg-workflow.mdc** - CCG multi-model orchestration and checkpoint protocol
- **bounded-tasks.mdc** - One task, one owner, one artifact discipline
- **spec-review.mdc** - CP4 final spec review (spec satisfaction only)

### Skills (Auto-Triggered)

| Skill | Triggers |
|-------|----------|
| `coordinating-multi-model-work` | Implementation, debugging, refactoring, UI work, APIs |
| `brainstorming` | Creating features, building components, design work |
| `writing-plans` | Implementation planning, task breakdown |
| `executing-plans` | Plan execution, bounded task work |
| `debugging-systematically` | Bug fixing, error investigation |
| `verifying-before-completion` | Finishing tasks, completion checks |
| `developing-with-subagents` | Parallel execution, isolated experiments |
| `enhance-prompt` | Context enrichment before routing |
| `activating-ccg-in-cursor` | CCG setup, session initialization |

### Commands (Explicit Invocation)

| Command | Usage |
|---------|-------|
| `/superpowers-ccg:brainstorm` | Explore requirements and design |
| `/superpowers-ccg:write-plan` | Create implementation plan |
| `/superpowers-ccg:execute-plan` | Execute plan with checkpoints |
| `/superpowers-ccg:enhance-prompt` | Enrich prompt with context |

### Agents

| Agent | Purpose |
|-------|---------|
| `ccg-orchestrator` | CCG workflow planning and routing |
| `code-reviewer` | Post-implementation review |

### Hooks

- **sessionStart** - Activates CCG workflow reminder
- **afterFileEdit** - Reminds to run verify command

## Checkpoint Protocol

| Checkpoint | Purpose |
|------------|---------|
| CP0 | Context acquisition (Auggie + Grok Search) |
| CP1 | Task assessment and routing |
| CP2 | External execution (Codex/Gemini) |
| CP3 | Reconciliation (if needed) |
| CP4 | Final spec review |

## Model Routing

| Task Type | Route To |
|-----------|----------|
| Frontend / UI / Styling | Gemini |
| Backend / API / Logic | Codex |
| Scripts / CI/CD / Docker | Codex |
| Full-Stack / Architecture | Cross-Validation |
| Docs / Simple Fixes | Claude |

## MCP Setup

```bash
# Backend and systems specialist
claude mcp add codex -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/codexmcp.git codexmcp

# Frontend specialist
claude mcp add gemini -s user --transport stdio -- uvx --from git+https://github.com/GuDaStudio/geminimcp.git geminimcp
```

## More Information

See the main [README.md](../README.md) for full documentation.
