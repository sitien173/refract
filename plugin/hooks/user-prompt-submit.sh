#!/usr/bin/env bash
# UserPromptSubmit hook for superpowers-ccg plugin

set -euo pipefail

# Print the reminder as literal text so markdown backticks never trigger shell execution.
cat <<'EOF'
[CP Protocol Threshold]

Before the first executor call, do minimal CP0 context acquisition using Auggie for full local context retrieval and Grok Search only for external/current knowledge or research.
Immediately after CP0 completes, run CP1 Phase Assessment & Routing using the original user request and the CP0 context artifacts, then choose `Session-Policy` and the right prompt tier for the next implementation phase.
CP1 routing guide:
| Task Category | Model | Cross-Validation | Notes / Triggers |
|---|---|---|---|
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
If the request is unclear or incomplete, route to Claude, output the CP1 block below, and then immediately ask clarifying questions.
If CP1 routes to Gemini, Codex, or Cross-Validation, run CP2 External Execution using the 3-tier prompt system: Tier 1 initial call for fresh sessions, Tier 2 for same-phase follow-up fixes, and Tier 3 for cross-phase continuation when `Session-Policy` is `CONTINUE`. Reuse the same worker `SESSION_ID` for Tier 2 fixes on that phase or Tier 3 continuation on a related phase, and send deltas only when continuing. Workers edit files directly via MCP write tools and respond using External Response Protocol v1.1; the response lists `## FILES MODIFIED` without duplicating file content.
Smart context budget: Tier 1 initial call <= 1500 tokens, Tier 2 same-phase follow-up <= 400 tokens, Tier 3 cross-phase continuation <= 600 tokens, `HYDRATED_CONTEXT` <= 300 tokens hard cap. If over budget, narrow the phase or shrink the hydrated snippets. Never pre-write new implementation inside `HYDRATED_CONTEXT`.
If Gemini fails once with timeout, tool-unavailable, or session/tool instability, fall back to Codex or Claude-code. If Codex fails, retry once, then fall back to Claude-code/Sonnet. Permission-blocked remains BLOCKED.
Run CP3 Reconciliation only when at least one deterministic trigger holds: CP1 chose Cross-Validation; OR any returned ERP block has `Meets Spec? NO` or `WITH_DEBT`; OR any block has non-empty `## CLARIFICATIONS NEEDED`; OR any block has `NEXT STEPS / CONTINUATION = CONTINUE_SESSION`; OR two workers' `## FILES MODIFIED` lists overlap. Otherwise skip CP3 and proceed to CP3.5 integration checks. In CP3, parse every External Response Protocol block, resolve conflicts against the original requirement, decide whether to proceed, retry, continue, or ask the user, and do not apply file edits yourself. After CP3 (or directly after CP2 if CP3 was skipped), run the phase's declared build/lint/test integration checks before CP4.
Run CP4 Phase Review after each phase, after CP3 when reconciliation is needed or directly after Claude-only / non-reconciled work. In CP4, use the original user request, the CP1 phase summary, reviewer checklist, integration results, and files changed by the workflow to judge phase satisfaction. Do not perform broad code quality, style, redundancy, or best-practice review in CP4 unless listed in the phase checklist.

Use the exact CP1, CP3, and CP4 formats below. Do not add extra narration inside those blocks. Use the literal headings and field labels exactly as written. Do not rename them. The CP1 route bullets must begin exactly with `- Model:`, `- Cross-Validation:`, `- Session-Policy:`, and `- Reason:`. Legacy `[CP1 Assessment]`, `[CP1] Routing`, `[CP3 Assessment]`, and `[CP3] Verified` formats are invalid.

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

# CP3 RECONCILIATION COMPLETE

## Summary
[One-sentence summary of what was merged/applied]

## Changes Applied
- [List of files created/edited/deleted]

## Status
Ready for CP4

# CP4 SPEC REVIEW COMPLETE

## Result
- **Status**: PASS / PASS_WITH_DEBT / FAIL
- **Explanation**: [Clear, concise explanation]

## Recommendation
- If PASS: Phase is complete
- If PASS_WITH_DEBT: [Non-blocking debt + owner/timing]
- If FAIL: [Specific gaps + suggested next action (e.g. re-run external model or ask user)]
EOF
