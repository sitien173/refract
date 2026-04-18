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
2. **CP0 first:** Do minimal context acquisition before routing. Use Auggie for full local codebase context retrieval, and use Grok Search only for external/current knowledge or research.
3. **Claude is planner/reviewer/integrator:** Codex is the default executor; Gemini is only for UI-heavy phases.
4. **Checkpoint Protocol:** CP1 Phase Assessment & Routing before the first executor call, including `Session-Policy` selection, CP2 External Execution when routing to external models, CP3 Reconciliation only after cross-validation or conflicting/non-trivial external feedback, and CP4 Phase Review after each phase.
5. **Fallback:** If Gemini fails once, fall back to Codex or Claude-code. If Codex fails, retry once, then fall back to Claude-code/Sonnet. Permission-blocked stays BLOCKED.
6. **Smart Context Budget:** Tier 1 initial call <=1500 tokens, Tier 2 same-phase follow-up <=400 tokens, Tier 3 cross-phase continuation <=600 tokens, HYDRATED_CONTEXT <=300 tokens hard cap.

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
