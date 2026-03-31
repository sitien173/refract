# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## What This Project Is

**Superpowers-CCG** is a Claude Code plugin that adds a skills-driven development workflow with multi-model orchestration (Claude + Codex + Gemini). Claude acts as pure orchestrator and routes all implementation code to external models. It is a fork of [obra/superpowers](https://github.com/obra/superpowers).

This repository is a **plugin/skills framework** written mostly as Markdown and Bash, with a small Node.js utility. There is no build step.

The authoritative agent rules are in `superpowers-ccg.md`.

## Running Tests

```bash
./tests/claude-code/run-skill-tests.sh
./tests/claude-code/run-skill-tests.sh --integration
./tests/claude-code/run-skill-tests.sh --test <test-file>.sh
./tests/claude-code/run-skill-tests.sh --verbose
./tests/claude-code/run-skill-tests.sh --timeout 1800
```

## Architecture

### Skills (`skills/`)

Each skill lives in a subdirectory with `SKILL.md` (YAML frontmatter + instructions). Skills are discovered and resolved via `lib/skills-core.js`. All skills are exposed under the `superpowers-ccg:` namespace.

Key skills:
- `coordinating-multi-model-work/` — Routes tasks to Codex/Gemini MCP and defines the CP checkpoint protocol
- `developing-with-subagents/` — Routes tasks to external models with spec review via Opus, then Opus quality review
- `executing-plans/` — Batch plan execution with review checkpoints

### Hooks (`hooks/`)

Three hooks regulate Claude behavior at runtime:

| Hook | Trigger | Purpose |
|------|---------|---------|
| `session-start.sh` | startup/resume/clear | Session initialization |
| `user-prompt-submit.sh` | every user message | Inject CP1/CP3 checkpoint reminders |
| `pre-tool-use-task.sh` | before Task tool | Remind about model selection |

### Multi-Model Routing

Claude is the **orchestrator**. It routes tasks, coordinates models, and integrates results, but **never writes implementation code**.

| Routing | When | MCP Tool |
|---------|------|----------|
| `CODEX` | Backend and systems: API, DB, auth, scripts, CI/CD, Dockerfiles, infrastructure | `mcp__codex__codex` |
| `GEMINI` | Frontend: UI, components, styles | `mcp__gemini__gemini` |
| `CROSS_VALIDATION` | Full-stack, architectural, uncertain | Multiple |
| `CLAUDE` | Orchestration only: docs, coordination (no code) | None |

Opus reviews all code-changing paths directly.

### Shared Context Layer (Serena HTTP)

All agents (Claude, Codex, Gemini) connect to a single Serena instance via Streamable HTTP (port 9121). This provides shared project memories and the `global/response_protocol` memory for token-efficient agent output.

### Supplementary Tools

Supplementary MCP tools can enhance orchestration, but they are optional. See `skills/shared/supplementary-tools.md`.

### Checkpoint Protocol

- **CP1**: Before first Task call
- **CP2**: Mid-execution when uncertainty or stalls appear
- **CP3**: Before claiming completion

### Plugin Metadata (`.claude-plugin/`)

- `plugin.json` — name, version, description
- `marketplace.json` — marketplace registration

## Skill Authoring

When creating or editing skills, use `superpowers-ccg:writing-skills`. Skills require a failing test before implementation.
