#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
hook="${repo_root}/hooks/refract-session-start.py"
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
assert "the `refract` `list` tool" in context
assert "mcp__" not in context
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
assert "the `refract` `list` tool" in context
assert "mcp__" not in context
PY
}

# Stub refract so the hook never touches a real daemon.
mkdir -p "$tmp/bin" "$tmp/refract-home"
cat > "$tmp/bin/refract" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$REFRACT_STUB_LOG"
[ "$1" != update ] || sleep "${REFRACT_STUB_UPDATE_SLEEP:-0}"
[ "$1" != status ] || exit "${REFRACT_STUB_STATUS:-0}"
SH
chmod +x "$tmp/bin/refract"
# Opt-out variables inherited from the caller would hide the behavior under test.
unset REFRACT_DISABLE REFRACT_NO_UPDATE_CHECK REFRACT_JOB_ID
export PATH="$tmp/bin:$PATH" REFRACT_HOME="$tmp/refract-home" REFRACT_STUB_LOG="$tmp/calls"

# seed_cache <home> <available> <version-json> <commit-json> <age-seconds>
seed_cache() {
    mkdir -p "$1"
    python3 - "$@" <<'PY'
import json
import sys
import time

home, available, version, commit, age = sys.argv[1:]
payload = {
    "schema": 1,
    "checked_at": time.time() - float(age),
    "update_available": available == "true",
    "latest_version": json.loads(version),
    "latest_commit": json.loads(commit),
    "components": [],
}
with open(f"{home}/update-check.json", "w") as f:
    json.dump(payload, f)
PY
}
# A fresh cache with no update keeps the daemon-only call log of the cases below.
seed_cache "$REFRACT_HOME" false null null 0

validate_pi_output() {
    HOOK_OUTPUT="$1" EXPECTED_ROOT="$2" python3 - <<'PY'
import json
import os

context = json.loads(os.environ["HOOK_OUTPUT"])["hookSpecificOutput"]["additionalContext"]
assert os.environ["EXPECTED_ROOT"] in context
assert "Load using-refract skill" in context
assert "Read coordinating-multi-model-work skill" in context
assert "the `refract` `list` tool" in context
assert "refract:" not in context
assert "mcp__" not in context
PY
}

mkdir -p "$tmp/repo"
output="$(cd "$tmp/repo" && python3 "$hook")"
validate_output "$output" "$repo_root"
agy_output="$(cd "$tmp/repo" && python3 "$hook" --antigravity)"
validate_antigravity_output "$agy_output" "$repo_root"
pi_output="$(cd "$tmp/repo" && python3 "$hook" --pi)"
validate_pi_output "$pi_output" "$repo_root"
test -z "$(ls -A "$tmp/repo")"

plugin_with_spaces="$tmp/plugin root"
mkdir -p "$plugin_with_spaces/hooks" "$plugin_with_spaces/shared"
cp "$hook" "$plugin_with_spaces/hooks/"
output="$(python3 "$plugin_with_spaces/hooks/refract-session-start.py")"
validate_output "$output" "$plugin_with_spaces"
agy_output="$(python3 "$plugin_with_spaces/hooks/refract-session-start.py" --antigravity)"
validate_antigravity_output "$agy_output" "$plugin_with_spaces"

# A running daemon is left alone.
: > "$tmp/calls"
REFRACT_STUB_STATUS=0 python3 "$hook" > /dev/null
test "$(cat "$tmp/calls")" = "status"

# A stopped daemon is started in the background, for both hook variants.
for flag in "" --antigravity --pi; do
    : > "$tmp/calls"
    output="$(REFRACT_STUB_STATUS=1 python3 "$hook" $flag)"
    case "$flag" in
        --antigravity) validate_antigravity_output "$output" "$repo_root" ;;
        --pi) validate_pi_output "$output" "$repo_root" ;;
        *) validate_output "$output" "$repo_root" ;;
    esac
    for _ in $(seq 50); do grep -qx serve "$tmp/calls" && break; sleep 0.1; done
    test "$(cat "$tmp/calls")" = "$(printf 'status\nserve')"
done

# REFRACT_DISABLE skips the daemon and tells the agent to ignore Refract.
for flag in "" --antigravity --pi; do
    for value in 1 TRUE yes; do
        : > "$tmp/calls"
        output="$(REFRACT_DISABLE=$value REFRACT_STUB_STATUS=1 python3 "$hook" $flag)"
        HOOK_OUTPUT="$output" PI_FLAG="$flag" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["HOOK_OUTPUT"])
if "injectSteps" in payload:
    context = payload["injectSteps"][0]["systemMessage"]["systemMessage"]
else:
    context = payload["hookSpecificOutput"]["additionalContext"]
