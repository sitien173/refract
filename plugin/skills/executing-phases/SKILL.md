---
name: executing-phases
description: "Executes one active implementation phase in the current session by routing to Codex or Gemini, then running Claude review and integration gates. Use when: executing-phases, phase execution, run this phase, continue current phase."
---

# Executing Phases

## Overview

Execute one implementation phase at a time with Codex or Gemini as the primary executor.

Claude stays in the orchestrator, reviewer, and integrator roles. The executor role goes to Codex by default, or Gemini when the phase is UI-heavy.

## Phase Execution Flow

1. **Planner** - Use the written plan phases. Each phase should contain 2-4 related tasks.
2. **Executor** - Route the active phase to Codex or Gemini.
3. **Reviewer** - Claude reviews the output against the phase checklist and returns `PASS`, `PASS_WITH_DEBT`, or `FAIL`.
4. **Integrator** - Run integration checks after every phase.
5. **Final Summary** - Summarize only after all phases complete.

## Routing Rules

- Codex first for most implementation: backend, full-stack, tests, refactors, debugging, infrastructure, scripts, and repo tooling.
- Gemini only when the phase is UI-heavy: visual design, component layout, styling, motion, canvas/SVG, or complex interactions dominate the work.
- Claude handles orchestration, review, integration checks, docs, and clarification. Claude may implement only when the plan explicitly routes to `claude` or the user overrides routing.
- Cross-validation is rare and only for unresolved architecture or true multi-domain conflict.
- If any Codex or Gemini MCP call fails, output `BLOCKED`; do not retry or switch executors.

## Phase Handoff Format

Provide each executor with:

```markdown
## Phase
[Phase N and short outcome]

## Goal
[One clear phase goal]

## Files
- Modify: `path/to/file`
- Create: `path/to/new/file`

## Tasks
1. [related task]
2. [related task]
3. [optional related task]
4. [optional related task]

## Acceptance Criteria
- [Testable criterion 1]
- [Testable criterion 2]

## Reviewer Checklist
- [spec requirement]
- [regression risk]
- [verification expectation]

## Integration Checks
- `exact command`
```

## Orchestration Rules

1. Execute one phase at a time.
2. Keep the controller thread small: no full-plan restatement for every worker call.
3. Send only phase-scoped context, relevant refs, changed snippets, and verification commands.
4. Reuse the same worker `SESSION_ID` only for fixes on the same phase.
5. Workers edit files directly via MCP write tools and respond with the changed-file list (no duplicated content); never accept prototype-only prose.
6. Move to the next phase only after review and integration return `PASS` or `PASS_WITH_DEBT`.

## Reviewer Gate

Claude reviews the phase output and returns:

- `PASS` - phase satisfies the checklist and integration can continue.
- `PASS_WITH_DEBT` - phase is usable, debt is explicit, and integration can continue.
- `FAIL` - blocking gap; route one bounded fix before integration.

## Integrator Gate

After each phase:

- Run the phase integration checks.
- Confirm the repo is still coherent at the required build/test level.
- Record changed files, worker used, review status, integration result, and debt.
- Do not produce the project final summary until the final integration checks pass.
