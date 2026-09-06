#!/usr/bin/env bash
# SessionStart hook for superpowers-ccg plugin.

set -euo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COMPACT_CONTEXT="$(cat <<ENDOFCOMPACT

You have superpowers. You as a coordinator plan work through superpowers-ccg.

Load superpowers-ccg:using-superpowers skill - your introduction to using skills. 
Read superpowers-ccg:coordinating-multi-model-work skill before any Plan, Execute,
or Review action. Route external workers only when that skill requires them.
User instructions override the workflow.

Bundled worker contracts:
- ${plugin_root}/shared/worker-contract.md
- ${plugin_root}/shared/erp.md
- ${plugin_root}/shared/notes-template.md
- ${plugin_root}/shared/journal-template.md
- ${plugin_root}/shared/backlog-contract.md
- ${plugin_root}/shared/closeout-template.md
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
