#!/usr/bin/env bash
# SessionStart hook for superpowers-ccg plugin

set -euo pipefail

COMPACT_CONTEXT="$(cat <<'ENDOFCOMPACT'
You have superpowers.

**Workflow: 3 gates — Plan → Execute → Review.**

1. **Plan.** New feature / ideation / proposal → run CROSS_VALIDATION first (Codex + Gemini narrow question), reconcile, then plan. Otherwise gather minimum context with whatever tool fits. Define one phase: 2-4 tasks, file set, Done When. Output the `# ROUTE` block.
2. **Execute.** Route by side (no default):
   - Claude — simple tasks Claude can do directly (one-line edits, doc tweaks, rename, clarification).
   - Codex (`mcp__codex__codex`) — **back-side**: backend, API, business logic, database, system, infra, CI/CD, scripts, server-side tests.
   - Gemini (`mcp__gemini__gemini`) — **front-side**: UI, CSS, motion, canvas/SVG, client interactions, multimodal input, large-context UI/doc sweeps.
   - Cross-Validation — new-feature ideation only; reconcile then assign side owner.
   Worker edits files via its own MCP write tools and returns `## FILES MODIFIED`.
3. **Review.** Two sub-steps:
   - (a) Spec: run Done When checks; PASS / PASS_WITH_DEBT / FAIL.
   - (b) Quality scan on `## FILES MODIFIED` (edge cases, error handling, security, naming, duplication, correctness). CRITICAL/HIGH → force FAIL; MEDIUM → downgrade PASS to PASS_WITH_DEBT; LOW noted. Skip for docs-only or trivial Claude direct edits; required for Codex/Gemini phases.
   Output `# REVIEW` with Spec Status, Quality Findings, Final Status.

**Hard rules:**
- MCP failure (timeout, unavailable, session-failed, permission-blocked, prompt too long) → output `BLOCKED`, ask the human. No retry, no executor switch, no Task/Agent fallback without explicit consent.
- Long input (>~8KB / >1500 tokens) → write to a repo file (prefer `docs/plans/`), pass the path. Never paste raw guides/specs/research into the MCP `PROMPT`.
- One phase, one owner, one review. No draft-then-reimplement handoffs.

**Skill namespace:** `superpowers-ccg:` — use Skill tool to load `coordinating-multi-model-work` for full details.
ENDOFCOMPACT
)"

escape_for_json() {
    local input="$1"
    local output=""
    local i char
    for (( i=0; i<${#input}; i++ )); do
        char="${input:$i:1}"
        case "$char" in
            $'\\') output+='\\' ;;
            '"') output+='\"' ;;
            $'\n') output+='\n' ;;
            $'\r') output+='\r' ;;
            $'\t') output+='\t' ;;
            *) output+="$char" ;;
        esac
    done
    printf '%s' "$output"
}

compact_escaped=$(escape_for_json "$COMPACT_CONTEXT")

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\n${compact_escaped}\n</EXTREMELY_IMPORTANT>"
  }
}
EOF

exit 0
