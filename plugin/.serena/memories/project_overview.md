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
| Tool | MCP | Purpose |
|------|-----|---------|
| Grok Search (Tavily) | `mcp__grok-search__web_search` | Web search, real-time info |
| Sequential-Thinking | `mcp__mcp-sequentialthinking-tools__sequentialthinking_tools` | Structured multi-step reasoning |
| Serena | `mcp__plugin_serena_serena__*` | Semantic code understanding, project memory |
| Magic | `mcp__magic__21st_magic_component_builder` | UI component generation |
| Morphllm | `mcp__morph-mcp__edit_file` | Bulk pattern-based editing |
