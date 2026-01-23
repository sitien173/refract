#!/bin/bash
# Run all explicit skill request tests
# Usage: ./run-all.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROMPTS_DIR="$SCRIPT_DIR/prompts"

echo "=== Running All Explicit Skill Request Tests ==="
echo ""

PASSED=0
FAILED=0
RESULTS=""

# Test: developing-with-subagents, please (canonical skill name)
echo ">>> Test 1: developing-with-subagents-please"
if "$SCRIPT_DIR/run-test.sh" "developing-with-subagents" "$PROMPTS_DIR/subagent-driven-development-please.txt"; then
    PASSED=$((PASSED + 1))
    RESULTS="$RESULTS\nPASS: developing-with-subagents-please"
else
    FAILED=$((FAILED + 1))
    RESULTS="$RESULTS\nFAIL: developing-with-subagents-please"
fi
echo ""

# Test: use debugging-systematically
echo ">>> Test 2: use-debugging-systematically"
if "$SCRIPT_DIR/run-test.sh" "debugging-systematically" "$PROMPTS_DIR/use-systematic-debugging.txt"; then
    PASSED=$((PASSED + 1))
    RESULTS="$RESULTS\nPASS: use-debugging-systematically"
else
    FAILED=$((FAILED + 1))
    RESULTS="$RESULTS\nFAIL: use-debugging-systematically"
fi
echo ""

# Test: please use brainstorming
echo ">>> Test 3: please-use-brainstorming"
if "$SCRIPT_DIR/run-test.sh" "brainstorming" "$PROMPTS_DIR/please-use-brainstorming.txt"; then
    PASSED=$((PASSED + 1))
    RESULTS="$RESULTS\nPASS: please-use-brainstorming"
else
    FAILED=$((FAILED + 1))
    RESULTS="$RESULTS\nFAIL: please-use-brainstorming"
fi
echo ""

# Test: mid-conversation execute plan
echo ">>> Test 4: mid-conversation-execute-plan"
if "$SCRIPT_DIR/run-test.sh" "developing-with-subagents" "$PROMPTS_DIR/mid-conversation-execute-plan.txt"; then
    PASSED=$((PASSED + 1))
    RESULTS="$RESULTS\nPASS: mid-conversation-execute-plan"
else
    FAILED=$((FAILED + 1))
    RESULTS="$RESULTS\nFAIL: mid-conversation-execute-plan"
fi
echo ""

echo "=== Summary ==="
echo -e "$RESULTS"
echo ""
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo "Total: $((PASSED + FAILED))"

if [ "$FAILED" -gt 0 ]; then
    exit 1
fi
