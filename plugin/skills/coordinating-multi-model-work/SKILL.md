---
name: coordinating-multi-model-work
description: "Routes implementation phases to Codex first, Gemini only for UI-heavy work, with Claude as planner, reviewer, and integrator. Use for implementation, debugging, refactoring, UI work, APIs, databases, scripts, CI/CD, security work, or cross-model arbitration."
---

# Coordinating Multi-Model Work

## Use When

- Work must be routed through CCG checkpoints.
- A phase needs Codex, Gemini, Claude-only handling, or rare cross-validation.
- User asks for implementation, debugging, refactoring, tests, CI/CD, infrastructure, UI-heavy work, or arbitration.

## Workflow

1. Run CP0: gather minimal context, use selective `docs/wiki/` lookup when useful, then Auggie for local code context; use Grok Search only for external/current research.
2. Reduce work to one implementation phase with 2-4 related tasks, file set, reviewer checklist, and integration checks.
3. Run CP1 and output the exact `# CP1 ROUTING DECISION` block.
4. If routing is not Claude, run CP2 with the 3-tier prompt system and External Response Protocol v1.1.
5. Workers edit files directly via MCP write tools and report `## FILES MODIFIED` without duplicating file content.
6. Run CP3 only for cross-validation, failed/debt ERP output, clarifications, continuation requests, or overlapping worker edits.
7. Run integration checks, then CP4 Phase Review with `PASS`, `PASS_WITH_DEBT`, or `FAIL`.

## Hard Rules

- Codex is default for most implementation.
- Gemini is only for UI-heavy visual layout, styling, motion, canvas/SVG, or complex interactions.
- Claude handles planning, review, integration, docs, and clarification.
- Cross-validation is rare; use only for unresolved architecture or true multi-domain uncertainty.
- Keep `HYDRATED_CONTEXT` under 300 tokens hard cap.
- If any Codex or Gemini MCP call fails with `timeout`, `tool-unavailable`, `session-failed`, session instability, model error, or `permission-blocked`, output `BLOCKED`; do not retry or switch executors.
- Never accept prototype-only prose for implementation work.

## References

- `skills/coordinating-multi-model-work/checkpoints.md` — CP0-CP4 workflow and failure handling.
- `skills/coordinating-multi-model-work/context-sharing.md` — canonical tier budgets, `SESSION_POLICY`, and Tier 3 freshness.
- `skills/coordinating-multi-model-work/routing-decision.md` — CP1 routing framework.
- `skills/coordinating-multi-model-work/GATE.md` — fail-closed multi-model gate.
- `skills/coordinating-multi-model-work/INTEGRATION.md` — multi-model integration guide.
- `skills/coordinating-multi-model-work/cross-validation.md` — arbitration-only cross-validation pattern.
- `skills/coordinating-multi-model-work/review-chain.md` — CP4 review owner and outcomes.
