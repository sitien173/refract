# Collaboration Checkpoints

## Contents

- Overview
- CP0: Context Acquisition
- CP1: Phase Assessment & Routing
- CP2: External Execution
- CP2 Failure Handling
- CP3: Reconciliation
- CP3.5: Integration Checks
- CP4: Phase Review
- User Override

## Overview

Checkpoints exist to control routing and keep the orchestrator thread small.

The active unit of work is an **execution phase**. A good execution phase contains 2-4 related tasks, one primary executor, one Claude review, and one integration gate.

### Glossary — "phase" disambiguation

The word "phase" appears in three distinct senses; do not conflate them:

| Term | Meaning |
| --- | --- |
| **Plan phase** | A numbered section in `docs/plans/*.md` produced by `writing-plans`. Coarse — may span several execution phases. |
| **Execution phase** | The CP1 unit of work (2-4 tasks, one executor, one review, one integration gate). What CP1–CP4 operate on. |
| **`## Phase` field** | The metadata header inside a Tier 1 worker prompt; carries `TASK_ID` and `SESSION_POLICY` only. |

## CP0: Context Acquisition

- Gather only the minimum context needed to route the next phase.
- Decide whether `docs/wiki/` durable knowledge is useful before local code retrieval.
- Selectively consult `docs/wiki/` for complex planning, architecture, debugging, refactors with prior decisions, or prompts asking what the project knows, decided, or tried.
- Skip wiki lookup for trivial edits, simple version bumps, formatting, and tasks answerable from current files.
- MUST run context-retrieval via `codebase-retrieval` for local semantic anchors, unfamiliar subsystems, architecture relationships, exact references, and stale wording checks before CP1 on every task (including trivial/current-file tasks). Optionally run `stellaris search_code` in parallel for code-specific symbol-level precision (AST-aware, voyage-code-3 embeddings, RRF fusion).
- If `codebase-retrieval` errors, is unavailable, permission-blocked, or returns tool failure, immediately output `BLOCKED` and stop before CP1. Stellaris failure does NOT trigger `BLOCKED`.
- Do not switch to file tools, Grok Search, or executors when `codebase-retrieval` fails.
- Use Grok Search only when the task needs external/current knowledge or research, and only after mandatory local retrieval succeeds.
- Merge useful output from both retrieval sources into small reusable `CONTEXT_ARTIFACTS`.
- Treat wiki content as advisory and citation-backed; current files, tests, and current user request override it.
- End CP0 as soon as the phase and likely owner are clear enough for CP1.

CP0 tool matrix:

| Need | Primary Tool | Secondary Tool | When to Trigger Grok Search | Fallback |
| --- | --- | --- | --- | --- |
| Durable project knowledge / prior decisions | `docs/wiki/` selective lookup | — | Do not trigger Grok Search for project-local wiki lookup | Skip when uninitialized or irrelevant |
| Local codebase context / references / architecture relationships | `codebase-retrieval` (mandatory before CP1) | `stellaris search_code` (optional, parallel) | Do not trigger Grok Search during mandatory local-context retrieval | `BLOCKED` for codebase-retrieval failure only; stellaris failure is non-blocking |
| Symbol-level code precision / AST-aware structure | `stellaris search_code` + `get_file_outline` / `get_symbol` | — | Do not trigger Grok Search for local symbol lookup | Skip if stellaris unavailable |
| External / real-world knowledge | Grok Search | — | When the task mentions "latest", "current", "best practice", an unknown library, or a raw error that needs external research | None |

## CP1: Phase Assessment & Routing

- Run immediately after CP0 completes.
- Read the original user request and the CP0 context artifacts.
- Summarize the active phase in one English sentence.
- Check whether the phase is clear, sufficiently scoped, and contains 2-4 related tasks.
- If not clear, route to `Claude`, output the CP1 routing block, and ask clarifying questions immediately.
- Classify the task using the routing matrix in `rules/ccg-workflow.mdc`. For detailed examples, see `routing-decision.md`.
- Decide model ownership, cross-validation, and `SESSION_POLICY` (see `context-sharing.md` for the decision table).
- Build one `PHASE_CONTEXT_BUNDLE` with `TASK_ID` and `HYDRATED_CONTEXT`.
- Output the exact `# CP1 ROUTING DECISION` block before the first executor call.

