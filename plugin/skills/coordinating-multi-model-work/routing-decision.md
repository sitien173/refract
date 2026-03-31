# Routing Decision Framework

## Overview

This framework guides Claude in making semantic routing decisions for multi-model task distribution.

## When to Use

Invoke this framework when a skill needs to call external models (Codex/Gemini) via the MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`).

## Decision Output

```text
**Routing Decision:** [CODEX | GEMINI | CROSS_VALIDATION | CLAUDE]
**Rationale:** [One sentence]
```

## Routing Targets

- **CODEX** - Backend and systems expert for APIs, databases, algorithms, server-side logic, CI/CD, scripts, Dockerfiles, infrastructure, and repo tooling
- **GEMINI** - Frontend expert for UI, components, styles, interactions
- **CROSS_VALIDATION** - Multiple models for full-stack tasks, architectural decisions, or high uncertainty (Codex + Gemini)
- **CLAUDE** - Orchestrator only: routing decisions, coordination, documentation edits

## Decision Guidelines

- Strong backend or systems signals and weak/no frontend signals → **CODEX**
- Strong frontend signals and weak/no backend signals → **GEMINI**
- Strong signals in both domains or high uncertainty → **CROSS_VALIDATION**
- Documentation-only or pure coordination → **CLAUDE**

## File Extension Heuristics

| File Pattern | Default Routing |
|-------------|----------------|
| `**/*.go`, `**/*.py`, `**/*.sql` | CODEX |
| `**/*.sh`, `**/*.yml`, `Dockerfile`, `Makefile`, `**/*.tf` | CODEX |
| `**/*.tsx`, `**/*.css`, `**/*.html` | GEMINI |
| Mixed frontend + backend | CROSS_VALIDATION |
| `**/*.md` (docs only, no code) | CLAUDE |

## Example

**Input:** "Fix the flaky test in CI pipeline"

**Output:**
```text
**Routing Decision:** CODEX
**Rationale:** CI/CD pipeline task with clear systems and automation signals
```
