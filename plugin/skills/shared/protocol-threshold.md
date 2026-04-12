# Protocol Threshold (Shared Reference)

All skills that use checkpoints must follow the CP protocol injected by hooks.

## CP0: Context Acquisition

- CP0 happens before CP1.
- Gather only the minimum context required to route the next phase.
- Use Auggie for full local codebase context retrieval.
- Use Grok Search only when the task needs external/current knowledge or research.
- Normalize CP0 findings into reusable `CONTEXT_ARTIFACTS`.
- CP0 is a retrieval phase, not a narration phase. Do not turn it into a long summary.

CP0 tool matrix:

| Need | Primary Tool | When to Trigger Grok Search | Fallback |
| --- | --- | --- | --- |
| Local codebase context / implementation anchors | Auggie | Do not trigger Grok Search during normal local-context retrieval | None |
| External / real-world knowledge | Grok Search | When the task mentions "latest", "current", "best practice", an unknown library, or a raw error that needs external research | None |

## Required Behavior

- Before the first executor call, output a standalone `# CP1 ROUTING DECISION` block.
- When CP2 is invoked, require `# EXTERNAL RESPONSE PROTOCOL v1.1` with final file content preferred and unified diff fallback.
- When CP3 is triggered, output a standalone `# CP3 RECONCILIATION COMPLETE` block.
- Always review each phase with a standalone `# CP4 SPEC REVIEW COMPLETE` block.
- Keep checkpoint blocks minimal. The checkpoint is a gate, not a summary.
- Legacy `[CP1 Assessment]` and `[CP1] Routing` formats are invalid for CP1.
- Legacy `[CP3 Assessment]` and `[CP3] Verified` formats are invalid for CP3.
- Do not rename the CP4 headings or bullets.
- Use the literal CP1 headings and field labels exactly as written. Do not bold or rename them.
- The route bullets must begin exactly with `- Model:`, `- Cross-Validation:`, and `- Reason:`.

## CP1: Phase Assessment & Routing

When it runs: immediately after CP0 completes.

Goal: perform a quick, structured phase assessment and choose the optimal route using the inline CP1 routing guide below.

Phase Assessment Process:

1. Read the original user request and the CP0 context artifacts.
2. Summarize the active phase in one English sentence.
3. Assess clarity and completeness.
4. If the task is unclear or underspecified, route to `Claude`, output the CP1 block, then immediately ask clarifying questions.
5. Classify the task against the inline CP1 routing guide below.
6. Decide the model and whether cross-validation is needed.
7. Build one `PHASE_CONTEXT_BUNDLE` for the next phase with `TASK_ID`, `CONTEXT_REFS`, and `HYDRATED_CONTEXT`.
8. Output the exact block below.

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
- Reason: [short 1-line justification]

## Next Action
[Proceed to CP2 with the chosen model(s) OR handle directly OR ask user]
```

## CP2: External Execution

When it runs: only when CP1 routes the phase to `Gemini`, `Codex`, or `Cross-Validation`.

Goal: the external model performs the actual work and returns the final artifact directly.

Required CP2 input:

1. compressed original user request
2. one `PHASE_CONTEXT_BUNDLE` containing:
   - `TASK_ID`
   - `CONTEXT_REFS`
   - `HYDRATED_CONTEXT`
3. CP1 phase summary, success criteria, and reviewer checklist
4. explicit file set and integration checks
5. for same-phase follow-ups on the same worker session: deltas only

Context budget:

- Planner phase context: <= 1500 tokens
- Executor prompt context: <= 2500 tokens when practical
- `HYDRATED_CONTEXT`: <= 800 tokens, preferably <= 300 tokens
- Same-phase follow-up: <= 1000 tokens
- If the budget is exceeded, narrow the phase or replace snippets with `CONTEXT_REFS`

Direct output mode:

- Prefer complete final file content.
- Allow a unified diff patch when full file content is not practical.

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

## FILE CONTENTS
For each file listed in FILES MODIFIED, return either:
1. the complete final file content (preferred), or
2. a unified diff patch for that file when full content is impractical.

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
- If PASS: Task is complete
- If PASS_WITH_DEBT: [Non-blocking debt + owner/timing]
- If FAIL: [Specific gaps + suggested next action (e.g. re-run external model or ask user)]
```

## Checkpoint Logic

- **CP0:** gather only the context needed to define the next phase
- **CP1:** assess the phase, choose the route, and invoke the worker if needed
- **CP2:** execute the routed phase externally and collect the returned artifact
- **CP3:** reconcile cross-validation output or other non-trivial external feedback before CP4
- **CP4:** perform the phase review and decide PASS / PASS_WITH_DEBT / FAIL
