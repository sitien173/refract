#!/usr/bin/env bash
# SessionStart hook for superpowers-ccg plugin

set -euo pipefail

# Check if legacy skills directory exists and build warning
warning_message=""
legacy_skills_dir="${HOME}/.config/superpowers/skills"
if [ -d "$legacy_skills_dir" ]; then
    warning_message="\n\n<important-reminder>IN YOUR FIRST REPLY AFTER SEEING THIS MESSAGE YOU MUST TELL THE USER:⚠️ **WARNING:** Superpowers now uses Claude Code's skills system. Custom skills in ~/.config/superpowers/skills will not be read. Move custom skills to ~/.claude/skills instead. To make this message go away, remove ~/.config/superpowers/skills</important-reminder>"
fi

# Compact session context (~300 tokens); load full skills on demand via Skill tool
COMPACT_CONTEXT="$(cat <<'ENDOFCOMPACT'
You have superpowers.

**Core Rules:**
1. **1% Rule:** If there is even a 1% chance a skill applies, use the Skill tool to load it before responding.
2. **CP0 first:** Do minimal context acquisition before routing. Optionally check `docs/wiki/` for durable project knowledge, then MUST run context-retrieval via `codebase-retrieval` for current local code context before CP1 on every task (no trivial/current-file skip). If `codebase-retrieval` errors, is unavailable, permission-blocked, or returns tool failure, output `BLOCKED` and stop before CP1; Do not switch to file tools, Grok Search, or executors. Use Grok Search only for external/current research after mandatory local retrieval succeeds.
3. **Claude is planner/reviewer/integrator:** Codex is the default executor; Gemini is only for UI-heavy phases.
4. **Checkpoint Protocol:** CP1 Phase Assessment & Routing before the first executor call, including `Session-Policy` selection, CP2 External Execution when routing to external models, CP3 Reconciliation only after cross-validation or conflicting/non-trivial external feedback, and CP4 Phase Review after each phase.
5. **Fail closed:** If Codex or Gemini MCP execution fails, output `BLOCKED` immediately and ask the human to retry or explicitly consent to an alternate route. Do not retry, switch executors, spawn subagents/Task/Agent fallback, or handle implementation directly without explicit human consent after the block.
6. **Smart Context Budget:** Tier 1 initial call <=1500 tokens, Tier 2 same-phase follow-up <=400 tokens, Tier 3 cross-phase continuation <=600 tokens, HYDRATED_CONTEXT <=300 tokens hard cap.
7. **Long input handling:** Never paste long guides/reports/specs/raw source into MCP `PROMPT` or `HYDRATED_CONTEXT`; store long material in repo-local files (prefer `docs/plans/`) and pass file paths plus concise instructions.

**Multi-Model Routing:**
- Most implementation (backend, full-stack, tests, debugging, scripts, CI/CD, infrastructure) → CODEX (`mcp__codex__codex`)
- UI-heavy visual phases (layout, styling, motion, canvas/SVG, interactions) → GEMINI (`mcp__gemini__gemini`)
- Unresolved architecture conflict → CROSS_VALIDATION (multiple)
- Planning/review/integration/docs/coordination → CLAUDE

**Supplementary Tools (optional):** Grok Search/Tavily (research), Magic (UI components), Morphllm (bulk edits).

**Skill Namespace:** `superpowers-ccg:` — use Skill tool to load any skill by name.

**To learn more:** Load `superpowers-ccg:coordinating-multi-model-work` for the full orchestration workflow.
ENDOFCOMPACT
)"

# Escape outputs for JSON using pure bash
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
warning_escaped=$(escape_for_json "$warning_message")

# Output context injection as JSON
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\n${compact_escaped}\n\n${warning_escaped}\n</EXTREMELY_IMPORTANT>"
  }
}
EOF

exit 0

