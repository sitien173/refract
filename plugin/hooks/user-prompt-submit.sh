#!/usr/bin/env bash
# UserPromptSubmit hook for superpowers-ccg plugin

set -euo pipefail

cat <<'EOF'
[CCG Workflow — 3 gates]

Use Plan → Execute → Review for any implementation work.

1. **Plan.** New feature / ideation / proposal → CROSS_VALIDATION first (Codex + Gemini narrow question, reconcile, then plan). Otherwise gather minimum context with whatever tool fits. Define one phase: 2-4 tasks, file set, Done When. Output:

# ROUTE
- Owner: Claude | Codex | Gemini | Cross-Validation
- Reason: [one line — back-side / front-side / simple / new-feature ideation]
- Done When: [commands or acceptance bullets]

Routing by side (no default):
- Claude — simple tasks handled directly (one-line edit, rename, doc tweak, clarification).
- Codex — back-side: backend, API, logic, database, system, infra, CI/CD, scripts, server-side tests.
- Gemini — front-side: UI, CSS, motion, canvas/SVG, interactions, multimodal, large-context UI/doc sweeps.
- Cross-Validation — mandatory for new features / ideation / proposals before planning; reconcile, then assign side owner.
- Full-stack phase → split into back-side + front-side sub-phases. Ambiguous side → ask user.

2. **Execute.** Claude edits directly for simple tasks. Otherwise invoke `mcp__openmcp__run(backend="codex", ...)` (back-side, Codex) or `mcp__openmcp__run(backend="agy", ...)` (front-side, Gemini). For Cross-Validation: ask both the same narrow question, reconcile divergences, then route implementation to one side owner. Worker returns:

# EXTERNAL RESPONSE
## SUMMARY
[one sentence]
## FILES MODIFIED
| Action | Path | Change |
## SPEC COMPLIANCE
- Meets Spec? YES | WITH_DEBT | NO
- Explanation: ...
## NEXT
TASK_COMPLETE | CONTINUE_SESSION | HANDOVER_TO_CLAUDE

Same-phase fix: reuse `SESSION_ID`, send `FIX:` + delta only.

3. **Review.** Two sub-steps:
   (a) Spec — run Done When checks (build/lint/test).
   (b) Quality scan on `## FILES MODIFIED` — edge cases, error handling, security, naming, duplication, correctness. CRITICAL/HIGH → force FAIL; MEDIUM → downgrade PASS to PASS_WITH_DEBT; LOW noted only. Skip for docs-only / trivial Claude direct edits; required for every Codex / Gemini phase.

Output:

# REVIEW
- Spec Status: PASS | PASS_WITH_DEBT | FAIL
- Quality Findings:
  | Severity | path:line | Problem | Fix |
  (or "No findings" / "Skipped: <reason>")
- Final Status: PASS | PASS_WITH_DEBT | FAIL
- Explanation: [one line]
- Next: [done | debt + owner | retry/clarify]

Hard rules:
- MCP failure (timeout, unavailable, session-failed, permission-blocked, prompt too long) → `BLOCKED`, ask the human. No retry, no executor switch, no Task/Agent fallback without explicit consent.
- Long input (>~8KB / >1500 tokens) → write to a repo file (prefer `docs/plans/`), pass the path. Never paste raw guides/specs/research into the MCP `PROMPT`.
- One phase, one owner, one review. No draft-then-reimplement handoffs.
EOF
