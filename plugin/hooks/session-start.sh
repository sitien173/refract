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
    "additionalContext": "<EXTREMELY_IMPORTANT>\nYou have superpowers.\n\n**Below is the full content of your 'superpowers:using-superpowers' skill - your introduction to using skills. For all other skills, use the 'Skill' tool:**\n\n${using_superpowers_escaped}\n\n---\n\n**【1%规则 - 强制执行】coordinating-multi-model-work skill：**\n\n**只要任务有 1% 的可能性需要调用外部 MCP tools（Codex MCP/Gemini MCP），你就必须：**\n\n1. **首先使用 Skill 工具读取** `superpowers:coordinating-multi-model-work` skill\n2. **执行检查点评估**（CP1/CP2/CP3）决定是否调用\n3. **如果评估结果需要调用**，则按照协议调用 MCP tools（`mcp__codex__codex` / `mcp__gemini__gemini`）\n4. **如果评估结果不需要调用**，则由 Claude 独立处理\n\n**跳过评估直接调用 = 严重违规**\n**评估后应该调用但忽略不调用 = 严重违规**\n\n**coordinating-multi-model-work skill 完整内容：**\n\n${coordinating_escaped}\n\n${warning_escaped}\n</EXTREMELY_IMPORTANT>"
  }
}
EOF

exit 0
