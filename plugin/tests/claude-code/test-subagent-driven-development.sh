#!/usr/bin/env bash
# Test: developing-with-subagents skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

echo "=== Test: developing-with-subagents skill ==="
echo ""

echo "Test 1: Skill loading..."
output=$(run_claude "What is the developing-with-subagents skill? Describe its key steps briefly." 60)
assert_contains "$output" "developing-with-subagents|Subagent-Driven Development|Subagent-Driven" "Skill is recognized" || exit 1
assert_contains "$output" "one bounded task|one task at a time|bounded task" "Bounded task focus" || exit 1
echo ""

echo "Test 2: Review ordering..."
output=$(run_claude "In the developing-with-subagents skill, what comes first: spec review or Opus quality review?" 60)
assert_contains "$output" "spec" "Mentions spec review" || exit 1
assert_contains "$output" "Opus" "Mentions Opus review" || exit 1
echo ""

echo "Test 3: Worker ownership..."
output=$(run_claude "How should developing-with-subagents assign implementation work: one worker per bounded task, or multiple workers on the same implementation task?" 60)
assert_contains "$output" "one worker|single worker" "Single worker ownership" || exit 1
assert_not_contains "$output" "multiple workers on the same task" "No duplicate worker ownership" || exit 1
echo ""

echo "Test 4: Session reuse..."
output=$(run_claude "Does developing-with-subagents say to reuse the same worker SESSION_ID for fixes on the same task?" 60)
assert_contains "$output" "same worker|SESSION_ID|reuse" "Session reuse mentioned" || exit 1
echo ""

echo "Test 5: No prototype-then-rewrite..."
output=$(run_claude "In developing-with-subagents, should Claude ask for a prototype/reference and then rewrite it later?" 60)
assert_contains "$output" "do not|should not|avoid" "Prohibited pattern is rejected" || exit 1
assert_contains "$output" "prototype|reference" "Mentions prototype/reference" || exit 1
echo ""

echo "Test 6: Output contract..."
output=$(run_claude "What should the worker return in developing-with-subagents: prose prototype, or diff-or-questions?" 60)
assert_contains "$output" "diff-or-questions|questions|diff" "Diff-or-questions contract" || exit 1
echo ""

echo "Test 7: Cross-validation is rare..."
output=$(run_claude "When should developing-with-subagents use cross-validation?" 60)
assert_contains "$output" "rare|only when|unresolved|ambigu" "Cross-validation is constrained" || exit 1
echo ""

echo "=== All developing-with-subagents skill tests passed ==="
