#!/usr/bin/env bash
# UserPromptSubmit hook for superpowers-ccg plugin

set -euo pipefail

# Print the reminder as literal text so markdown backticks never trigger shell execution.
cat <<'EOF'
[CP Protocol Threshold]

Before the first Task call, do minimal CP0 context acquisition using Auggie for full local context retrieval and Grok Search only for external/current knowledge or research.
Immediately after CP0 completes, run CP1 Task Assessment & Routing using the original user request and the CP0 context artifacts, then build one task-scoped context bundle for the next bounded task.
CP1 routing guide:
| Task Category | Model | Cross-Validation | Notes / Triggers |
|---|---|---|---|
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
If the request is unclear or incomplete, route to Claude, output the CP1 block below, and then immediately ask clarifying questions.
If CP1 routes to Gemini, Codex, or Cross-Validation, run CP2 External Execution using a task-scoped context bundle: compressed original request, context refs, hydrated context snippets, and the CP1 task summary plus success criteria. Reuse the same worker SESSION_ID only for follow-up fixes on that bounded task, and send deltas only on follow-up turns. Require final file contents directly (preferred) or a unified diff patch using External Response Protocol v1.1.
If CP1 chose Cross-Validation or CP2 returned conflicts, overlap, PARTIAL/NO spec compliance, clarifications, CONTINUE_SESSION, or other non-trivial feedback, run CP3 Reconciliation. In CP3, parse every External Response Protocol block, resolve conflicts against the original requirement, decide whether to proceed, retry, continue, or ask the user, and do not apply file edits yourself.
Always run CP4 Final Spec Review as the final step, after CP3 when reconciliation is needed or directly after Claude-only / non-reconciled work. In CP4, use the original user request, the CP1 task summary, and the files changed by the workflow to judge spec satisfaction only. Do not perform code quality, style, redundancy, or best-practice review in CP4.

Use the exact CP1, CP3, and CP4 formats below. Do not add extra narration inside those blocks. Use the literal headings and field labels exactly as written. Do not rename them. The CP1 route bullets must begin exactly with `- Model:`, `- Cross-Validation:`, and `- Reason:`. Legacy `[CP1 Assessment]`, `[CP1] Routing`, `[CP3 Assessment]`, and `[CP3] Verified` formats are invalid.

# CP1 ROUTING DECISION

## Task Summary
[One-sentence English summary of the request]

## Route
- Model: Gemini / Codex / Cross-Validation (Codex + Gemini) / Claude
- Cross-Validation: Yes / No
- Reason: [short 1-line justification]

## Next Action
[Proceed to CP2 with the chosen model(s) OR handle directly OR ask user]

# CP3 RECONCILIATION COMPLETE

## Summary
[One-sentence summary of what was merged/applied]

## Changes Applied
- [List of files created/edited/deleted]

## Status
Ready for CP4

# CP4 SPEC REVIEW COMPLETE

## Result
- **Status**: PASS / PARTIAL / FAIL
- **Explanation**: [Clear, concise explanation]

## Recommendation
- If PASS: Task is complete
- If PARTIAL/FAIL: [Specific gaps + suggested next action (e.g. re-run external model or ask user)]
EOF