## CP2: External Execution

Run CP2 only when CP1 routes the phase to `Gemini`, `Codex`, or `Cross-Validation`.

Goal:
- The external model performs the actual work.
- The external model returns the final code/files directly.

CP2 uses the 3-tier prompt system. Tier templates, budgets, `SESSION_POLICY` decision table, and retry rules are canonical in `context-sharing.md`. ERP v1.1 format is in `shared/protocol-threshold.md`.

Output contract:
- Workers edit files directly via MCP write tools. The on-disk files are the source of truth.
- The response uses ERP v1.1 and lists every changed file in `## FILES MODIFIED`, but does not duplicate file content.
- Optional `## CONTEXT ARTIFACTS` section for reusable discoveries.

## CP2 Failure Handling

Failure handling rules, blocking reasons, evidence format, and the no-retry policy are canonical in `GATE.md`.

CP4 does not run when CP2 blocks before executor output exists.

## CP3: Reconciliation

Run CP3 only after CP2 when **at least one** of these deterministic conditions holds:

- CP1 chose `Cross-Validation`
- Any returned ERP block has `Meets Spec? NO` or `WITH_DEBT`
- Any returned ERP block has a non-empty `## CLARIFICATIONS NEEDED`
- Any returned ERP block has `NEXT STEPS / CONTINUATION = CONTINUE_SESSION`
- Two or more workers ran on the same phase and their `## FILES MODIFIED` lists overlap

If none of these hold, skip CP3 and go straight to CP4.

Claude must:
- parse every `# EXTERNAL RESPONSE PROTOCOL v1.1` block returned from Codex and/or Gemini
- compare `SUMMARY`, `FILES MODIFIED`, `SPEC COMPLIANCE`, `CLARIFICATIONS NEEDED`, and `NEXT STEPS / CONTINUATION`
- decide whether to proceed, retry external execution, continue the same external session, or ask the user

Decision rules:
- if all models say `Meets Spec? YES` and there are no conflicts, proceed to CP4
- if any model reports incomplete or failed spec compliance, identify the gap and decide whether to retry or fix through external execution
- if `CLARIFICATIONS NEEDED` is present, answer internally if possible; otherwise ask the user
- if any model says `CONTINUE_SESSION`, continue with that model on the same phase
- if conflicting edits are reported on the same file, resolve against the original requirement as the source of truth
- if no files were modified but `Meets Spec? YES`, treat the task as completed and proceed to CP4

CP3 constraints:
- do not apply file edits in CP3
- output the exact `# CP3 RECONCILIATION COMPLETE` block

## CP3.5: Integration Checks

Before CP4 reviews the phase, run the integration checks declared in the phase's `Done When` (build, lint, type-check, tests, smoke commands). Treat this as a numbered, non-skippable step:

- If all checks pass → record results and proceed to CP4 with that evidence.
- If any check fails → CP4 input includes the failure; CP4 must return `FAIL` (not `PASS_WITH_DEBT`). Dispatch a Tier-2 follow-up against the failing check.
- If the phase declared no integration checks (pure docs/coordination) → record "no integration checks declared" and proceed.

Integration checks here mean **build/test pipeline** checks, not the multi-model integration described in `INTEGRATION.md`.

## CP4: Phase Review

Run CP4 after CP3.5 integration checks complete (or directly after Claude-only tasks).

CP4 reviews: original user request, CP1 success criteria, reviewer checklist, and integration results. Returns `PASS`, `PASS_WITH_DEBT`, or `FAIL`.

CP4 scope and outcomes are canonical in `review-chain.md`. Format block in `shared/protocol-threshold.md`.

## User Override

- "Use Codex" / "Use Gemini" / "Cross-validate" force corresponding routing.
- "Do not use external models" forces `CLAUDE` for docs and coordination only.

