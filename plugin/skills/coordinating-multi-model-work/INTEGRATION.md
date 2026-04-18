# Multi-Model Integration Guide

> **Naming note.** "Integration" in this filename means **integrating multiple models** (Claude + Codex + Gemini) into one workflow. It is **not** the build/test "integration checks" gate that runs at CP3.5 — that lives in `checkpoints.md`.
>
> Tier rules, budgets, and `SESSION_POLICY` decisions are canonical in `context-sharing.md`. This file restates the workflow shape; if details diverge, `context-sharing.md` wins.

Claude is planner, orchestrator, reviewer, and integrator. Implementation normally goes through an executor, with Codex as the default route and Gemini reserved for UI-heavy phases.

## Standard Pattern

1. Define one implementation phase with 2-4 related tasks.
2. Turn CP0 findings into small reusable `CONTEXT_ARTIFACTS`.
3. Build one `PHASE_CONTEXT_BUNDLE` for the phase.
4. If routing is not `CLAUDE`, execute CP2 using the 3-tier prompt system:
   - Tier 1 initial call for a fresh session
   - Tier 2 same-phase follow-up for a bounded fix
   - Tier 3 cross-phase continuation when the same worker continues a related phase with `SESSION_POLICY: CONTINUE`
5. Workers edit files directly via MCP write tools and respond using External Response Protocol v1.1; the response lists `## FILES MODIFIED` but does not duplicate file content.
6. Reuse `SESSION_ID` for:
   - Tier 2 follow-up fixes on the same phase, with delta files and delta context only
   - Tier 3 cross-phase continuation when CP1 keeps the same worker on the same subsystem
7. Keep `HYDRATED_CONTEXT` under 300 tokens hard cap and avoid resending context the worker already has.
8. Do not exceed 2 Tier-2 follow-ups on the same phase. If the phase still fails, re-scope, ask the user, or restart with `SESSION_POLICY: FRESH`.
9. If CP1 chose `Cross-Validation`, or CP2 returned conflicts, overlap, gaps, clarifications, or continuation requests, run CP3 Reconciliation as Claude's decision layer.
10. Always run CP4 Phase Review after CP3, or directly after CP2/Claude-only work when no reconciliation is needed.
11. Run integration checks after each phase review.
12. `PASS` completes the phase. `PASS_WITH_DEBT` completes the phase with explicit non-blocking debt. `FAIL` requires a retry, follow-up, or user clarification.

## Hard Rules

- Do not ask for draft code that the orchestrator will later re-implement.
- Do not ask for design prose on an implementation task.
- Do not restate the whole PRD, plan, or prior conversation in every prompt.
- Do not repaste the full CP0 discovery output into every worker prompt.
- Do not send multiple workers the same implementation phase unless cross-validation is explicitly selected.
- Do not ask the worker to paste file content back into the response; the on-disk files written via MCP are the source of truth.
- Do not turn CP4 into a code-quality or best-practice review pass.

## Prompt Structure

Every implementation prompt should use one of these tiers:

```text
Tier 1: Task + Phase + Context + Files + Done When + full ERP v1.1
Tier 2: SESSION_ID + FIX + DELTA_FILES + DELTA_CONTEXT + "Respond using ERP v1.1"
Tier 3: SESSION_ID + SESSION_POLICY: CONTINUE + PHASE + New Phase + New/Changed Files + Delta Context + Done When + "Respond using ERP v1.1"
```

Keep `Done When` as the worker-facing checklist. Claude retains reviewer and integration checks for CP4.

## When To Cross-Validate

Use `CROSS_VALIDATION` only for design arbitration or unresolved multi-domain ambiguity. When you do:
- keep the file set and success criteria narrow
- compare only the meaningful divergences
- return one reconciled artifact in External Response Protocol v1.1, not two unrelated implementations

## CP4 Phase Review

Claude performs CP4 in the main thread using:
- the original user request
- the CP1 phase summary
- the CP1 success criteria
- the reviewer checklist
- the integration check results
- the files modified by the workflow

CP4 returns:
- `PASS` when the phase fully satisfies the checklist
- `PASS_WITH_DEBT` when the phase is usable and debt is explicit
- `FAIL` when a blocking requirement is not satisfied
