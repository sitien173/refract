# Multi-Model Integration (Shared Reference)

> Consuming-skill checklist for invoking external models. Canonical details: routing in `rules/ccg-workflow.mdc`, tier rules/budgets in `skills/coordinating-multi-model-work/context-sharing.md`, failure handling in `skills/coordinating-multi-model-work/GATE.md`.

**Related skill:** `superpowers-ccg:coordinating-multi-model-work`

## Integration Steps

1. Route using the routing matrix (`rules/ccg-workflow.mdc`). For detailed examples, see `routing-decision.md`.
2. Reduce scope to one phase with 2-4 related tasks, file set, reviewer checklist, and integration checks.
3. Choose the right prompt tier and send only hydrated snippets needed. Budgets are in `context-sharing.md`.
4. Invoke one primary worker: `mcp__codex__codex` (default) or `mcp__gemini__gemini` (UI/multimodal/large-context).
5. Reuse `SESSION_ID` for Tier 2 follow-ups or Tier 3 continuation per `SESSION_POLICY`.
6. Use `CROSS_VALIDATION` only for architecture conflict / multi-domain arbitration.
7. Run CP4 Phase Review → `PASS`, `PASS_WITH_DEBT`, or `FAIL`.
8. Run integration checks after every phase.

Workers edit files directly via MCP write tools and respond using ERP v1.1 (format in `shared/protocol-threshold.md`).

On MCP failure: `BLOCKED` per `GATE.md`. No retry/switch/fallback without human consent.
