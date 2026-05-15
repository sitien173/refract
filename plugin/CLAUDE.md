# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Global orchestration rules, routing matrix, tiebreakers, and failure handling live in `rules/ccg-workflow.mdc` (always loaded). Phase discipline in `rules/bounded-tasks.mdc`. CP4 review scope in `rules/spec-review.mdc`.

## Common Commands

- Run skill tests: `./tests/claude-code/run-skill-tests.sh`
- Run integration tests: `./tests/claude-code/run-skill-tests.sh --integration`
- Run specific test: `./tests/claude-code/run-skill-tests.sh --test test-executing-plans.sh`
- Update plugin: `claude plugin update superpowers-ccg`
- Install MCPs: `claude mcp add codex ...` and `claude mcp add gemini ...` (see README.md)

## High-Level Architecture

Superpowers-CCG enhances Claude Code with CCG multi-model orchestration: Claude plans phases, routes execution, reviews outputs, and runs integration checks. Codex is the default executor for most implementation. Gemini handles UI, multimodal, and large-context visual/document phases.

Core workflow uses strict CP0 (stellaris context) → CP1 (phase routing) → CP2 (external execution) → CP3 (reconciliation if needed) → CP4 (phase review: `PASS`, `PASS_WITH_DEBT`, or `FAIL`) → integration checks after every phase.

Key areas:
- `skills/coordinating-multi-model-work/`: routing, checkpoints, CP protocol, external response format
- `skills/`: domain-specific skills (debugging-systematically, writing-plans, etc.)
- `tests/claude-code/`: bash-based skill behavior verification using headless `claude -p`

See README.md for full CCG details, model routing matrix, and differences from original superpowers. All changes must follow the checkpoint protocol in skills/coordinating-multi-model-work/SKILL.md.

## Routing

Routing matrix, tiebreakers, and new routing axes are in `rules/ccg-workflow.mdc` (always loaded). Detailed matrix with examples and session policy in `skills/coordinating-multi-model-work/routing-decision.md`.
