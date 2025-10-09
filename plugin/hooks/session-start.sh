#!/usr/bin/env bash
# SessionStart hook for superpowers plugin

# Create data directory
mkdir -p ~/.superpowers

# Output context injection as JSON
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\nYou have superpowers.\n\n**RIGHT NOW, go read**: @${CLAUDE_PLUGIN_ROOT}/skills/getting-started/SKILL.md\n</EXTREMELY_IMPORTANT>"
  }
}
EOF

exit 0
