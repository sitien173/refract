# Protocol Threshold (Shared Reference)

> Exact CP1, CP3, and CP4 response blocks and ERP v1.1 format are canonical here for hook injection. All other checkpoint rules are canonical in `skills/coordinating-multi-model-work/checkpoints.md`, routing in `rules/ccg-workflow.mdc`, tier budgets and `SESSION_POLICY` in `skills/coordinating-multi-model-work/context-sharing.md`.

All skills that use checkpoints must follow the CP protocol injected by hooks.

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

## CP3 Reconciliation Format

```text
# CP3 RECONCILIATION COMPLETE

## Summary
[One-sentence summary of what was merged/applied]

## Changes Applied
- [List of files created/edited/deleted]

## Status
Ready for CP4
```

## CP4 Phase Review Format

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
