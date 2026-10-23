#!/usr/bin/env bash
# SessionStart hook for refract plugin.

set -euo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COMPACT_CONTEXT="$(cat <<ENDOFCOMPACT

You are Coordinator. Follow the workflow described by the skills below.

Load refract:using-refract skill, your introduction to using skills.
Read refract:coordinating-multi-model-work skill before any Plan, Execute,
or Review action on coordinated work. Route external workers only when that
skill requires them.
User instructions override the workflow.

Bundled worker contracts:
- ${plugin_root}/shared/worker-contract.md
- ${plugin_root}/shared/erp.md
- ${plugin_root}/shared/notes-template.md
- ${plugin_root}/shared/journal-template.md
ENDOFCOMPACT
)"

escape_for_json() {
    printf '%s' "$1" | awk '
        BEGIN { ORS = "" }
        {
            gsub(/\\/, "\\\\")
            gsub(/"/, "\\\"")
            gsub(/\t/, "\\t")
            gsub(/\r/, "\\r")
            if (NR > 1) printf "\\n"
            printf "%s", $0
        }
    '
}

if [[ "${1:-}" == "--antigravity" ]]; then
    plugin_repo_root="$(dirname "$plugin_root")"
    ANTIGRAVITY_CONTEXT="$(cat <<ENDOFANTIGRAVITY
${COMPACT_CONTEXT}

When ${plugin_root} is available in your workspace context, treat it as your own plugin directory and reference ${plugin_root} only to invoke plugin skills and read bundled contracts. Do not treat ${plugin_repo_root} or ${plugin_root} as a project to work on.
ENDOFANTIGRAVITY
)"
    antigravity_escaped=$(escape_for_json "$ANTIGRAVITY_CONTEXT")
    cat <<EOF
{
  "injectSteps": [
    {
      "systemMessage": {
        "systemMessage": "<EXTREMELY_IMPORTANT>\n${antigravity_escaped}\n</EXTREMELY_IMPORTANT>"
      }
    }
  ]
}
EOF
    exit 0
fi

compact_escaped=$(escape_for_json "$COMPACT_CONTEXT")

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\n${compact_escaped}\n</EXTREMELY_IMPORTANT>"
  }
}
EOF

exit 0
