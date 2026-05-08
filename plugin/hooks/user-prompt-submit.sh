#!/usr/bin/env bash
# UserPromptSubmit hook for superpowers-ccg plugin

set -euo pipefail

# Print the reminder as literal text so markdown backticks never trigger shell execution.
cat <<'EOF'
[CP Protocol Threshold]

Before the first executor call, do minimal CP0 context acquisition: decide if selective `docs/wiki/` durable knowledge lookup is useful, use it only for complex planning/architecture/debugging/refactors or prompts asking what was known/decided/tried, then MUST run context-retrieval via `codebase-retrieval` for current local context before CP1 on every task (no trivial/current-file skip). If `codebase-retrieval` errors, is unavailable, permission-blocked, or returns tool failure, immediately output `BLOCKED` and stop before CP1. Do not switch to file tools, Grok Search, or executors. Use Grok Search only for external/current research after mandatory local retrieval succeeds.
Normalize wiki findings as `wiki/relevant`, `wiki/decisions`, `wiki/conflicts`, or `wiki/sources`; wiki is advisory and citation-backed, while current files/tests and the current user request override it. Do not dump full wiki pages into worker prompts; keep `HYDRATED_CONTEXT` <= 300 tokens.
Immediately after CP0 completes, run CP1 Phase Assessment & Routing using the original user request and the CP0 context artifacts, then choose `Session-Policy` and the right prompt tier for the next implementation phase.
CP1 routing guide:
| Task Category | Model | Cross-Validation | Notes / Triggers |
|---|---|---|---|
| Backend / Logic / API | Codex | No | Default implementation route |
| Tests / CI / Terminal / Infra-DevOps | Codex | No | Terminal-Bench leader |
| Large refactor (>=10 files or >1K LOC) | Codex | No | 7-hr horizon |
| Bug fix / Debugging / Performance | Codex | No | Snappy small + sustained deep |
| Data / ML / Analytics | Codex | No | Logic-heavy |
| UI components / CSS / animation / canvas / SVG | Gemini | No | WebDev Arena leader |
| Multimodal input -> code | Gemini | No | Only multimodal frontier |
| Large-context sweep (>200K tokens) | Gemini | No | 1M ctx, cheapest tier |
| Visual regression / screen automation / OCR | Gemini | No | ScreenSpot-Pro 72.7% |
| Doc / spec extraction from PDFs / diagrams | Gemini | No | Document understanding |
| Security / compliance / legal-sensitive code | Codex | No (mandatory Claude review gate) | Hallucination guardrail |
| Architecture conflict / multi-domain | Cross-Validation (Codex + Gemini) | Yes | Rare arbitration |
| Docs / Comments / Coordination / Simple edits | Claude | No | Per user constraint |
| Orchestration / Review / Integration / Planning | Claude | No | Per user constraint |
| Uncategorized / Ambiguous | Claude | No | Fail-closed; clarify |
New routing axes: context-size (>200K) -> Gemini; multimodal input -> Gemini; horizon length (>1 hour autonomous chain) -> Codex.
Tiebreaker order: (1) Hallucination-sensitive -> Codex + Claude review gate, (2) Multimodal input -> Gemini, (3) Context >200K -> Gemini, (4) UI-dominant -> Gemini, (5) Else -> Codex.
If the request is unclear or incomplete, route to Claude, output the CP1 block below, and then immediately ask clarifying questions.
If CP1 routes to Gemini, Codex, or Cross-Validation, run CP2 External Execution using the 3-tier prompt system: Tier 1 initial call for fresh sessions, Tier 2 for same-phase follow-up fixes, and Tier 3 for cross-phase continuation when `Session-Policy` is `CONTINUE`. Reuse the same worker `SESSION_ID` for Tier 2 fixes on that phase or Tier 3 continuation on a related phase, and send deltas only when continuing. Workers edit files directly via MCP write tools and respond using External Response Protocol v1.1; the response lists `## FILES MODIFIED` without duplicating file content.
Smart context budget: Tier 1 initial call <= 1500 tokens, Tier 2 same-phase follow-up <= 400 tokens, Tier 3 cross-phase continuation <= 600 tokens, `HYDRATED_CONTEXT` <= 300 tokens hard cap. If over budget, narrow the phase or shrink the hydrated snippets. Never pre-write new implementation inside `HYDRATED_CONTEXT`.
For CP2 prompts, keep MCP `PROMPT` small: never paste long guides/research/reports/specs/raw source into `PROMPT` or `HYDRATED_CONTEXT`. Put long material in repo-local artifact files (prefer `docs/plans/` or the task's existing input/output file), then pass file paths plus short summary/instructions so the worker reads from disk.
If user-provided long text is needed and no suitable file exists, create a local artifact file first, then prompt with its path.
If any Codex or Gemini MCP call fails with timeout, tool-unavailable, session-failed, session/tool instability, model error, or permission-blocked, output `BLOCKED` immediately and ask the human to retry or explicitly consent to an alternate route. Do not retry, switch executors, spawn subagents/Task/Agent fallback, or handle implementation directly without explicit human consent after the block.
If an MCP call returns `command line is too long` or equivalent prompt-packaging failure, output `BLOCKED` immediately and ask the human to retry with file-backed input or explicitly consent to an alternate route; do not retry/switch/spawn fallback/handle directly without explicit human consent after the block.
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

