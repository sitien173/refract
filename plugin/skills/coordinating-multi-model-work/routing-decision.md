# Routing Decision Framework

## Overview

This framework guides Claude in making semantic routing decisions for multi-model task distribution. Claude analyzes task characteristics using reasoning to determine the optimal execution model.

**Purpose**: Enable intelligent, context-aware routing decisions that adapt to task nuances.

## When to Use

Invoke this framework when a skill needs to call external models (Codex/Gemini/Cursor) via the MCP tools (`mcp__codex__codex`, `mcp__gemini__gemini`, `mcp__cursor__cursor`).

## Standard Information Set

Collect these inputs for decision-making:

1. **Task Description** - User's request in natural language
2. **File Information** - File paths and extensions involved
3. **Tech Stack** - Inferred from project files

## Analysis Dimensions

### 1. Task Essence

What problem is this task primarily solving?

**Consider:**
- Core objective: Fix bug, add feature, optimize performance, refactor code
- Domain focus: Data processing, user interface, business logic, infrastructure
- Primary skill required: Design thinking, algorithmic problem-solving, UI/UX implementation

### 2. Technical Domain

Does this task lean toward frontend (UI/interaction) or backend (logic/data)?

**Frontend Indicators:**
- UI components, layouts, visual design
- User interactions, event handling
- Styling, animations, responsive design
- Client-side state management
- Browser APIs, DOM manipulation

**Backend Indicators:**
- API endpoints, server logic
- Database operations, data models, ORM
- Algorithms, performance optimization
- Authentication, authorization, security
- Background jobs, message queues

### 3. Complexity & Uncertainty

Does this task involve multiple domains or uncertain factors?

**High Complexity Indicators:**
- Spans frontend and backend simultaneously
- Multiple possible root causes (debugging scenarios)
- Architectural design decisions affecting both layers
- Critical changes affecting core functionality
- Insufficient information to determine domain

**Low Complexity Indicators:**
- Single file change in a clear domain
- Well-defined scope
- Isolated component or function

## Decision Output

Based on the analysis, output:

```
**Routing Decision:** [CODEX | GEMINI | CURSOR | CROSS_VALIDATION | CLAUDE]
**Rationale:** [One sentence]
```

**Early exposure note:** If `Routing != CLAUDE`, apply `coordinating-multi-model-work/GATE.md` immediately (evidence or BLOCKED) before doing real work.

### Routing Targets

- **CODEX** - Backend expert for APIs, databases, algorithms, server-side logic
- **GEMINI** - Frontend expert for UI, components, styles, interactions
- **CURSOR** - DevOps agent for CI/CD, shell scripts, Dockerfiles, Makefiles, infrastructure, and repo tooling
- **CROSS_VALIDATION** - Multiple models for full-stack tasks, architectural decisions, or high uncertainty (default: Codex+Gemini; escalate to 3-way with Cursor for critical/high-uncertainty tasks)
- **CLAUDE** - Orchestrator only: routing decisions, coordination, documentation edits. **Claude does NOT write implementation code** — all coding tasks must route to CODEX, GEMINI, or CURSOR

> **Important:** Claude's role is pure orchestration. If a task requires code changes, it MUST be routed to an external model. If all external models are unavailable, the task is BLOCKED by design.

## Quality Gate Decision (Orthogonal to Routing)

In addition to domain routing, CP3 evaluates whether code quality review is needed:

```
**QualityGateRequired:** [Yes | No]
**Rationale:** [Code changed / docs-only]
```

See `coordinating-multi-model-work/review-chain.md` for the review chain rule and `checkpoints.md` for the QualityGateRequired decision table.

## Decision Guidelines

- Strong backend signals and weak/no frontend signals → **CODEX**
- Strong frontend signals and weak/no backend signals → **GEMINI**
- DevOps, CI/CD, shell scripts, Dockerfiles, Makefiles, infrastructure → **CURSOR**
- Strong signals in both domains OR high uncertainty OR architectural → **CROSS_VALIDATION**
- Debugging or refactoring with unclear domain → **CROSS_VALIDATION**
- Documentation-only OR pure coordination (no code changes) → **CLAUDE**
- Ambiguous case between domains → **CROSS_VALIDATION**

**Key Principle**: Claude never writes code. When in doubt between CODEX/GEMINI/CURSOR, prefer CROSS_VALIDATION. When in doubt between CLAUDE and others, route externally.

## File Extension Heuristics

Quick hints (use semantic analysis for final decision):

| File Pattern | Default Routing |
|-------------|----------------|
| `**/*.go`, `**/*.py`, `**/*.sql` | CODEX |
| `**/*.tsx`, `**/*.css`, `**/*.html` | GEMINI |
| `**/*.sh`, `**/*.yml`, `Dockerfile`, `Makefile`, `**/*.tf` | CURSOR |
| Mixed frontend + backend | CROSS_VALIDATION |
| `**/*.md` (docs only, no code) | CLAUDE |
| Design docs, architecture docs, requirements specs | CROSS_VALIDATION |

## Supplementary Tools (Orchestrator-Level)

In addition to primary routing, Claude may use supplementary MCP tools to enhance analysis. These are optional and do not affect routing decisions. See `skills/shared/supplementary-tools.md`.

| Supplementary Tool | When to Use Alongside Routing |
|-------------------|-------------------------------|
| Tavily | Research phase: unfamiliar tech, current info needed |
| Sequential-Thinking | Complex tasks: 3+ components, architectural decisions |
| Serena | Large codebases: symbol tracing, dependency analysis |
| Magic | Frontend routing: complements Gemini with component patterns |
| Morphllm | Bulk edits: pattern-driven multi-file changes |

## Review Chain

See `coordinating-multi-model-work/review-chain.md` for the canonical review chain rule.

## Examples

### Example 1: Frontend Task

**Input:** "Add a dark mode toggle to the settings page"
**Files:** `src/components/Settings.tsx`, `src/styles/theme.css`

**Output:**
```
**Routing Decision:** GEMINI
**Rationale:** UI component and styling task with clear frontend domain signals
```

---

### Example 2: Backend Task

**Input:** "Optimize database query performance for user search"
**Files:** `server/api/users.go`, `server/db/queries.sql`

**Output:**
```
**Routing Decision:** CODEX
**Rationale:** Database query optimization with clear backend domain signals
```

---

### Example 3: Full-Stack Task

**Input:** "Implement real-time notification system"
**Files:** `server/websocket/hub.go`, `src/components/NotificationBell.tsx`

**Output:**
```
**Routing Decision:** CROSS_VALIDATION
**Rationale:** Spans backend WebSocket implementation and frontend UI component
```

---

### Example 4: DevOps Task

**Input:** "Fix the flaky test in CI pipeline"
**Files:** `tests/integration/test_pipeline.sh`, `.github/workflows/ci.yml`

**Output:**
```
**Routing Decision:** CURSOR
**Rationale:** CI/CD pipeline task — DevOps domain
```

---

### Example 5: Uncertain Debugging (Multi-Domain)

**Input:** "Fix the authentication bug - users can't log in"
**Files:** Unknown (need investigation)

**Output:**
```
**Routing Decision:** CROSS_VALIDATION
**Rationale:** Authentication bug with unclear root cause requires multi-perspective diagnosis
```

---

### Example 6: Refactoring Task

**Input:** "Refactor the logging utility to use structured logging"
**Files:** `lib/logger.js`, `lib/utils.js`

**Output:**
```
**Routing Decision:** CROSS_VALIDATION
**Rationale:** General refactoring with unclear domain — cross-validate for best approach
```
