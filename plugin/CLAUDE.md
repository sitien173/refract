# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**Superpowers-CCCG** is a Claude Code plugin that adds a skills-driven development workflow with multi-model orchestration (Claude + Codex + Cursor + Gemini). Claude acts as pure orchestrator — all implementation code is routed to external models. It is a fork of [obra/superpowers](https://github.com/obra/superpowers).

This is not a compiled application — it is a **plugin/skills framework** written as Markdown files, Bash scripts, and a small Node.js utility. There is no `package.json`, `Makefile`, or build step.

The authoritative agent rules for working in this repository are in `superpowers-ccg.md`.

## Running Tests

```bash
# Run all fast tests (recommended)
./tests/claude-code/run-skill-tests.sh

# Run integration tests (slow, 10–30 minutes)
./tests/claude-code/run-skill-tests.sh --integration

# Run a single test file
./tests/claude-code/run-skill-tests.sh --test <test-file>.sh

# With verbose output
./tests/claude-code/run-skill-tests.sh --verbose

# Custom timeout (seconds)
./tests/claude-code/run-skill-tests.sh --timeout 1800
```

Test helpers (`tests/claude-code/test-helpers.sh`) expose: `run_claude`, `assert_contains`, `assert_not_contains`, `assert_count`, `assert_order`.

## Architecture

### Skills (`skills/`)

Each skill lives in a subdirectory with `SKILL.md` (YAML frontmatter + instructions). Skills are discovered and resolved via `lib/skills-core.js`. All skills are exposed under the `superpowers-cccg:` namespace.

Key skills:
- `coordinating-multi-model-work/` — Routes tasks to Codex/Gemini/Cursor MCP; defines the CP checkpoint protocol. Claude is orchestrator-only.
- `developing-with-subagents/` — Routes tasks to external models with spec review via Opus, then Opus quality review on every code-changing path
- `executing-plans/` — Batch plan execution with review checkpoints

### Hooks (`hooks/`)

Three hooks regulate Claude behavior at runtime:

| Hook | Trigger | Purpose |
|------|---------|---------|
| `session-start.sh` | startup/resume/clear | Session initialization |
| `user-prompt-submit.sh` | every user message | Inject CP1/CP3 checkpoint reminders |
| `pre-tool-use-task.sh` | before Task tool | Remind about model selection (sonnet/haiku) |

Hook registration is in `hooks/hooks.json`.

### Multi-Model Routing

Claude is the **orchestrator** — it routes tasks, coordinates models, and integrates results but **never writes implementation code**.

| Routing | When | MCP Tool |
|---------|------|----------|
| `CODEX` | Backend: API, DB, auth, algorithms | `mcp__codex__codex` |
| `GEMINI` | Frontend: UI, components, styles | `mcp__gemini__gemini` |
| `CURSOR` | DevOps: CI/CD, scripts, Dockerfiles, infrastructure | `mcp__cursor__cursor` |
| `CROSS_VALIDATION` | Full-stack, architectural, uncertain | Multiple |
| `CLAUDE` | Orchestration only: docs, coordination (NO code) | None |

Cursor is the **DevOps implementation agent** (CI/CD, scripts, Dockerfiles, infrastructure) using `claude-4.6-sonnet-medium-thinking`. Opus reviews all code-changing paths directly — there is no intermediate review assistant step.

**Fail-closed rule**: If `Routing != CLAUDE` and the MCP call cannot complete, output `BLOCKED` — never guess or produce a final answer without evidence. If all external models are unavailable, all coding tasks are BLOCKED by design. See `GATE.md` for tiered failure policy.

### Supplementary Tools (Optional)

Claude may use these MCP tools to enhance orchestration — they are optional enhancements, not requirements. See `skills/shared/supplementary-tools.md`.

- **Grok Search** (Tavily-powered) — real-time web search (research, error search)
- **Sequential-Thinking** — structured reasoning for complex analysis
- **Serena** — semantic code understanding (symbol tracing, project memory)
- **Magic** — UI component generation (complements Gemini)
- **Morphllm** — bulk pattern-based code editing

### Checkpoint (CP) Protocol

- **CP1**: Before first Task call — assess routing, invoke external model if needed
- **CP2**: Mid-execution — triggered by uncertainty, stalled debugging, 2+ failed attempts
- **CP3**: Before claiming completion — run verification, record evidence

### Plugin Metadata (`.claude-plugin/`)

- `plugin.json` — name, version, description (current: 1.1.3)
- `marketplace.json` — marketplace registration

### Commands (`commands/`)

Quick-invoke workflows: `/brainstorm`, `/write-plan`, `/execute-plan`. These map directly to their corresponding skills.

## Skill Authoring

When creating or editing skills, use `superpowers-cccg:writing-skills`. Skills require a failing test before implementation (same TDD discipline as code).

Skill file structure:
```
skills/<skill-name>/
  SKILL.md        # frontmatter (name, description) + instructions
  [supporting files, e.g. routing-decision.md, GATE.md]
```
