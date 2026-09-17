#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
hook="${repo_root}/hooks/superpowers-ccg-session-start.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

validate_output() {
    HOOK_OUTPUT="$1" EXPECTED_ROOT="$2" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["HOOK_OUTPUT"])
specific = payload["hookSpecificOutput"]
assert specific["hookEventName"] == "SessionStart"
context = specific["additionalContext"]
assert os.environ["EXPECTED_ROOT"] in context
assert "coordinating-multi-model-work" in context
PY
}

mkdir -p "$tmp/repo"
output="$(cd "$tmp/repo" && "$hook")"
validate_output "$output" "$repo_root"
test -z "$(ls -A "$tmp/repo")"

plugin_with_spaces="$tmp/plugin root"
mkdir -p "$plugin_with_spaces/hooks" "$plugin_with_spaces/shared"
cp "$hook" "$plugin_with_spaces/hooks/"
output="$("$plugin_with_spaces/hooks/superpowers-ccg-session-start.sh")"
validate_output "$output" "$plugin_with_spaces"

printf 'session-start tests passed\n'
