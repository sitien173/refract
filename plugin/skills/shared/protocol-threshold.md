# Protocol Threshold (Shared Reference)

> Exact CP1, CP3, and CP4 response blocks are canonical here for hook injection. Tier-prompt rules, budgets, `SESSION_POLICY` decisions, and the Tier 3 freshness check are canonical in `skills/coordinating-multi-model-work/context-sharing.md`.

All skills that use checkpoints must follow the CP protocol injected by hooks.

## Contents

- CP0: Context Acquisition
- Required Behavior
- CP1: Phase Assessment & Routing
- CP2: External Execution
- External Response Protocol v1.1
- CP3: Reconciliation
- CP4: Phase Review
- Checkpoint Logic

## CP0: Context Acquisition

- CP0 happens before CP1.
- Gather only the minimum context required to route the next phase.
- Decide whether `docs/wiki/` durable knowledge is useful before code retrieval.
- Selectively consult `docs/wiki/` for complex planning, architecture, debugging, refactors with prior decisions, or prompts asking what the project knows, decided, or tried.
- Skip wiki lookup for trivial edits, simple version bumps, formatting, and tasks answerable from current files.
- Use Auggie for full local codebase context retrieval after any useful wiki lookup.
- Use Grok Search only when the task needs external/current knowledge or research.
- Normalize CP0 findings into reusable `CONTEXT_ARTIFACTS`.
- Treat wiki content as advisory and citation-backed; current files, tests, and current user request override it.
- CP0 is a retrieval phase, not a narration phase. Do not turn it into a long summary.

CP0 tool matrix:

| Need | Primary Tool | When to Trigger Grok Search | Fallback |
| --- | --- | --- | --- |
| Durable project knowledge / prior decisions | `docs/wiki/` selective lookup | Do not trigger Grok Search for project-local wiki lookup | Skip when uninitialized or irrelevant |
| Local codebase context / implementation anchors | Auggie | Do not trigger Grok Search during normal local-context retrieval | None |
| External / real-world knowledge | Grok Search | When the task mentions "latest", "current", "best practice", an unknown library, or a raw error that needs external research | None |

## Required Behavior

- Before the first executor call, output a standalone `# CP1 ROUTING DECISION` block.
- When CP2 is invoked, require `# EXTERNAL RESPONSE PROTOCOL v1.1`. Workers edit files directly via MCP write tools; the response lists changed files in `## FILES MODIFIED` but does not duplicate file content.
- When CP3 is triggered, output a standalone `# CP3 RECONCILIATION COMPLETE` block.
- Always review each phase with a standalone `# CP4 SPEC REVIEW COMPLETE` block.
- Keep checkpoint blocks minimal. The checkpoint is a gate, not a summary.
- Legacy `[CP1 Assessment]` and `[CP1] Routing` formats are invalid for CP1.
- Legacy `[CP3 Assessment]` and `[CP3] Verified` formats are invalid for CP3.
- Do not rename the CP4 headings or bullets.
- Use the literal CP1 headings and field labels exactly as written. Do not bold or rename them.
- The route bullets must begin exactly with `- Model:`, `- Cross-Validation:`, `- Session-Policy:`, and `- Reason:`.

## CP1: Phase Assessment & Routing

When it runs: immediately after CP0 completes.

Goal: perform a quick, structured phase assessment and choose the optimal route using the inline CP1 routing guide below.

Phase Assessment Process:

1. Read the original user request and the CP0 context artifacts.
2. Summarize the active phase in one English sentence.
3. Assess clarity and completeness.
4. If the task is unclear or underspecified, route to `Claude`, output the CP1 block, then immediately ask clarifying questions.
5. Classify the task against the inline CP1 routing guide below.
6. Decide the model, whether cross-validation is needed, and `Session-Policy`.
7. Build the right executor prompt tier for the next phase:
   - Tier 1 for a fresh worker session
   - Tier 3 when continuing a related phase on the same worker session
8. Keep `HYDRATED_CONTEXT` under 300 tokens hard cap.
9. Output the exact block below.

## CP1 Routing Guide

| Task Category | Model | Cross-Validation | Notes / Triggers |
| --- | --- | --- | --- |
| UI-heavy visual implementation | Gemini | No | Use only when UI dominates the phase |
| Backend / Logic / API | Codex | No | Default implementation route |
| Full-Stack / Architecture | Codex | No | Cross-validate only for unresolved architecture conflict |
| Docs / Comments / Coordination | Claude | No | Usually no external executor |
| Debugging / Performance | Codex | No | Escalate to cross-validation only if the failure mode stays ambiguous |
| Infrastructure / DevOps | Codex | No | Use cross-validation only for high-risk changes |
| Data / ML / Analytics | Codex | No | Use cross-validation only if the task becomes unusually complex |
| Testing / Test Coverage | Codex | No | Gemini only for visual/UI-heavy tests |
| Cross-Cutting / Security | Codex | No | Add Claude/human review instead of default cross-validation |
| Uncategorized / Ambiguous | Claude | No | Fail-closed: ask clarifying questions immediately |

