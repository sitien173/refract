#!/usr/bin/env bash
# UserPromptSubmit hook for superpowers-ccg plugin.
# Parses the active docs/plans/*/.handover.md and emits a short
# human-readable summary via systemMessage so the user can see
# where the orchestrator left off each turn.

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

build_summary() {
    local active_file plan current_phase owner next_action read_first
    local codex_val gemini_val codex_state gemini_state

    active_file="$(find_active_handover)"
    if [ -z "$active_file" ] || [ ! -f "$active_file" ]; then
        return 0
    fi

    plan="$(extract_frontmatter_value "$active_file" "plan" || true)"
    current_phase="$(extract_frontmatter_value "$active_file" "current_phase" || true)"
    owner="$(extract_frontmatter_value "$active_file" "owner" || true)"
    next_action="$(extract_section "$active_file" "next_action" | awk 'NF{print; exit}')"
    read_first="$(extract_section "$active_file" "read_first" | awk 'NF')"

    codex_val="$(extract_session_ref "$active_file" "codex")"
    gemini_val="$(extract_session_ref "$active_file" "gemini")"

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

if [ "${1:-}" = "--codex" ] || [ "${1:-}" = "--qoder" ]; then
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
