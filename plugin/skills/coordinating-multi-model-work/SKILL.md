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

1. Run CP0: gather minimal context per `checkpoints.md` CP0 section. Mandatory stellaris `search_code` before CP1; `BLOCKED` on failure. Use `get_file_outline` / `get_file_folded` / `get_symbol` for token-efficient drill-down.
2. Reduce work to one implementation phase with 2-4 related tasks, file set, reviewer checklist, and integration checks.
3. Run CP1 and output the exact `# CP1 ROUTING DECISION` block.
4. If routing is not Claude, run CP2 with the 3-tier prompt system and External Response Protocol v1.1.
5. Workers edit files directly via MCP write tools and report `## FILES MODIFIED` without duplicating file content.
6. Parse `## FILES MODIFIED` from ERP and call `reindex_file` for each file (parallel, non-blocking on error). External workers bypass Claude's PostToolUse hooks.
7. Run CP3 only for cross-validation, failed/debt ERP output, clarifications, continuation requests, or overlapping worker edits.
8. Run integration checks, then CP4 Phase Review with `PASS`, `PASS_WITH_DEBT`, or `FAIL`.
9. Run CP4.5 Quality Review: spawn `cavecrew-reviewer` on `## FILES MODIFIED`, evaluate findings, output `# CP4.5 QUALITY REVIEW COMPLETE`. Can downgrade CP4 result based on severity.

## Hard Rules

- Codex is default for most implementation.
- Gemini is only for UI-heavy visual layout, styling, motion, canvas/SVG, or complex interactions.
- Claude handles planning, review, integration, docs, and clarification.
- Cross-validation is rare; use only for unresolved architecture or true multi-domain uncertainty.
- `HYDRATED_CONTEXT` ≤300 tokens hard cap. Budget details in `context-sharing.md`.
- MCP failure → `BLOCKED` per `GATE.md`. No retry/switch/fallback without human consent.
- Never accept prototype-only prose for implementation work.

## References

- `skills/coordinating-multi-model-work/checkpoints.md` — CP0-CP4 workflow and failure handling.
- `skills/coordinating-multi-model-work/context-sharing.md` — canonical tier budgets, `SESSION_POLICY`, and Tier 3 freshness.
- `skills/coordinating-multi-model-work/routing-decision.md` — CP1 routing framework.
- `skills/coordinating-multi-model-work/GATE.md` — fail-closed multi-model gate.
- `skills/coordinating-multi-model-work/INTEGRATION.md` — multi-model integration guide.
- `skills/coordinating-multi-model-work/cross-validation.md` — arbitration-only cross-validation pattern.
- `skills/coordinating-multi-model-work/review-chain.md` — CP4 review owner and outcomes.

