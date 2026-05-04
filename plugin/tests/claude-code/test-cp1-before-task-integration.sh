#!/usr/bin/env bash
# Integration Test: CP1 evaluation must appear before first worker dispatch tool use
#
# Purpose:
# - Reproduces the failure mode where Claude dispatches workers without
#   explicitly outputting a CP1 routing evaluation.
# - Validates the improved skill/hook prompts enforce an explicit CP1 block
#   before any worker dispatch tool call.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

echo "========================================"
echo " Integration Test: CP1 before worker dispatch"
echo "========================================"
echo ""

# Create a minimal test project (no deps, no git required)
TEST_PROJECT=$(create_test_project)
echo "Test project: $TEST_PROJECT"
trap "cleanup_test_project $TEST_PROJECT" EXIT

mkdir -p "$TEST_PROJECT"

# Run Claude from repo root so local dev skills/hooks are loaded.
# The prompt explicitly requests using Task so we can verify ordering in transcript.
PROMPT="Change to directory $TEST_PROJECT, then use the executing-phases skill to execute the following plan.

IMPORTANT (protocol):
- Before the first Task tool call, you MUST output a standalone assistant text message that begins with # CP1 ROUTING DECISION and includes these required sections and fields:
  - ## Task Summary
  - ## Route
  - Model
  - Cross-Validation
  - Reason
  - ## Next Action
- Do NOT output any legacy [CP1 Assessment] or [CP1] Routing block.
- That CP1 message must NOT include any tool calls.

PLAN:
- Task 1: Dispatch ONE implementer worker using the Task tool (not internal reasoning), whose only job is to reply with the exact text: pong
  Constraints for the implementer worker:
  - Do not read or write any files
  - Do not run Bash
  - Do not call any tools

IMPORTANT:
- You MUST use the Task tool for the implementer worker.
- Do not complete the task yourself.

After the implementer responds, stop."

OUTPUT_FILE="$TEST_PROJECT/claude-output.txt"

echo "Running Claude (output saved to $OUTPUT_FILE)..."
echo "================================================================================"
cd "$SCRIPT_DIR/../.." && run_with_timeout 600 claude -p "$PROMPT" --allowed-tools=all --add-dir "$TEST_PROJECT" --permission-mode bypassPermissions 2>&1 | tee "$OUTPUT_FILE" || {
  echo ""
  echo "================================================================================"
  echo "EXECUTION FAILED (exit code: $?)"
  exit 1
}
echo "================================================================================"

# Locate session transcript
# Session dir corresponds to where we run `claude` from (repo root).
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT_WIN="$(cd "$SCRIPT_DIR/../.." && pwd -W 2>/dev/null || true)"
WORKING_DIR_ESCAPED_UNIX=$(echo "$REPO_ROOT" | sed 's/\//-/g')
WORKING_DIR_ESCAPED_WIN=""
if [ -n "$REPO_ROOT_WIN" ]; then
  WORKING_DIR_ESCAPED_WIN=$(echo "$REPO_ROOT_WIN" | sed -E 's#^([A-Za-z]):[\\/]#\1--#; s#[\\/]#-#g')
fi

SESSION_DIR=""
for candidate in \
  "$HOME/.claude/projects/$WORKING_DIR_ESCAPED_WIN" \
  "$HOME/.claude/projects/$WORKING_DIR_ESCAPED_UNIX"
do
  if [ -n "$candidate" ] && [ -d "$candidate" ]; then
    SESSION_DIR="$candidate"
    break
  fi
done

if [ -z "$SESSION_DIR" ]; then
  echo "ERROR: Could not find session directory"
  echo "Looked for:"
  echo "  $HOME/.claude/projects/$WORKING_DIR_ESCAPED_WIN"
  echo "  $HOME/.claude/projects/$WORKING_DIR_ESCAPED_UNIX"
  exit 1
fi

SESSION_FILE=$(python3 - "$SESSION_DIR" <<'PY'
import glob
import os
import sys

d = sys.argv[1]
paths = glob.glob(os.path.join(d, '*.jsonl'))
if not paths:
    raise SystemExit(1)
# Prefer most-recent mtime; this is more reliable than lexicographic sort of UUIDs.
paths.sort(key=os.path.getmtime, reverse=True)
print(paths[0])
PY
) || SESSION_FILE=""

