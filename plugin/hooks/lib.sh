#!/usr/bin/env bash
# Shared helpers for the superpowers-ccg session-start and user-prompt-submit
# hooks. Sourced via:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

# JSON-escape a string. Handles a wider range of control characters than
# the previous per-hook implementation so a stray \x1b (ANSI escape) or
# other C0 byte in handover frontmatter does not produce invalid JSON.
escape_for_json() {
    LC_ALL=C printf '%s' "$1" | awk '
        BEGIN { ORS = "" }
        function ctrl(c,   v) {
            v = ord[c]
            return sprintf("\\u%04x", v)
        }
        BEGIN {
            for (i = 0; i < 256; i++) ord[sprintf("%c", i)] = i
        }
        {
            line = $0
            out = ""
            n = length(line)
            for (i = 1; i <= n; i++) {
                c = substr(line, i, 1)
                v = ord[c]
                if (c == "\\")      out = out "\\\\"
                else if (c == "\"") out = out "\\\""
                else if (c == "\t") out = out "\\t"
                else if (c == "\r") out = out "\\r"
                else if (c == "\b") out = out "\\b"
                else if (c == "\f") out = out "\\f"
                else if (v < 32)    out = out sprintf("\\u%04x", v)
                else                out = out c
            }
            if (NR > 1) printf "\\n"
            printf "%s", out
        }
    '
}

# Extract a YAML-style key from the frontmatter of a markdown file. Only
# strips trailing comments when ' #' appears after the value, so values
# containing '#' (e.g. URLs, anchors) are preserved.
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
                    # Strip trailing comment only when preceded by whitespace.
                    sub(/[[:space:]]+#.*/, "", v)
                    gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
                    print v
                    exit
                }
            }
        }
    ' "$file"
}

# Extract a `session_refs.<backend>` value from frontmatter.
extract_session_ref() {
    local file="$1"
    local backend="$2"
    awk -v target="$backend" '
        BEGIN { fm = 0; refs = 0 }
        /^---[[:space:]]*$/ { if (fm == 0) { fm = 1; next } else exit }
        fm && /^session_refs[[:space:]]*:/ { refs = 1; next }
        refs && /^[[:space:]]+[A-Za-z0-9_-]+[[:space:]]*:/ {
            line = $0
            key = line
            sub(/^[[:space:]]+/, "", key)
            sub(/[[:space:]]*:.*/, "", key)
            if (key == target) {
                v = line
                sub(/^[^:]*:[[:space:]]*/, "", v)
                sub(/[[:space:]]+#.*/, "", v)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
                print v
                exit
            }
        }
        refs && /^[^[:space:]]/ { exit }
    ' "$file"
}

# Extract the body of a `## <section>` section from a markdown file.
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

# Find the most recently modified ACTIVE handover under docs/plans.
# Prints the path, or nothing if none exists.
find_active_handover() {
    local candidate status
    local -a active=()
    shopt -s nullglob
    local -a handovers=(docs/plans/*/.handover.md)
    shopt -u nullglob
    [ ${#handovers[@]} -eq 0 ] && return 0
    for candidate in "${handovers[@]}"; do
        status="$(extract_frontmatter_value "$candidate" "status" || true)"
        [ "$status" = "ACTIVE" ] && active+=("$candidate")
    done
    [ ${#active[@]} -eq 0 ] && return 0
    ls -1t -- "${active[@]}" 2>/dev/null | head -n 1 || true
}
