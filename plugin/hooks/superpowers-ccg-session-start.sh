#!/usr/bin/env bash
# SessionStart hook for superpowers-ccg plugin

set -euo pipefail

COMPACT_CONTEXT="$(cat <<'ENDOFCOMPACT'
superpowers-ccg: you plan, route, review, and do simple edits; Codex owns back-side, Gemini front-side. Before any Plan/Execute/Review action, load the `superpowers-ccg:coordinating-multi-model-work` skill first — it is the authoritative 3-gate workflow, routing, review, and resume spec. Resume-first: if a `<RESUME>` block follows, read `.handover.md` and every `read_first` file and honor cached `session_refs` before proposing or executing anything; if an `ACTIVE` handover covers the user's topic, resume it — never silently start fresh.
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

# Materialize the bundled shared contract (shared/*.md) into the consuming
# project's .agents/shared/. Deterministic, version-stamped copy. Writes nothing
# to stdout (stdout is reserved for the SessionStart JSON contract). Every step
# is guarded so a copy failure never suppresses the resume context below.
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

materialize_shared || true

extract_frontmatter_value() {
    local file="$1"
    local key="$2"
    awk -v target="$key" '
        BEGIN { in_frontmatter = 0 }
        /^---[[:space:]]*$/ {
            if (in_frontmatter == 0) {
                in_frontmatter = 1
                next
            }
            if (in_frontmatter == 1) {
                exit
            }
        }
        in_frontmatter == 1 {
            line = $0
            sub(/\r$/, "", line)
            if (match(line, /^[[:space:]]*[^:#]+[[:space:]]*:/)) {
                k = substr(line, RSTART, RLENGTH)
                sub(/:.*/, "", k)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", k)
                if (k == target) {
                    v = line
                    sub(/^[^:]*:[[:space:]]*/, "", v)
                    sub(/[[:space:]]*#.*/, "", v)
                    gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
                    print v
                    exit
                }
            }
        }
    ' "$file"
}

build_resume_context() {
    local handovers active active_file status
    local plan current_phase owner next_action read_first
    local codex_state gemini_state codex_val gemini_val
    local files_list

    shopt -s nullglob
    handovers=(docs/plans/*/.handover.md)
    shopt -u nullglob

    if [ ${#handovers[@]} -eq 0 ]; then
        return 0
    fi

    active=()
    for candidate in "${handovers[@]}"; do
        status="$(extract_frontmatter_value "$candidate" "status" || true)"
        if [ "$status" = "ACTIVE" ]; then
            active+=("$candidate")
        fi
    done

    if [ ${#active[@]} -eq 0 ]; then
        return 0
    fi

    active_file="$(ls -1t -- "${active[@]}" 2>/dev/null | head -n 1 || true)"
    if [ -z "$active_file" ] || [ ! -f "$active_file" ]; then
        return 0
    fi

    plan="$(extract_frontmatter_value "$active_file" "plan" || true)"
    current_phase="$(extract_frontmatter_value "$active_file" "current_phase" || true)"
    owner="$(extract_frontmatter_value "$active_file" "owner" || true)"

    next_action="$(
        awk '
            /^##[[:space:]]+next_action[[:space:]]*$/ { in_section = 1; next }
            /^##[[:space:]]+/ { if (in_section) exit }
            in_section {
                line = $0
                sub(/\r$/, "", line)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
                if (line != "") {
                    print line
                    exit
                }
            }
        ' "$active_file" 2>/dev/null || true
    )"

    read_first="$(
        awk '
            /^##[[:space:]]+read_first[[:space:]]*$/ { in_section = 1; next }
            /^##[[:space:]]+/ { if (in_section) exit }
            in_section {
                line = $0
                sub(/\r$/, "", line)
                print line
            }
        ' "$active_file" 2>/dev/null || true
    )"

    codex_state="absent"
    gemini_state="absent"
    codex_val="$(awk '
        BEGIN{fm=0;refs=0}
        /^---[[:space:]]*$/{if(fm==0){fm=1;next}else exit}
        fm&&/^session_refs[[:space:]]*:/{refs=1;next}
        refs&&/^[[:space:]]+codex[[:space:]]*:/{
            v=$0;sub(/^[^:]*:[[:space:]]*/,"",v);sub(/[[:space:]]*#.*/,"",v)
            gsub(/^[[:space:]]+|[[:space:]]+$/,"",v);print v;exit}
        refs&&/^[^[:space:]]/{exit}
    ' "$active_file" 2>/dev/null || true)"
    gemini_val="$(awk '
        BEGIN{fm=0;refs=0}
        /^---[[:space:]]*$/{if(fm==0){fm=1;next}else exit}
        fm&&/^session_refs[[:space:]]*:/{refs=1;next}
        refs&&/^[[:space:]]+gemini[[:space:]]*:/{
            v=$0;sub(/^[^:]*:[[:space:]]*/,"",v);sub(/[[:space:]]*#.*/,"",v)
            gsub(/^[[:space:]]+|[[:space:]]+$/,"",v);print v;exit}
        refs&&/^[^[:space:]]/{exit}
    ' "$active_file" 2>/dev/null || true)"
    [ -n "$codex_val" ] && [ "$codex_val" != "null" ] && codex_state="present"
    [ -n "$gemini_val" ] && [ "$gemini_val" != "null" ] && gemini_state="present"

    cat <<EOF
<RESUME>
Active plan: ${plan}
Current phase: ${current_phase}
Owner: ${owner}
Next action: ${next_action}
Read first:
${read_first}
Sessions: codex=${codex_state}, gemini=${gemini_state}
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
