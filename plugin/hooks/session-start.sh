#!/usr/bin/env bash
# SessionStart hook for superpowers-ccg plugin

set -euo pipefail

COMPACT_CONTEXT="$(cat <<'ENDOFCOMPACT'
You are planner, orchestrator, reviewer, integrator for the superpowers-ccg plugin. Codex owns back-side, Gemini owns front-side, you handle simple edits.

**Mandatory skill load** (namespace `superpowers-ccg:`) before any Plan or Execute action:
- `coordinating-multi-model-work` — canonical 3-gate workflow, routing, review, resume artifacts. Load first; it is authoritative.
- `writing-plans` — load before authoring a plan.
- `executing-plans` — load before running a phase.

**Resume-first.** If a `<RESUME>` block follows, read `.handover.md` and every file in `read_first` before proposing a new plan or executing a phase. Honor cached `session_refs`. If an `ACTIVE` handover covers the user's topic, resume it — never silently start fresh.
ENDOFCOMPACT
)"

escape_for_json() {
    local input="$1"
    local output=""
    local i char
    for (( i=0; i<${#input}; i++ )); do
        char="${input:$i:1}"
        case "$char" in
            $'\\') output+='\\' ;;
            '"') output+='\"' ;;
            $'\n') output+='\n' ;;
            $'\r') output+='\r' ;;
            $'\t') output+='\t' ;;
            *) output+="$char" ;;
        esac
    done
    printf '%s' "$output"
}

compact_escaped=$(escape_for_json "$COMPACT_CONTEXT")

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

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<EXTREMELY_IMPORTANT>\n${compact_escaped}\n</EXTREMELY_IMPORTANT>${resume_escaped:+\n${resume_escaped}}"
  }
}
EOF

exit 0