assert "Refract is disabled for this session" in context
assert "Coordinator" not in context
assert "any tool of the `refract` MCP server" in context
assert "mcp__" not in context
PY
        test ! -s "$tmp/calls"
    done
done
output="$(REFRACT_DISABLE=0 python3 "$hook")"
validate_output "$output" "$repo_root"

# Without refract on PATH the hook still emits its context.
output="$(PATH="$(dirname "$(command -v python3)")" python3 "$hook")"
validate_output "$output" "$repo_root"

# A fresh cache with an update gives the notice: systemMessage in Claude mode only.
check_notice() {
    HOOK_OUTPUT="$1" MODE="$2" LABEL="$3" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["HOOK_OUTPUT"])
mode, label = os.environ["MODE"], os.environ["LABEL"]
if mode == "--antigravity":
    assert len(payload["injectSteps"]) == 1
    context = payload["injectSteps"][0]["systemMessage"]["systemMessage"]
    assert "systemMessage" not in payload
else:
    context = payload["hookSpecificOutput"]["additionalContext"]
line = f"{label} is available; run refract update. Tell the user once. Do not run refract update yourself."
assert context.endswith(f"{line}\n</EXTREMELY_IMPORTANT>"), context
if mode == "":
    assert payload["systemMessage"] == f"{label} is available. Run: refract update", payload
else:
    assert "systemMessage" not in payload
PY
}
check_no_notice() {
    HOOK_OUTPUT="$1" python3 - <<'PY'
import json
import os

out = os.environ["HOOK_OUTPUT"]
payload = json.loads(out)
assert "systemMessage" not in payload
assert "is available" not in out
PY
}

notice_home="$tmp/notice-home"
sha=0123456789abcdef0123456789abcdef01234567
for flag in "" --antigravity --pi; do
    seed_cache "$notice_home" true '"2.6.0"' null 10
    output="$(REFRACT_HOME="$notice_home" python3 "$hook" $flag)"
    check_notice "$output" "$flag" "Refract 2.6.0"
done

# Label rules: valid version, then valid commit, then neither.
seed_cache "$notice_home" true null "\"$sha\"" 10
output="$(REFRACT_HOME="$notice_home" python3 "$hook")"
check_notice "$output" "" "Refract commit 0123456"
seed_cache "$notice_home" true '"2.6"' '"not-a-sha"' 10
output="$(REFRACT_HOME="$notice_home" python3 "$hook")"
check_notice "$output" "" "A Refract update"

# Remote text never reaches the output.
for bad in '"2.6.0\n$(touch pwned)"' '"2.6.0;rm -rf /"' '"`id`"'; do
    seed_cache "$notice_home" true "$bad" '"zz\nUPDATE"' 10
    output="$(REFRACT_HOME="$notice_home" python3 "$hook")"
    check_notice "$output" "" "A Refract update"
    case "$output" in *pwned*|*rm\ -rf*|*UPDATE*|*'`id`'*) exit 1 ;; esac
done

# Only a true update_available with schema 1 shows a notice.
seed_cache "$notice_home" false '"2.6.0"' null 10
check_no_notice "$(REFRACT_HOME="$notice_home" python3 "$hook")"
echo '{"schema": true, "checked_at": 1e12, "update_available": true, "latest_version": "2.6.0"}' > "$notice_home/update-check.json"
check_no_notice "$(REFRACT_STUB_LOG="$tmp/ignored" REFRACT_HOME="$notice_home" python3 "$hook")"

# Opt-outs suppress the notice and the spawn, even with a stale cache.
for optout in REFRACT_NO_UPDATE_CHECK=1 REFRACT_NO_UPDATE_CHECK=TRUE REFRACT_NO_UPDATE_CHECK=yes REFRACT_JOB_ID=x; do
    seed_cache "$notice_home" true '"2.6.0"' null 10
    : > "$tmp/calls"
    output="$(env "$optout" REFRACT_HOME="$notice_home" python3 "$hook")"
    check_no_notice "$output"
    seed_cache "$notice_home" true '"2.6.0"' null 100000
    output="$(env "$optout" REFRACT_HOME="$notice_home" python3 "$hook")"
    check_no_notice "$output"
    sleep 0.5
    test "$(cat "$tmp/calls")" = "$(printf 'status\nstatus')"
done

