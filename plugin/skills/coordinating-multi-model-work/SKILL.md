---
name: coordinating-multi-model-work
description: "Routes implementation phases to Codex first, Gemini only for UI-heavy work, with Claude as planner, reviewer, and integrator. Use when: implementation, debugging, refactoring, UI work, APIs, databases, scripts, CI/CD, or cross-model arbitration."
---

# Coordinating Multi-Model Work

> Tier-prompt rules, budgets, `SESSION_POLICY` decisions, and the Tier 3 freshness check are canonical in `context-sharing.md`. Other sections in this skill restate parts for in-place legibility; on conflict, `context-sharing.md` wins.

## Overview

Claude is the orchestrator, reviewer, and integrator. It plans phases, routes execution, reviews output, and runs integration checks.

Use this module to route one implementation phase at a time:
- **Codex** — default executor for most implementation
- **Gemini** — UI-heavy executor only
- **Claude** — planner, reviewer, integrator, docs, clarification, or explicit Claude-code fallback

## Core Rules

1. Reduce the current work to one implementation phase with 2-4 related tasks, a clear file set, reviewer checklist, and integration checks.
2. Route that phase to exactly one primary worker unless there is real architectural uncertainty.
3. Turn CP0 findings into reusable context artifacts, then build the right executor prompt tier for that phase.
4. Reuse the same worker `SESSION_ID` for Tier 2 follow-up fixes on that phase, or Tier 3 cross-phase continuation when CP1 keeps the same worker on a related subsystem. Send deltas only.
5. Ask for the actual final artifact using External Response Protocol v1.1. Workers edit files directly via MCP write tools; the response reports changes in `## FILES MODIFIED` without duplicating file content. Never accept prototypes or design prose.
6. Use CP3 as a Claude-only reconciliation layer when cross-validation or other non-trivial external feedback appears.
7. Always run Claude review after executor output and integration checks after every phase.
8. Review returns `PASS`, `PASS_WITH_DEBT`, or `FAIL`.
9. If a Gemini MCP call fails once with `timeout`, `tool-unavailable`, or session/tool instability, fall back to Codex or Claude-code. Do not spend multiple retries on Gemini.
10. If a Codex MCP call fails with `timeout` or `tool-unavailable`, retry once, then fall back to Claude-code. See `checkpoints.md` CP2 Failure & Fallback for the full policy.

## Cross-Validation

`CROSS_VALIDATION` is rare. Use it only when:
- the task genuinely spans frontend and backend at the same time, or
- two viable designs remain after scope reduction, or
- the failure mode is still ambiguous after one worker pass.

Do not use cross-validation as the default for ordinary implementation work.

## Checkpoint Workflow

Before CP1, do CP0 context acquisition with:
- Auggie for full local codebase context retrieval
- Grok Search only for external/current knowledge or research
- Normalize CP0 findings into reusable context artifacts before routing

At CP1, perform Phase Assessment & Routing using the original request and the CP0 context artifacts, decide `SESSION_POLICY`, then build the right executor prompt tier and emit the exact `# CP1 ROUTING DECISION` block.

| Task Category | Model | Cross-Validation | Notes / Triggers |
| --- | --- | --- | --- |
| UI-heavy visual implementation | Gemini | No | Use only when visual layout, styling, motion, canvas/SVG, or interactions dominate |
| Backend / Logic / API | Codex | No | Default implementation route |
| Full-Stack / Architecture | Codex | No | Use cross-validation only for unresolved architecture conflict |
| Docs / Comments / Coordination | Claude | No | No external executor needed |
| Debugging / Performance | Codex | No | Escalate to cross-validation only if the failure mode stays ambiguous |
| Infrastructure / DevOps | Codex | No | Use cross-validation only for high-risk changes |
| Data / ML / Analytics | Codex | No | Use cross-validation only if the task becomes unusually complex |
| Testing / Test Coverage | Codex | No | Gemini only if the tests are mainly visual/UI behavior |
| Cross-Cutting / Security | Codex | No | Add human/Claude review instead of default cross-validation |
| Uncategorized / Ambiguous | Claude | No | Fail-closed: ask clarifying questions immediately |

At CP2, if routing is not `Claude`, use the 3-tier system: Tier 1 for a fresh session, Tier 2 for same-phase follow-up fixes, and Tier 3 for cross-phase continuation with `SESSION_POLICY: CONTINUE`. Keep `HYDRATED_CONTEXT` under 300 tokens hard cap. Do not exceed 2 Tier-2 follow-ups on the same phase. Require External Response Protocol v1.1; workers edit files directly via MCP write tools, so responses list `## FILES MODIFIED` without duplicating file content.

At CP3, parse every external response block, resolve conflicts or clarifications, and decide whether the task is ready for CP4, needs a retry, or needs user input.

At CP4, use the original user request, the CP1 phase summary, the CP1 success criteria, the reviewer checklist, integration results, and modified files to decide `PASS`, `PASS_WITH_DEBT`, or `FAIL`. Do not perform broad style review unless style is part of the phase checklist.

## Response Protocol

All external model prompts must inline External Response Protocol v1.1 directly. Do not rely on external memory indirection.

## Reference Files

- `coordinating-multi-model-work/checkpoints.md`
- `coordinating-multi-model-work/context-sharing.md`
- `coordinating-multi-model-work/routing-decision.md`
- `coordinating-multi-model-work/GATE.md`
- `coordinating-multi-model-work/INTEGRATION.md`
- `coordinating-multi-model-work/review-chain.md`
- `coordinating-multi-model-work/cross-validation.md`
