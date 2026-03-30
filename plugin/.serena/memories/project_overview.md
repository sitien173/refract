# Project Overview: superpowers-ccg

## Purpose
Claude Code plugin that adds a skills-driven development workflow with multi-model orchestration (Claude + Codex + Cursor + Gemini). Claude acts as pure orchestrator — all implementation code is routed to external models via MCP tools.

Fork of [obra/superpowers](https://github.com/obra/superpowers).

## Tech Stack
- **Not a compiled application** — no `package.json`, `Makefile`, or build step
- Markdown files (`.md`) — skill definitions and documentation
- Bash scripts (`.sh`) — hooks and test runner
- Node.js (`lib/skills-core.js`) — skill discovery/resolution
- Windows environment (but uses bash/unix shell syntax via Git Bash)

## Directory Structure
```
.claude-plugin/     plugin metadata (plugin.json, marketplace.json)
agents/             agent definitions
bin/                CLI utilities
commands/           quick-invoke commands (/brainstorm, /write-plan, /execute-plan)
docs/               documentation
hooks/              runtime behavior hooks (hooks.json, *.sh, run-hook.cmd)
lib/                skills-core.js — skill discovery and resolution
skills/             all skill subdirectories, each with SKILL.md
tests/              test suites (claude-code, explicit-skill-requests, etc.)
superpowers-ccg.md  authoritative agent rules document
CLAUDE.md           Claude Code project instructions
```

## Primary Routing (Implementation)
| Label | When | MCP Tool |
|-------|------|----------|
| CODEX | Backend: API, DB, algorithms | `mcp__codex__codex` |
| GEMINI | Frontend: UI, components, styles | `mcp__gemini__gemini` |
| CURSOR | DevOps: CI/CD, scripts, Dockerfiles, infrastructure | `mcp__cursor__cursor` |
| CLAUDE | Orchestration only (NO code) | none |

## Review Chain
Opus reviews all code-changing paths directly. No intermediate review assistant step.

## Supplementary Tools (Optional Enhancements)
| Tool | Purpose |
|------|---------|
| Tavily | Web search, real-time info (research, error search) |
| Sequential-Thinking | Structured multi-step reasoning (complex analysis) |
| Serena | Semantic code understanding (symbol tracing, project memory) |
| Magic | UI component generation (complements Gemini) |
| Morphllm | Bulk pattern-based editing (multi-file transformations) |

These enhance Claude's orchestration but are NOT required — workflows work without them.
