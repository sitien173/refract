#!/usr/bin/env bash
# SessionStart hook for superpowers-ccg plugin.

set -euo pipefail

COMPACT_CONTEXT="$(cat <<'ENDOFCOMPACT'
You are Superpowers with Coordinate multi-model work.

In this session, you will be working with external worker agent to implement a plan. 
You will be responsible for coordinating the work of the worker, ensuring that they are following the plan and that they are working together effectively.

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

# Materialize the bundled shared contract (shared/*.md) and the domain-rule
# Only runs in repos that already opt in to this workflow — gated by an
# existing `.agents/`, `docs/plans/`, or `.handover.md` marker. We never
# write into arbitrary cwd's (incl. $HOME) on session start.
should_materialize() {
    [ -d "${PWD}/.agents" ] && return 0
    [ -d "${PWD}/docs/plans" ] && return 0
    shopt -s nullglob
    local h=(docs/plans/*/.handover.md)
    shopt -u nullglob
    [ ${#h[@]} -gt 0 ] && return 0
    return 1
}

shared_version() {
    awk '
        match($0, /ccg-shared-version:[[:space:]]*[^[:space:]>]+/) {
            v = substr($0, RSTART, RLENGTH)
            sub(/^ccg-shared-version:[[:space:]]*/, "", v)
            print v
            exit
        }
    ' "$1" 2>/dev/null || true
}

materialize_shared() {
    local plugin_root src_dir dest_dir template name dest src_ver dest_ver
    plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd || true)"
    [ -n "$plugin_root" ] || return 0
    src_dir="${plugin_root}/shared"
    [ -d "$src_dir" ] || return 0

    dest_dir="${PWD}/.agents/shared"
    shopt -s nullglob
    for template in "$src_dir"/*.md; do
        name="$(basename "$template")"
        dest="${dest_dir}/${name}"
        if [ -f "$dest" ]; then
            src_ver="$(shared_version "$template")"
            dest_ver="$(shared_version "$dest")"
            [ "$src_ver" = "$dest_ver" ] && continue
        fi
        mkdir -p "$dest_dir" 2>/dev/null || true
        cp -f "$template" "$dest" 2>/dev/null || true
    done
    shopt -u nullglob
}

if should_materialize; then
    materialize_shared || true
fi

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\n${compact_escaped}\n</EXTREMELY_IMPORTANT>"
  }
}
EOF

exit 0
