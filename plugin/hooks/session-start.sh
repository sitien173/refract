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
3. **Claude is orchestrator-only:** All implementation code goes through external models (Codex/Gemini MCP).
4. **Checkpoint Protocol:** CP1 Task Assessment & Routing before the first Task call, CP2 External Execution when routing to external models, CP3 Reconciliation only after cross-validation or conflicting/non-trivial external feedback, and CP4 Final Spec Review as the last step.
5. **Fail-Closed:** If Routing != CLAUDE and MCP call fails, output BLOCKED (see GATE.md for tiered policy).

**Multi-Model Routing:**
- Backend (API, DB, auth) → CODEX (`mcp__codex__codex`)
- Frontend (UI, styles) → GEMINI (`mcp__gemini__gemini`)
- Backend and systems (API, DB, auth, CI/CD, scripts, infrastructure) → CODEX (`mcp__codex__codex`)
- Full-stack/uncertain → CROSS_VALIDATION (multiple)
- Docs/coordination only → CLAUDE

**Supplementary Tools (optional):** Grok Search/Tavily (research), Sequential-Thinking (complex reasoning), Magic (UI components), Morphllm (bulk edits).

**Skill Namespace:** `superpowers-ccg:` — use Skill tool to load any skill by name.

**To learn more:** Load `superpowers-ccg:using-superpowers` or `superpowers-ccg:coordinating-multi-model-work` for full instructions.
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
