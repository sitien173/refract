# Protocol Threshold (Shared Reference)

All skills that use checkpoints must follow the CP protocol injected by hooks.

## CP0: Context Acquisition

- CP0 happens before CP1.
- Gather only the minimum context required to route the next bounded task.
- Use the Hybrid Context Engine:
  - Auggie for semantic "where/what/how" discovery in the codebase
  - Morph WarpGrep for fast parallel search and file-set narrowing
  - Serena for symbol navigation, references, project memory, and graph context
  - Grok Search only when the task needs external/current knowledge
- CP0 is a retrieval phase, not a narration phase. Do not turn it into a long summary.

CP0 tool matrix:

| Need | Primary Tool | When to Trigger Grok Search | Fallback |
| --- | --- | --- | --- |
| Semantic "Where/What/How" in codebase | Auggie | Do not trigger Grok Search during normal local-context retrieval | None |
| Fast parallel search inside the codebase | Morph WarpGrep | Do not trigger Grok Search during normal local-context retrieval | Auggie |
| Symbol navigation & references | Serena | Do not trigger Grok Search during normal local-context retrieval | Morph WarpGrep |
| Persistent project memory / graph | Serena | Do not trigger Grok Search during normal local-context retrieval | None |
| External / real-world knowledge | Grok Search | When the task mentions "latest", "current", "best practice", an unknown library, or a raw error that needs external research | None |

## Required Behavior

- Before the first Task call, output a standalone `# CP1 ROUTING DECISION` block.
- When CP2 is invoked, require `# EXTERNAL RESPONSE PROTOCOL v1.1` with final file content preferred and unified diff fallback.
- When CP3 is triggered, output a standalone `# CP3 RECONCILIATION COMPLETE` block.
- Always end the workflow with a standalone `# CP4 SPEC REVIEW COMPLETE` block.
- Keep checkpoint blocks minimal. The checkpoint is a gate, not a summary.
- Legacy `[CP1 Assessment]` and `[CP1] Routing` formats are invalid for CP1.
- Legacy `[CP3 Assessment]` and `[CP3] Verified` formats are invalid for CP3.
- Do not rename the CP4 headings or bullets.
- Use the literal CP1 headings and field labels exactly as written. Do not bold or rename them.
- The route bullets must begin exactly with `- Model:`, `- Cross-Validation:`, and `- Reason:`.

## CP1: Task Assessment & Routing

When it runs: immediately after CP0 completes.

Goal: perform a quick, structured task assessment and choose the optimal route using the inline CP1 routing guide below.

Task Assessment Process:

1. Read the original user request and the full `CONTEXT_PACKAGE` from CP0.
2. Summarize the core task in one English sentence.
3. Assess clarity and completeness.
4. If the task is unclear or underspecified, route to `Claude`, output the CP1 block, then immediately ask clarifying questions.
5. Classify the task against the inline CP1 routing guide below.
6. Decide the model and whether cross-validation is needed.
7. Output the exact block below.

## CP1 Routing Guide

| Task Category | Model | Cross-Validation | Notes / Triggers |
| --- | --- | --- | --- |
| Pure Frontend / UI / Styling | Gemini | No | Fastest path |
| Pure Backend / Logic / API | Codex | No | Use cross-validation only if the task becomes high-impact or architecture-heavy |
| Full-Stack / Architecture | Cross-Validation (Codex + Gemini) | Yes | Both models run in parallel |
| Docs / Comments / Simple Fix | Claude | No | Usually no external models |
| Debugging / Performance | Codex | No | Escalate to cross-validation only if the failure mode stays ambiguous |
| Infrastructure / DevOps | Codex | No | Use cross-validation only for high-risk changes |
| Data / ML / Analytics | Codex | No | Use cross-validation only if the task becomes unusually complex |
| Testing / Test Coverage | Cross-Validation (Codex + Gemini) | Yes | Useful when tests span frontend and backend behavior |
| Cross-Cutting / Security | Codex | Yes | Extra safety layer |
| Uncategorized / Ambiguous | Claude | No | Fail-closed: ask clarifying questions immediately |

## CP1 Routing Decision Format

```text
# CP1 ROUTING DECISION

## Task Summary
[One-sentence English summary of the request]

## Route
- Model: Gemini / Codex / Cross-Validation (Codex + Gemini) / Claude
- Cross-Validation: Yes / No
- Reason: [short 1-line justification]

## Next Action
[Proceed to CP2 with the chosen model(s) OR handle directly OR ask user]
```

## CP2: External Execution

When it runs: only when CP1 routes the bounded task to `Gemini`, `Codex`, or `Cross-Validation`.

Goal: the external model performs the actual work and returns the final artifact directly.

Required CP2 input:

1. original user request
2. full `CONTEXT_PACKAGE` from CP0
3. CP1 task summary and success criteria

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

## SPEC COMPLIANCE
- Meets Spec? YES / PARTIAL / NO
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

## CP4: Final Spec Review

When it runs: always as the last step, after CP3 when reconciliation was needed or directly after Claude-only / non-reconciled work.

Goal: perform a pure spec review against the original user request and the CP1 success criteria.

CP4 rules:

- Review only spec satisfaction.
- Do not perform code quality, style, redundancy, or best-practice review.
- Return `PASS`, `PARTIAL`, or `FAIL`.

```text
# CP4 SPEC REVIEW COMPLETE

## Result
- **Status**: PASS / PARTIAL / FAIL
- **Explanation**: [Clear, concise explanation]

## Recommendation
- If PASS: Task is complete
- If PARTIAL/FAIL: [Specific gaps + suggested next action (e.g. re-run external model or ask user)]
```

## Checkpoint Logic

- **CP0:** gather only the context needed to define the next bounded task
- **CP1:** assess the task, choose the route, and invoke the worker if needed
- **CP2:** execute the routed bounded task externally and collect the returned artifact
- **CP3:** reconcile cross-validation output or other non-trivial external feedback before CP4
- **CP4:** perform the final pure spec review and decide PASS / PARTIAL / FAIL
