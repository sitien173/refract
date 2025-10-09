#!/usr/bin/env bash
# SessionStart hook for superpowers plugin

# Create data directory
mkdir -p ~/.superpowers

# Output context injection as JSON
# Use double quotes for heredoc to allow variable expansion
cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\nYou have superpowers.\n\nBefore ANY task, search for relevant skills:\n\n${CLAUDE_PLUGIN_ROOT}/skills/getting-started/skills-search PATTERN\n\n**Skills are mandatory when they exist, not optional.**\n\nFailed searches are logged to: ~/.superpowers/search-log.jsonl\n\n**Skills location**: ${CLAUDE_PLUGIN_ROOT}/skills/\n\nCategories:\n- testing/ - TDD, async testing, anti-patterns\n- debugging/ - Systematic debugging, root cause tracing, verification\n- collaboration/ - Brainstorming, planning, code review, parallel agents\n- meta/ - Creating, testing, and contributing skills\n\n**Critical**: Skills exist and you didn't use them = failed task.\n\n**RIGHT NOW, go read**: @${CLAUDE_PLUGIN_ROOT}/skills/getting-started/SKILL.md\n</EXTREMELY_IMPORTANT>"
  }
}
EOF

exit 0
