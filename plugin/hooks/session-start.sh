#!/usr/bin/env bash
# SessionStart hook for superpowers plugin

set -euo pipefail

# Set SUPERPOWERS_SKILLS_ROOT environment variable
export SUPERPOWERS_SKILLS_ROOT="${HOME}/.config/superpowers/skills"

# Run skills initialization script (handles clone/fetch/notification)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
init_output=$("${PLUGIN_ROOT}/lib/initialize-skills.sh" 2>&1 || echo "")

# Run personal superpowers setup
setup_output=$("${SCRIPT_DIR}/setup-personal-superpowers.sh" 2>&1 || echo "setup_failed=true")

# Use same directory resolution as setup script
SUPERPOWERS_DIR="${PERSONAL_SUPERPOWERS_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/superpowers}"

# Check if GitHub CLI is available and setup succeeded
github_recommendation=""
if echo "$setup_output" | grep -q "github_cli_available=true"; then
    if [[ ! -d "$SUPERPOWERS_DIR/.git" ]]; then
        # This should not happen, but handle gracefully
        github_recommendation=""
    else
        # Check if remote already exists
        if ! (cd "$SUPERPOWERS_DIR" && git remote get-url origin &>/dev/null); then
            github_recommendation="\n\n💡 Want to share your personal skills on GitHub? Superpowers are best when everyone can learn from them! I can create a 'personal-superpowers' repo for you."
        fi
    fi
elif echo "$setup_output" | grep -q "setup_failed=true"; then
    github_recommendation="\n\n⚠️  Personal superpowers setup encountered an issue. Please file a bug at https://github.com/obra/superpowers/issues"
fi

# Run find-skills to show all available skills
find_skills_output=$("${SUPERPOWERS_SKILLS_ROOT}/skills/using-skills/find-skills" 2>&1 || echo "Error running find-skills")

# Read using-skills content (renamed from getting-started)
using_skills_content=$(cat "${SUPERPOWERS_SKILLS_ROOT}/skills/using-skills/SKILL.md" 2>&1 || echo "Error reading using-skills")

# Escape outputs for JSON
init_escaped=$(echo "$init_output" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | awk '{printf "%s\\n", $0}')
find_skills_escaped=$(echo "$find_skills_output" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | awk '{printf "%s\\n", $0}')
using_skills_escaped=$(echo "$using_skills_content" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | awk '{printf "%s\\n", $0}')

# Build initialization output message if present
init_message=""
if [ -n "$init_escaped" ]; then
    init_message="${init_escaped}\n\n"
fi

# Output context injection as JSON
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\nYou have superpowers.\n\n${init_message}**The content below is from skills/using-skills/SKILL.md - your introduction to using skills:**\n\n${using_skills_escaped}\n\n**Tool paths (use these when you need to search for or run skills):**\n- find-skills: ${SUPERPOWERS_SKILLS_ROOT}/skills/using-skills/find-skills\n- skill-run: ${SUPERPOWERS_SKILLS_ROOT}/skills/using-skills/skill-run\n\n**Available skills (output of find-skills):**\n\n${find_skills_escaped}${github_recommendation}\n</EXTREMELY_IMPORTANT>"
  }
}
EOF

exit 0
