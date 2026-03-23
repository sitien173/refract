#!/usr/bin/env bash
# Integration Test: CP3 evaluation must appear before "DONE" marker
#
# Purpose:
# - Ensures Claude outputs a CP3 routing evaluation before claiming completion.
# - Validates CP3 block formatting and that it is a standalone assistant text message.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

echo "========================================"
echo " Integration Test: CP3 before DONE"
echo "========================================"
echo ""

# Create a minimal test project (no deps, no git required)
TEST_PROJECT=$(create_test_project)
echo "Test project: $TEST_PROJECT"
trap "cleanup_test_project $TEST_PROJECT" EXIT

mkdir -p "$TEST_PROJECT"

# Run Claude from repo root so local dev skills/hooks are loaded.
# The prompt forces a stable end marker (DONE) so we can assert ordering.
PROMPT="Change to directory $TEST_PROJECT.

Then do the following strictly:
1) Output a standalone assistant text block containing the exact lines:
   [CP3 Assessment]
   - Task type: Other
   - Routing decision: CLAUDE
   - Rationale: test
   IMPORTANT: This CP3 block must be the only content in that assistant message (no tool calls in the same message).
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

# Locate session transcript
# Session dir corresponds to where we run `claude` from (repo root).
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORKING_DIR_ESCAPED=$(echo "$REPO_ROOT" | sed 's/\//-/g')
SESSION_DIR="$HOME/.claude/projects/$WORKING_DIR_ESCAPED"
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

cp3_line = None
cp3_block_ok = False
cp3_is_text_only_block = False

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

                if cp3_line is None and '[CP3 Assessment]' in text:
                    cp3_line = i
                    cp3_block_ok = (
                        ('Task type' in text or 'task type' in text)
                        and ('Routing decision' in text or 'routing decision' in text)
                        and ('Rationale' in text or 'rationale' in text)
                    )
                    cp3_is_text_only_block = all(
                        isinstance(b, dict) and b.get('type') != 'tool_use'
                        for b in content
                    )

                # DONE may appear in the same text block as CP3 (depending on model behavior).
                # Treat it as found if the marker appears anywhere in a text block.
                if done_line is None and 'DONE' in text:
                    done_line = i

        if cp3_line is not None and done_line is not None:
            break

failed = False

print('Test 1: DONE marker was output...')
if done_line is None:
    print('  [FAIL] No DONE marker found in assistant messages')
    failed = True
else:
    print(f'  [PASS] DONE at transcript line {done_line}')

print('')
print('Test 2: CP3 evaluation block was output...')
if cp3_line is None:
    print('  [FAIL] No "[CP3 Assessment]" block found in assistant messages')
    failed = True
else:
    print(f'  [PASS] CP3 evaluation found at transcript line {cp3_line}')

print('')
print('Test 3: CP3 block includes required fields...')
if cp3_line is None:
    print('  [FAIL] Missing CP3; cannot validate required fields')
    failed = True
elif cp3_block_ok:
    print('  [PASS] CP3 contains: Task type / Routing decision / Rationale')
else:
    print('  [FAIL] CP3 missing one or more required fields:')
    print('         - Task type / Routing decision / Rationale')
    failed = True

print('')
print('Test 4: CP3 is a standalone assistant text message (no tool_use in same message)...')
if cp3_line is None:
    print('  [FAIL] Missing CP3; cannot validate standalone requirement')
    failed = True
elif cp3_is_text_only_block:
    print('  [PASS] CP3 appears in a text-only assistant message')
else:
    print('  [FAIL] CP3 was not in a text-only assistant message')
    failed = True

print('')
print('Test 5: CP3 appears BEFORE DONE marker...')
if cp3_line is None or done_line is None:
    print('  [FAIL] Missing CP3 or DONE; cannot verify order')
    failed = True
elif cp3_line <= done_line:
    # Allow same-line success because DONE may be appended in the same assistant message.
    print(f'  [PASS] CP3 (line {cp3_line}) is before-or-same-line as DONE (line {done_line})')
else:
    print(f'  [FAIL] Expected CP3 before DONE, but CP3 is at line {cp3_line} and DONE is at line {done_line}')
    failed = True

sys.exit(1 if failed else 0)
PY

echo ""
echo "========================================"
echo " Test Summary"
echo "========================================"
echo ""
echo "STATUS: PASSED"
