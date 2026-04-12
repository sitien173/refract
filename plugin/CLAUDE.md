# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Global code style, error-handling rules, CP0–CP4 workflow details, required tools (`auggie`, `grok-search`, `codex`, `gemini`), RTK shell prefix, and Morph edit policy live in `rules/global-claude-workflow.mdc` (also applied when using the Cursor plugin rules pack).

## Common Commands

- Run skill tests: `./tests/claude-code/run-skill-tests.sh`
- Run integration tests: `./tests/claude-code/run-skill-tests.sh --integration`
- Run specific test: `./tests/claude-code/run-skill-tests.sh --test test-subagent-driven-development.sh`
- Update plugin: `claude plugin update superpowers-ccg`
- Install MCPs: `claude mcp add codex ...` and `claude mcp add gemini ...` (see README.md)

## High-Level Architecture

Superpowers-CCG enhances Claude Code with CCG multi-model orchestration: Claude plans phases, routes execution, reviews outputs, and runs integration checks. Codex is the default executor for most implementation. Gemini is reserved for UI-heavy phases.

Core workflow uses strict CP0 (Auggie context) → CP1 (phase routing) → CP2 (external execution) → CP3 (reconciliation if needed) → CP4 (phase review: `PASS`, `PASS_WITH_DEBT`, or `FAIL`) → integration checks after every phase.

Key areas:
- `skills/coordinating-multi-model-work/`: routing, checkpoints, CP protocol, external response format
- `skills/`: domain-specific skills (debugging-systematically, writing-plans, etc.)
- `tests/claude-code/`: bash-based skill behavior verification using headless `claude -p`

See README.md for full CCG details, model routing matrix, and differences from original superpowers. All changes must follow the checkpoint protocol in skills/coordinating-multi-model-work/SKILL.md.
