#!/usr/bin/env bash
# SessionStart hook for superpowers plugin

set -euo pipefail

# Run personal superpowers setup
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

# Output context injection as JSON
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\nYou have superpowers.\n\n**Skill tools are at:**\n- find-skills: ${CLAUDE_PLUGIN_ROOT}/scripts/find-skills\n- skill-run: ${CLAUDE_PLUGIN_ROOT}/scripts/skill-run\n\n**RIGHT NOW, go read**: @${CLAUDE_PLUGIN_ROOT}/skills/getting-started/SKILL.md${github_recommendation}\n</EXTREMELY_IMPORTANT>"
  }
}
EOF

exit 0
