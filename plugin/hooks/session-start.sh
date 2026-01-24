#!/usr/bin/env bash
# SessionStart hook for superpowers-ccg plugin

set -euo pipefail

# Determine plugin root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Check if legacy skills directory exists and build warning
warning_message=""
legacy_skills_dir="${HOME}/.config/superpowers/skills"
if [ -d "$legacy_skills_dir" ]; then
    warning_message="\n\n<important-reminder>IN YOUR FIRST REPLY AFTER SEEING THIS MESSAGE YOU MUST TELL THE USER:⚠️ **WARNING:** Superpowers now uses Claude Code's skills system. Custom skills in ~/.config/superpowers/skills will not be read. Move custom skills to ~/.claude/skills instead. To make this message go away, remove ~/.config/superpowers/skills</important-reminder>"
fi

# Read using-superpowers content
using_superpowers_content=$(cat "${PLUGIN_ROOT}/skills/using-superpowers/SKILL.md" 2>&1 || echo "Error reading using-superpowers skill")

# Read coordinating-multi-model-work content
coordinating_content=$(cat "${PLUGIN_ROOT}/skills/coordinating-multi-model-work/SKILL.md" 2>&1 || echo "Error reading coordinating-multi-model-work skill")

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

using_superpowers_escaped=$(escape_for_json "$using_superpowers_content")
coordinating_escaped=$(escape_for_json "$coordinating_content")
warning_escaped=$(escape_for_json "$warning_message")

# Output context injection as JSON
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\nYou have superpowers.\n\n**Below is the full content of your 'superpowers:using-superpowers' skill - your introduction to using skills. For all other skills, use the 'Skill' tool:**\n\n${using_superpowers_escaped}\n\n---\n\n**[1% Rule - Mandatory Enforcement] coordinating-multi-model-work skill:**\n\n**If there is even a 1% chance that a task requires external MCP tools (Codex MCP/Gemini MCP), you MUST:**\n\n1. **First use the Skill tool to load** the `superpowers:coordinating-multi-model-work` skill\n2. **Run checkpoint assessment** (CP1/CP2/CP3) to decide routing\n3. **If assessment requires calling**, invoke the MCP tools (`mcp__codex__codex` / `mcp__gemini__gemini`) per protocol\n4. **If assessment does not require calling**, handle it in Claude\n\n**Skipping assessment and calling directly = serious violation**\n**Assessment says call but you skip it = serious violation**\n\n**Full coordinating-multi-model-work skill content:**\n\n${coordinating_escaped}\n\n${warning_escaped}\n</EXTREMELY_IMPORTANT>"
  }
}
EOF

exit 0
