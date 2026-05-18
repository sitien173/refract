#!/usr/bin/env bash
# SessionStart hook for superpowers-ccg plugin

set -euo pipefail

COMPACT_CONTEXT="$(cat <<'ENDOFCOMPACT'
You have superpowers. Your Role is planner, orchestrator, reviewer, integrator. Use English with tools/models. Make targeted changes. If context insufficient, ask.

**MANDATORY skill load before first Plan or Execute action this session:**
- Call `Skill` tool with `superpowers-ccg:coordinating-multi-model-work` (canonical 3-gate workflow + routing + resume artifacts).
- Call `Skill` tool with `superpowers-ccg:writing-plans` before any plan-writing.
- Call `Skill` tool with `superpowers-ccg:executing-plans` before any phase execution.
- Compact summary below is a pointer only; the Skill body is authoritative.

**Resume-first protocol:**
- If a `<RESUME>` block follows this context, treat it as an active plan signal. Read `.handover.md` and every file listed in `read_first` BEFORE proposing a new plan or executing a phase. Honor cached `SESSION_ID`s in `.sessions.json`.
- If user requests plan/execute work and `docs/plans/<slug>/.handover.md` with `status: ACTIVE` exists for that topic, resume that plan instead of starting a new one.
- Never silently start fresh when an ACTIVE handover exists for the same topic — ask the user if unsure.

**Workflow: 3 gates — Plan → Execute → Review.**

1. **Plan.** New feature / ideation / proposal → run CROSS_VALIDATION first (Codex + Gemini narrow question), reconcile, then plan. Otherwise gather minimum context with whatever tool fits. Define one phase: 2-4 tasks, file set, Done When. Output the `# ROUTE` block.
2. **Execute.** Route by side (no default):
   - Claude — simple tasks Claude can do directly (one-line edits, doc tweaks, rename, clarification).
   - Codex (`mcp__codex__codex`) — **back-side**: backend, API, business logic, database, system, infra, CI/CD, scripts, server-side tests.
   - Gemini (`mcp__gemini__gemini`) — **front-side**: UI, CSS, motion, canvas/SVG, client interactions, multimodal input, large-context UI/doc sweeps.
   - Cross-Validation — new-feature ideation only; reconcile then assign side owner.
   Worker edits files via its own MCP write tools and returns `## FILES MODIFIED`.
3. **Review.** Two sub-steps:
   - (a) Spec: run Done When checks; PASS / PASS_WITH_DEBT / FAIL.
   - (b) Quality scan on `## FILES MODIFIED` (edge cases, error handling, security, naming, duplication, correctness). CRITICAL/HIGH → force FAIL; MEDIUM → downgrade PASS to PASS_WITH_DEBT; LOW noted. Skip for docs-only or trivial Claude direct edits; required for Codex/Gemini phases.
   Output `# REVIEW` with Spec Status, Quality Findings, Final Status.

**Hard rules:**
- MCP failure (timeout, unavailable, session-failed, permission-blocked, prompt too long) → output `BLOCKED`, ask the human. No retry, no executor switch, no Task/Agent fallback without explicit consent.
- Long input (>~8KB / >1500 tokens) → write to a repo file (prefer `docs/plans/`), pass the path. Never paste raw guides/specs/research into the MCP `PROMPT`.
- One phase, one owner, one review. No draft-then-reimplement handoffs.
- After any Codex/Gemini MCP call that returns `SESSION_ID`, write it to `<plan-dir>/.sessions.json`. After any plan-state change, rewrite `<plan-dir>/.handover.md`.

**Skill namespace:** `superpowers-ccg:` — Skill load is mandatory per the directives above, not optional.
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
    local sessions_file codex_state gemini_state
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

    sessions_file="$(dirname "$active_file")/.sessions.json"
    codex_state="absent"
    gemini_state="absent"
    if [ -f "$sessions_file" ]; then
        if grep -Eq '"codex"[[:space:]]*:' "$sessions_file"; then
            if ! grep -Eq '"codex"[[:space:]]*:[[:space:]]*null([[:space:]]*[,}])?' "$sessions_file"; then
                codex_state="present"
            fi
        fi
        if grep -Eq '"gemini"[[:space:]]*:' "$sessions_file"; then
            if ! grep -Eq '"gemini"[[:space:]]*:[[:space:]]*null([[:space:]]*[,}])?' "$sessions_file"; then
                gemini_state="present"
            fi
        fi
    fi

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
