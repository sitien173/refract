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
2. **Claude is orchestrator-only:** All implementation code goes through external models (Codex/Gemini/Cursor MCP).
3. **Checkpoint Protocol:** CP1 before first Task call, CP3 before claiming completion.
4. **Fail-Closed:** If Routing != CLAUDE and MCP call fails, output BLOCKED (see GATE.md for tiered policy).

**Multi-Model Routing:**
- Backend (API, DB, auth) → CODEX (`mcp__codex__codex`)
- Frontend (UI, styles) → GEMINI (`mcp__gemini__gemini`)
- DevOps (CI/CD, scripts, infrastructure) → CURSOR (`mcp__cursor__cursor`)
- Full-stack/uncertain → CROSS_VALIDATION (multiple)
- Docs/coordination only → CLAUDE

**Supplementary Tools (optional):** Tavily (research), Sequential-Thinking (complex reasoning), Serena (semantic code), Magic (UI components), Morphllm (bulk edits). See `skills/shared/supplementary-tools.md`.

**Skill Namespace:** `superpowers-cccg:` — use Skill tool to load any skill by name.

**To learn more:** Load `superpowers-cccg:using-superpowers` or `superpowers-cccg:coordinating-multi-model-work` for full instructions.
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
