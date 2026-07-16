#!/usr/bin/env bash
# SessionStart hook for superpowers-ccg plugin.

set -euo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

COMPACT_CONTEXT="$(cat <<ENDOFCOMPACT
Coordinate plan work through superpowers-ccg.

Load superpowers-ccg:coordinating-multi-model-work before any Plan, Execute,
or Review action. Route external workers only when that skill requires them.
User instructions override the workflow.

OpenMCP uses durable project jobs. Resume active work from the project jobs
resource before resolving new routing. Route from task templates.
Chooses configured nicknames and stable execution roles. Existing phase chains
keep stored routing. Use compact waits. Never expose provider sessions.

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