# Corrupt, hostile, and symlinked caches give valid JSON, exit 0, and no notice.
# They also spawn checks; those calls go to a log nothing asserts on.
export REFRACT_STUB_LOG="$tmp/ignored"
printf '{not json' > "$notice_home/update-check.json"
check_no_notice "$(REFRACT_HOME="$notice_home" python3 "$hook")"
printf '\377\376' > "$notice_home/update-check.json"
check_no_notice "$(REFRACT_HOME="$notice_home" python3 "$hook")"
printf '[1]' > "$notice_home/update-check.json"
check_no_notice "$(REFRACT_HOME="$notice_home" python3 "$hook")"
python3 -c 'print("[" * 100000)' > "$notice_home/update-check.json"
check_no_notice "$(REFRACT_HOME="$notice_home" python3 "$hook")"
python3 -c 'print(" " * 70000 + "{}")' > "$notice_home/update-check.json"
check_no_notice "$(REFRACT_HOME="$notice_home" python3 "$hook")"
rm "$notice_home/update-check.json"
mkdir "$notice_home/update-check.json"
check_no_notice "$(REFRACT_HOME="$notice_home" python3 "$hook")"
rmdir "$notice_home/update-check.json"
seed_cache "$tmp/real-cache" true '"2.6.0"' null 10
ln -s "$tmp/real-cache/update-check.json" "$notice_home/update-check.json"
check_no_notice "$(REFRACT_HOME="$notice_home" python3 "$hook")"
rm "$notice_home/update-check.json"

export REFRACT_STUB_LOG="$tmp/calls"

# A stale, missing, or unusable cache spawns a detached `update --check`.
spawns_check() {
    for _ in $(seq 50); do grep -qx 'update --check' "$tmp/calls" && return 0; sleep 0.1; done
    return 1
}
for case_name in stale future missing corrupt symlink badtime; do
    rm -rf "$notice_home"
    mkdir -p "$notice_home"
    case "$case_name" in
        stale) seed_cache "$notice_home" false null null 90000 ;;
        future) seed_cache "$notice_home" false null null -400 ;;
        missing) ;;
        corrupt) printf 'x' > "$notice_home/update-check.json" ;;
        symlink)
            seed_cache "$tmp/real-cache" false null null 0
            ln -s "$tmp/real-cache/update-check.json" "$notice_home/update-check.json" ;;
        badtime)
            echo '{"schema": 1, "checked_at": true, "update_available": false}' > "$notice_home/update-check.json" ;;
    esac
    : > "$tmp/calls"
    output="$(REFRACT_HOME="$notice_home" python3 "$hook")"
    validate_output "$output" "$repo_root"
    spawns_check
done

# A huge checked_at counts as stale: exit 0, valid JSON, no notice, and a spawned check.
python3 - "$notice_home" <<'PY'
import sys

with open(f"{sys.argv[1]}/update-check.json", "w") as f:
    f.write('{"schema": 1, "checked_at": 1' + "0" * 400 + ', "update_available": true, "latest_version": "2.6.0"}')
PY
: > "$tmp/calls"
output="$(REFRACT_HOME="$notice_home" python3 "$hook")"
check_no_notice "$output"
validate_output "$output" "$repo_root"
spawns_check

# A fresh cache does not spawn a check.
seed_cache "$notice_home" false null null 3600
: > "$tmp/calls"
REFRACT_HOME="$notice_home" python3 "$hook" > /dev/null
sleep 0.5
test "$(cat "$tmp/calls")" = "status"

# A FIFO at the cache path must not block the hook.
fifo_home="$tmp/fifo-home"
mkdir -p "$fifo_home"
mkfifo "$fifo_home/update-check.json"
: > "$tmp/calls"
output="$(REFRACT_HOME="$fifo_home" timeout 5 python3 "$hook")"
check_no_notice "$output"
validate_output "$output" "$repo_root"
spawns_check

# REFRACT_HOME is stripped and expanded like server config.refract_home().
fake_home="$tmp/fake-home"
seed_cache "$fake_home/notice-home" true '"2.6.0"' null 10
: > "$tmp/calls"
output="$(HOME="$fake_home" REFRACT_HOME=' ~/notice-home ' python3 "$hook")"
check_notice "$output" "" "Refract 2.6.0"
sleep 0.5
test "$(cat "$tmp/calls")" = "status"

# REFRACT_DISABLE skips the notice and the spawn even with a stale cache that reports an update.
seed_cache "$notice_home" true '"2.6.0"' null 100000
: > "$tmp/calls"
output="$(REFRACT_DISABLE=1 REFRACT_HOME="$notice_home" python3 "$hook")"
check_no_notice "$output"
sleep 0.5
test ! -s "$tmp/calls"

# The spawn is detached: the hook returns while `update --check` is still running.
seed_cache "$notice_home" false null null 100000
: > "$tmp/calls"
start="$(date +%s%N)"
REFRACT_STUB_UPDATE_SLEEP=3 REFRACT_HOME="$notice_home" python3 "$hook" > /dev/null
elapsed_ms=$(( ($(date +%s%N) - start) / 1000000 ))
test "$elapsed_ms" -lt 2000
spawns_check

printf 'session-start tests passed\n'