if [ -z "${SESSION_FILE:-}" ]; then
  echo "ERROR: Could not find session transcript file"
  echo "Looked in: $SESSION_DIR"
  exit 1
fi

echo "Analyzing session transcript: $(basename "$SESSION_FILE")"
echo ""

echo "=== Verification Tests ==="
echo ""

python3 - "$SESSION_FILE" <<'PY'
import json
import sys

path = sys.argv[1]

cp1_line = None
cp1_block_ok = False
cp1_is_text_only_block = False
legacy_cp1_seen = False
first_dispatch_line = None

with open(path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if obj.get('type') != 'assistant':
            continue

        msg = obj.get('message') or {}
        content = msg.get('content') or []

        for block in content:
            if not isinstance(block, dict):
                continue

            if block.get('type') == 'text' and cp1_line is None:
                text = block.get('text') or ''
                if '# CP1 ROUTING DECISION' in text:
                    cp1_line = i

                    # CP1 block must include required fields.
                    cp1_block_ok = (
                        ('## Task Summary' in text)
                        and ('## Route' in text)
                        and ('Model' in text or 'model' in text)
                        and ('Cross-Validation' in text or 'cross-validation' in text)
                        and ('Reason' in text or 'reason' in text)
                        and ('## Next Action' in text)
                    )

                    # CP1 must be a standalone assistant text message (no tool_use blocks in same message).
                    cp1_is_text_only_block = all(
                        isinstance(b, dict) and b.get('type') != 'tool_use'
                        for b in content
                    )
                if '[CP1 Assessment]' in text or '[CP1] Routing' in text:
                    legacy_cp1_seen = True

            if block.get('type') == 'tool_use' and first_dispatch_line is None:
                if block.get('name') in ('Task', 'Agent'):
                    first_dispatch_line = i

        if cp1_line is not None and first_dispatch_line is not None:
            break

failed = False

print('Test 1: Worker dispatch tool was used...')
if first_dispatch_line is None:
    print('  [FAIL] No Task or Agent tool call found in transcript')
    failed = True
else:
    print(f'  [PASS] First Task/Agent tool call at transcript line {first_dispatch_line}')

print('')
print('Test 2: CP1 evaluation block was output...')
if cp1_line is None:
    print('  [FAIL] No "# CP1 ROUTING DECISION" block found in assistant messages')
    failed = True
else:
    print(f'  [PASS] CP1 evaluation found at transcript line {cp1_line}')

print('')
print('Test 3: CP1 block includes required fields...')
if cp1_line is None:
    print('  [FAIL] Missing CP1; cannot validate required fields')
    failed = True
elif cp1_block_ok:
    print('  [PASS] CP1 contains: Task Summary / Route / Model / Cross-Validation / Reason / Next Action')
else:
    print('  [FAIL] CP1 missing one or more required fields:')
    print('         - Task Summary / Route / Model / Cross-Validation / Reason / Next Action')
    failed = True

print('')
print('Test 4: Legacy CP1 formats are not used...')
if legacy_cp1_seen:
    print('  [FAIL] Found legacy "[CP1 Assessment]" or "[CP1] Routing" output')
    failed = True
else:
    print('  [PASS] No legacy CP1 format found')

print('')
print('Test 5: CP1 is a standalone assistant text message (no tool_use in same message)...')
if cp1_line is None:
    print('  [FAIL] Missing CP1; cannot validate standalone requirement')
    failed = True
elif cp1_is_text_only_block:
    print('  [PASS] CP1 appears in a text-only assistant message')
else:
    print('  [FAIL] CP1 was not in a text-only assistant message')
    failed = True

print('')
print('Test 6: CP1 appears BEFORE first worker dispatch tool call...')
if cp1_line is None or first_dispatch_line is None:
    print('  [FAIL] Missing CP1 or Task/Agent line; cannot verify order')
    failed = True
elif cp1_line < first_dispatch_line:
    print(f'  [PASS] CP1 (line {cp1_line}) is before Task/Agent (line {first_dispatch_line})')
else:
    print(f'  [FAIL] Expected CP1 before Task/Agent, but CP1 is at line {cp1_line} and Task/Agent is at line {first_dispatch_line}')
    failed = True

sys.exit(1 if failed else 0)
PY

echo ""
echo "========================================"
echo " Test Summary"
echo "========================================"
echo ""
echo "STATUS: PASSED"
