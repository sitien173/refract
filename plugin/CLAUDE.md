# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

- Run skill tests: `./tests/claude-code/run-skill-tests.sh`
- Run integration tests: `./tests/claude-code/run-skill-tests.sh --integration`
- Run specific test: `./tests/claude-code/run-skill-tests.sh --test test-subagent-driven-development.sh`
- Update plugin: `claude plugin update superpowers-ccg`
- Install MCPs: `claude mcp add codex ...` and `claude mcp add gemini ...` (see README.md)

## High-Level Architecture

Superpowers-CCG enhances Claude Code with CCG multi-model orchestration (Claude as pure orchestrator routing bounded tasks to Codex for backend/systems and Gemini for frontend via MCP tools). 

Core workflow uses strict CP0 (Auggie context) → CP1 (routing matrix) → CP2 (external execution) → CP3 (reconciliation if needed) → CP4 (spec-only review).

Key areas:
- `skills/coordinating-multi-model-work/`: routing, checkpoints, CP protocol, external response format
- `skills/`: domain-specific skills (debugging-systematically, writing-plans, etc.)
- `tests/claude-code/`: bash-based skill behavior verification using headless `claude -p`

See README.md for full CCG details, model routing matrix, and differences from original superpowers. All changes must follow the checkpoint protocol in skills/coordinating-multi-model-work/SKILL.md.
