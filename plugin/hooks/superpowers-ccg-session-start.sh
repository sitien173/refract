#!/usr/bin/env bash
# SessionStart hook for superpowers-ccg plugin.

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

COMPACT_CONTEXT="$(cat <<'ENDOFCOMPACT'
You are Superpowers with Coordinate multi-model work.

You Plan, route, review, and handle simple edits.

Codex owns back-side work.
agy owns front-side work.

Behavioral rules for this session:
- Think before acting. Read existing files before writing.
- Be concise in output but thorough in reasoning.
- Prefer editing over rewriting whole files.
- Do not re-read files already read unless file may have changed.
- Execute tool calls sequentially, not in parallel. Wait for each tool result before making the next tool call.
- No sycophantic openers or closing fluff.
- Keep solutions simple and direct.
- User instructions always override these rules.

On first use, load this skill:

```text
superpowers-ccg:coordinating-multi-model-work
```

That skill is the authoritative source for:

* 3-gate workflow
* routing rules
* review rules
* resume behavior

Resume-first rule:

If a `<RESUME>` block is present:

1. Read `.handover.md`.
2. Read every file listed in `read_first`.
3. Reuse cached `session_refs`.
4. If the active handover matches the user’s topic, resume it.
5. Never silently start a new plan when a matching active handover exists.
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
# files (BACKEND.md / FRONTEND.md) into the consuming project's .agents/.
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

materialize_domain_rules() {
    local plugin_root dest_dir template name dest src_ver dest_ver
    plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd || true)"
    [ -n "$plugin_root" ] || return 0

    dest_dir="${PWD}/.agents"
    for name in BACKEND.md FRONTEND.md; do
        template="${plugin_root}/${name}"
        [ -f "$template" ] || continue
        dest="${dest_dir}/${name}"
        if [ -f "$dest" ]; then
            src_ver="$(shared_version "$template")"
            dest_ver="$(shared_version "$dest")"
            [ "$src_ver" = "$dest_ver" ] && continue
        fi
        mkdir -p "$dest_dir" 2>/dev/null || true
        cp -f "$template" "$dest" 2>/dev/null || true
    done
}

if should_materialize; then
    materialize_shared || true
    materialize_domain_rules || true
fi

build_resume_context() {
    local active_file plan current_phase owner next_action read_first
    local codex_state agy_state codex_val agy_val
    active_file="$(find_active_handover)"
    if [ -z "$active_file" ] || [ ! -f "$active_file" ]; then
        return 0
    fi

    plan="$(extract_frontmatter_value "$active_file" "plan" || true)"
    current_phase="$(extract_frontmatter_value "$active_file" "current_phase" || true)"
    owner="$(extract_frontmatter_value "$active_file" "owner" || true)"
    next_action="$(extract_section "$active_file" "next_action" | awk 'NF{print; exit}')"
    read_first="$(extract_section "$active_file" "read_first")"

    codex_state="absent"
    agy_state="absent"
    codex_val="$(extract_session_ref "$active_file" "codex")"
    agy_val="$(extract_session_ref "$active_file" "agy")"
    [ -n "$codex_val" ] && [ "$codex_val" != "null" ] && codex_state="present"
    [ -n "$agy_val" ] && [ "$agy_val" != "null" ] && agy_state="present"

    cat <<EOF
<RESUME>
Active plan: ${plan}
Current phase: ${current_phase}
Owner: ${owner}
Next action: ${next_action}
Read first:
${read_first}
Sessions: codex=${codex_state}, agy=${agy_state}
</RESUME>
EOF
}

resume_context="$(build_resume_context || true)"
resume_escaped=""
if [ -n "$resume_context" ]; then
    resume_escaped="$(escape_for_json "$resume_context")"
fi

if [ "${1:-}" = "--qoder" ]; then
    cat <<EOF
{
  "systemMessage": "<EXTREMELY_IMPORTANT>\n${compact_escaped}\n</EXTREMELY_IMPORTANT>${resume_escaped:+\n${resume_escaped}}",
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "<EXTREMELY_IMPORTANT>\n${compact_escaped}\n</EXTREMELY_IMPORTANT>${resume_escaped:+\n${resume_escaped}}"
  }
}
EOF
    exit 0
fi

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\n${compact_escaped}\n</EXTREMELY_IMPORTANT>${resume_escaped:+\n${resume_escaped}}"
  }
}
EOF

exit 0
