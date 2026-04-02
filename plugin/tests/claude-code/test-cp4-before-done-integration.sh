#!/usr/bin/env bash
# Integration Test: CP4 spec review block must appear before "DONE" marker
#
# Purpose:
# - Ensures Claude outputs the new CP4 spec review block before claiming completion.
# - Validates CP4 block formatting and that it is a standalone assistant text message.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

echo "========================================"
echo " Integration Test: CP4 before DONE"
echo "========================================"
echo ""

TEST_PROJECT=$(create_test_project)
echo "Test project: $TEST_PROJECT"
trap "cleanup_test_project $TEST_PROJECT" EXIT

mkdir -p "$TEST_PROJECT"

PROMPT="Change to directory $TEST_PROJECT.

Then do the following strictly:
1) Output a standalone assistant text block containing the exact lines:
   # CP4 SPEC REVIEW COMPLETE
   
   ## Result
   - **Status**: PASS
   - **Explanation**: test
   
   ## Recommendation
   - If PASS: Task is complete
   IMPORTANT: This CP4 block must be the only content in that assistant message (no tool calls in the same message).
2) After that, output the exact text: DONE

Constraints:
- Do not call any tools
- Do not read or write any files
- Do not run Bash"

OUTPUT_FILE="$TEST_PROJECT/claude-output.txt"

echo "Running Claude (output saved to $OUTPUT_FILE)..."
echo "================================================================================"
cd "$SCRIPT_DIR/../.." && run_with_timeout 600 claude -p "$PROMPT" --allowed-tools=none --add-dir "$TEST_PROJECT" --permission-mode bypassPermissions 2>&1 | tee "$OUTPUT_FILE" || {
  echo ""
  echo "================================================================================"
  echo "EXECUTION FAILED (exit code: $?)"
  exit 1
}
echo "================================================================================"

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

cp4_line = None
cp4_block_ok = False
cp4_is_text_only_block = False
done_line = None

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

            if block.get('type') == 'text':
                text = block.get('text') or ''

                if cp4_line is None and '# CP4 SPEC REVIEW COMPLETE' in text:
                    cp4_line = i
                    cp4_block_ok = (
                        ('## Result' in text)
                        and ('Status' in text or 'status' in text)
                        and ('Explanation' in text or 'explanation' in text)
                        and ('## Recommendation' in text)
                    )
                    cp4_is_text_only_block = all(
                        isinstance(b, dict) and b.get('type') != 'tool_use'
                        for b in content
                    )

                if done_line is None and 'DONE' in text:
                    done_line = i

        if cp4_line is not None and done_line is not None:
            break

failed = False

print('Test 1: DONE marker was output...')
if done_line is None:
    print('  [FAIL] No DONE marker found in assistant messages')
    failed = True
else:
    print(f'  [PASS] DONE at transcript line {done_line}')

print('')
print('Test 2: CP4 spec review block was output...')
if cp4_line is None:
    print('  [FAIL] No "# CP4 SPEC REVIEW COMPLETE" block found in assistant messages')
    failed = True
else:
    print(f'  [PASS] CP4 block found at transcript line {cp4_line}')

print('')
print('Test 3: CP4 block includes required fields...')
if cp4_line is None:
    print('  [FAIL] Missing CP4; cannot validate required fields')
    failed = True
elif cp4_block_ok:
    print('  [PASS] CP4 contains: Result / Status / Explanation / Recommendation')
else:
    print('  [FAIL] CP4 missing one or more required fields:')
    print('         - Result / Status / Explanation / Recommendation')
    failed = True

print('')
print('Test 4: CP4 is a standalone assistant text message (no tool_use in same message)...')
if cp4_line is None:
    print('  [FAIL] Missing CP4; cannot validate standalone requirement')
    failed = True
elif cp4_is_text_only_block:
    print('  [PASS] CP4 appears in a text-only assistant message')
else:
    print('  [FAIL] CP4 was not in a text-only assistant message')
    failed = True

print('')
print('Test 5: CP4 appears BEFORE DONE marker...')
if cp4_line is None or done_line is None:
    print('  [FAIL] Missing CP4 or DONE; cannot verify order')
    failed = True
elif cp4_line <= done_line:
    print(f'  [PASS] CP4 (line {cp4_line}) is before-or-same-line as DONE (line {done_line})')
else:
    print(f'  [FAIL] Expected CP4 before DONE, but CP4 is at line {cp4_line} and DONE is at line {done_line}')
    failed = True

sys.exit(1 if failed else 0)
PY

echo ""
echo "========================================"
echo " Test Summary"
echo "========================================"
echo ""
echo "STATUS: PASSED"
