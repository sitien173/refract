#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
hook="${repo_root}/hooks/refract-session-start.sh"
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
assert "Do not treat" not in context
PY
}

validate_antigravity_output() {
    HOOK_OUTPUT="$1" EXPECTED_ROOT="$2" python3 - <<'PY'
import json
import os
import pathlib

payload = json.loads(os.environ["HOOK_OUTPUT"])
steps = payload["injectSteps"]
assert len(steps) == 1
context = steps[0]["systemMessage"]["systemMessage"]
expected_root = os.environ["EXPECTED_ROOT"]
expected_repo_root = str(pathlib.Path(expected_root).parent)
assert expected_root in context
assert "coordinating-multi-model-work" in context
assert f"reference {expected_root} only to invoke plugin skills" in context
assert f"Do not treat {expected_repo_root} or {expected_root} as a project to work on." in context
PY
}

mkdir -p "$tmp/repo"
output="$(cd "$tmp/repo" && "$hook")"
validate_output "$output" "$repo_root"
agy_output="$(cd "$tmp/repo" && "$hook" --antigravity)"
validate_antigravity_output "$agy_output" "$repo_root"
test -z "$(ls -A "$tmp/repo")"

plugin_with_spaces="$tmp/plugin root"
mkdir -p "$plugin_with_spaces/hooks" "$plugin_with_spaces/shared"
cp "$hook" "$plugin_with_spaces/hooks/"
output="$("$plugin_with_spaces/hooks/refract-session-start.sh")"
validate_output "$output" "$plugin_with_spaces"
agy_output="$("$plugin_with_spaces/hooks/refract-session-start.sh" --antigravity)"
validate_antigravity_output "$agy_output" "$plugin_with_spaces"

printf 'session-start tests passed\n'