## CP1 Routing Decision Format

```text
# CP1 ROUTING DECISION

## Task Summary
[One-sentence English summary of the phase]

## Route
- Model: Gemini / Codex / Cross-Validation (Codex + Gemini) / Claude
- Cross-Validation: Yes / No
- Session-Policy: CONTINUE / FRESH
- Reason: [short 1-line justification]

## Next Action
[Proceed to CP2 with the chosen model(s) OR handle directly OR ask user]
```

## CP2: External Execution

When it runs: only when CP1 routes the phase to `Gemini`, `Codex`, or `Cross-Validation`.

Goal: the external model performs the actual work and returns the final artifact directly.

CP2 uses the 3-tier prompt system:

1. Tier 1 initial call: `Task`, `Phase` (`TASK_ID` + `SESSION_POLICY: FRESH`), `Context`, `Files`, `Done When`, and full ERP v1.1
2. Tier 2 same-phase follow-up: `SESSION_ID`, `FIX`, `DELTA_FILES`, `DELTA_CONTEXT`, and `Respond using ERP v1.1`
3. Tier 3 cross-phase continuation: `SESSION_ID`, `SESSION_POLICY: CONTINUE`, `PHASE`, `New Phase`, `New/Changed Files`, `Delta Context`, `Done When`, and `Respond using ERP v1.1`
4. Tier 2 is for same-phase fixes only; do not exceed 2 Tier-2 follow-ups on one phase

Context budget:

- Tier 1 initial call: <= 1500 tokens
- Tier 2 same-phase follow-up: <= 400 tokens
- Tier 3 cross-phase continuation: <= 600 tokens
- `HYDRATED_CONTEXT`: <= 300 tokens hard cap
- If the budget is exceeded, narrow the phase or shrink the hydrated snippets

Direct output mode:

- Workers edit files directly via MCP write tools. The on-disk files are the source of truth.
- The response must list every changed file in `## FILES MODIFIED` but does not duplicate file content.

## External Response Protocol v1.1

```text
# EXTERNAL RESPONSE PROTOCOL v1.1

## SUMMARY
One-sentence summary of what you did.

## FILES MODIFIED
| Action  | File Path          | Description of Change |
|---------|--------------------|-----------------------|
| Created | src/...            | ...                   |
| Edited  | src/...            | ...                   |

## CONTEXT ARTIFACTS
[optional reusable artifacts discovered or updated during execution]

## SPEC COMPLIANCE
- Meets Spec? YES / WITH_DEBT / NO
- Explanation: ...

## CLARIFICATIONS NEEDED
None (or list questions)

## NEXT STEPS / CONTINUATION
TASK_COMPLETE / CONTINUE_SESSION / HANDOVER_TO_CLAUDE
```

## CP3: Reconciliation

```text
# CP3 RECONCILIATION COMPLETE

## Summary
[One-sentence summary of what was merged/applied]

## Changes Applied
- [List of files created/edited/deleted]

## Status
Ready for CP4
```

## CP4: Phase Review

When it runs: after each phase, after CP3 when reconciliation was needed or directly after Claude-only / non-reconciled work.

Goal: perform a phase review against the original user request, CP1 success criteria, reviewer checklist, and integration results.

CP4 rules:

- Review only spec satisfaction.
- Do not perform broad code quality, style, redundancy, or best-practice review unless listed in the phase checklist.
- Return `PASS`, `PASS_WITH_DEBT`, or `FAIL`.

```text
# CP4 SPEC REVIEW COMPLETE

## Result
- **Status**: PASS / PASS_WITH_DEBT / FAIL
- **Explanation**: [Clear, concise explanation]

## Recommendation
- If PASS: Phase is complete
- If PASS_WITH_DEBT: [Non-blocking debt + owner/timing]
- If FAIL: [Specific gaps + suggested next action (e.g. re-run external model or ask user)]
```

## Checkpoint Logic

- **CP0:** gather only the context needed to define the next phase
- **CP1:** assess the phase, choose the route, and invoke the worker if needed
- **CP2:** execute the routed phase externally and collect the returned artifact
- **CP3:** reconcile cross-validation output or other non-trivial external feedback before CP4
- **CP4:** perform the phase review and decide PASS / PASS_WITH_DEBT / FAIL
