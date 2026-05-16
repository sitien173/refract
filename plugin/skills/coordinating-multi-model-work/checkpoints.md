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
- CP4.5: Quality Review
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
- MUST run stellaris via `search_code` for local semantic anchors, unfamiliar subsystems, architecture relationships, exact references, and stale wording checks before CP1 on every task (including trivial/current-file tasks). Use `get_file_outline`, `get_file_folded`, and `get_symbol` for token-efficient drill-down (AST-aware, voyage-code-3 embeddings, LanceDB + FTS5 + RRF fusion).
- If `stellaris search_code` errors, is unavailable, permission-blocked, or returns tool failure, immediately output `BLOCKED` and stop before CP1.
- Do not switch to file tools, Grok Search, or executors when `stellaris search_code` fails.
- Use Grok Search only when the task needs external/current knowledge or research, and only after mandatory local retrieval succeeds.
- Normalize the useful output into small reusable `CONTEXT_ARTIFACTS`.
- Treat wiki content as advisory and citation-backed; current files, tests, and current user request override it.
- End CP0 as soon as the phase and likely owner are clear enough for CP1.

CP0 tool matrix:

| Need | Primary Tool | When to Trigger Grok Search | Fallback |
| --- | --- | --- | --- |
| Durable project knowledge / prior decisions | `docs/wiki/` selective lookup | Do not trigger Grok Search for project-local wiki lookup | Skip when uninitialized or irrelevant |
| Local codebase context / references / architecture relationships | `stellaris search_code` (mandatory before CP1) | Do not trigger Grok Search during mandatory local-context retrieval | `BLOCKED` (none; stop before CP1) |
| Symbol-level code precision / AST-aware structure | `stellaris get_file_outline` / `get_file_folded` / `get_symbol` | Do not trigger Grok Search for local symbol lookup | Skip if not needed after search_code |
| External / real-world knowledge | Grok Search | When the task mentions "latest", "current", "best practice", an unknown library, or a raw error that needs external research | None |

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

### Stellaris Index Refresh

After receiving a successful CP2 response, parse every file path listed in the ERP `## FILES MODIFIED` section and call `mcp__stellaris__reindex_file` for each one. This keeps the stellaris index current for CP3.5 integration checks and subsequent CP0 lookups. External workers edit files via their own MCP write tools, which do not trigger Claude's PostToolUse hooks — so Claude must reindex explicitly.

- Call `reindex_file` once per modified file, using absolute paths.
- Run all reindex calls in parallel (no dependencies between files).
- If `reindex_file` errors on a file, log and continue — do not block the phase.
- Skip this step when CP2 reports no files modified or when CP2 failed/blocked.

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

## CP4.5: Quality Review

Run CP4.5 after CP4 returns `PASS` or `PASS_WITH_DEBT`. Skip when CP4 returns `FAIL` (no point reviewing failed work).

### Purpose

CP4 answers "did the worker meet spec?" — CP4.5 answers "is the code good?" These are distinct concerns. CP4.5 catches quality issues that spec compliance alone misses.

### Trigger

CP4.5 runs on every phase. For docs/coordination phases, scope narrows to clarity and completeness only.

### Execution

Spawn a `cavecrew-reviewer` subagent with the list of files from `## FILES MODIFIED`. The reviewer checks:

| Category | What to look for |
| --- | --- |
| Edge cases | Missing null/undefined checks, empty arrays, boundary conditions, off-by-one |
| Error handling | Swallowed errors, missing catch blocks, unhelpful error messages, unhandled promise rejections |
| Security | Injection vectors (SQL, XSS, command), hardcoded secrets, unsafe deserialization, missing input validation at system boundaries |
| Naming & clarity | Misleading names, ambiguous abbreviations, functions doing more than their name says |
| Duplication | Copy-pasted logic that should be extracted, near-identical blocks across files |
| Correctness | Logic errors, race conditions, resource leaks, incorrect type narrowing |

The reviewer subagent receives only the changed file paths (not full content — it reads files itself). Reviewer output uses `cavecrew-reviewer` compressed format: `path:line: <severity>: <problem>. <fix>.`

### Severity levels

| Severity | Meaning | Effect on phase |
| --- | --- | --- |
| `CRITICAL` | Bug, security vulnerability, data loss risk | Downgrades to `FAIL` |
| `HIGH` | Likely bug or significant quality gap | Downgrades to `FAIL` |
| `MEDIUM` | Code smell, missing edge case, unclear logic | Downgrades to `PASS_WITH_DEBT` (if was `PASS`) |
| `LOW` | Minor naming, style, or minor duplication | No downgrade — noted only |

### Outcome

Claude evaluates reviewer findings against the phase context and outputs the `# CP4.5 QUALITY REVIEW COMPLETE` block.

- If no `CRITICAL` or `HIGH` findings → phase result unchanged, note any `MEDIUM` debt.
- If `CRITICAL` or `HIGH` findings exist → downgrade phase result. Dispatch Tier-2 fix to the same worker session for `HIGH`; for `CRITICAL`, ask user before proceeding.
- Findings that contradict the user's explicit request or project conventions are discarded with explanation.

### Skip conditions

- User says "skip review" or "no quality review" → skip CP4.5 for that phase.
- CP4 returned `FAIL` → skip (work needs redo, not polish).

## User Override

- "Use Codex" / "Use Gemini" / "Cross-validate" force corresponding routing.
- "Do not use external models" forces `CLAUDE` for docs and coordination only.

