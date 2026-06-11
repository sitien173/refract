#!/usr/bin/env bash
# UserPromptSubmit hook for superpowers-ccg plugin.
# Parses the active docs/plans/*/.handover.md and emits a short
# human-readable summary via systemMessage so the user can see
# where the orchestrator left off each turn.

set -euo pipefail

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

extract_frontmatter_value() {
    local file="$1"
    local key="$2"
    awk -v target="$key" '
        BEGIN { in_frontmatter = 0 }
        /^---[[:space:]]*$/ {
            if (in_frontmatter == 0) { in_frontmatter = 1; next }
            if (in_frontmatter == 1) { exit }
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

extract_section() {
    local file="$1"
    local section="$2"
    awk -v target="$section" '
        $0 ~ "^##[[:space:]]+" target "[[:space:]]*$" { in_section = 1; next }
        /^##[[:space:]]+/ { if (in_section) exit }
        in_section {
            line = $0
            sub(/\r$/, "", line)
            print line
        }
    ' "$file" 2>/dev/null || true
}

build_summary() {
    local handovers active active_file status
    local plan current_phase owner next_action read_first
    local codex_val gemini_val codex_state gemini_state

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

    next_action="$(extract_section "$active_file" "next_action" | awk 'NF{print; exit}')"
    read_first="$(extract_section "$active_file" "read_first" | awk 'NF')"

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

    codex_state="absent"
    gemini_state="absent"
    [ -n "$codex_val" ] && [ "$codex_val" != "null" ] && codex_state="present"
    [ -n "$gemini_val" ] && [ "$gemini_val" != "null" ] && gemini_state="present"

    {
        echo "superpowers-ccg | active handover: ${active_file}"
        [ -n "$plan" ]          && echo "  plan          : ${plan}"
        [ -n "$current_phase" ] && echo "  current phase : ${current_phase}"
        [ -n "$owner" ]         && echo "  owner         : ${owner}"
        [ -n "$next_action" ]   && echo "  next action   : ${next_action}"
        echo "  sessions      : codex=${codex_state}, gemini=${gemini_state}"
        if [ -n "$read_first" ]; then
            echo "  read first:"
            printf '%s\n' "$read_first" | sed 's/^/    /'
        fi
    }
}

summary="$(build_summary || true)"

if [ -z "$summary" ]; then
    exit 0
fi

escaped="$(escape_for_json "$summary")"

if [ "${1:-}" = "--codex" ]; then
    cat <<EOF
{
  "systemMessage": "${escaped}",
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "${escaped}"
  }
}
EOF
    exit 0
fi

cat <<EOF
{
  "systemMessage": "${escaped}",
  "suppressOutput": true
}
EOF

exit 0
