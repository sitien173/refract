#!/usr/bin/env bash
# Test: developing-with-subagents skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

echo "=== Test: developing-with-subagents skill ==="
echo ""

echo "Test 1: Skill loading..."
output=$(run_claude "What is the developing-with-subagents skill? Describe its key steps briefly." 60)
assert_contains "$output" "[Dd]eveloping-with-[Ss]ubagents|[Ss]ubagent-[Dd]riven [Dd]evelopment|[Ss]ubagent-[Dd]riven" "Skill is recognized" || exit 1
assert_contains "$output" "one implementation phase|one phase at a time|2-4 related tasks|phase" "Phase focus" || exit 1
echo ""

echo "Test 2: Final review stage..."
output=$(run_claude "In the developing-with-subagents skill, what is the review step: CP4 phase review, or Sonnet code quality review?" 60)
assert_contains "$output" "CP4|phase review|PASS|PASS_WITH_DEBT|FAIL" "Mentions CP4 phase review" || exit 1
echo ""

echo "Test 3: Worker ownership..."
output=$(run_claude "How should developing-with-subagents assign implementation work: one primary executor per phase, or multiple workers on the same implementation phase?" 60)
assert_contains "$output" "[Oo]ne primary executor|one worker|single worker" "Single executor ownership" || exit 1
assert_not_contains "$output" "multiple workers on the same task" "No duplicate worker ownership" || exit 1
echo ""

echo "Test 4: Session reuse..."
output=$(run_claude "Does developing-with-subagents say to reuse the same worker SESSION_ID for fixes on the same phase?" 60)
assert_contains "$output" "same worker|SESSION_ID|reuse" "Session reuse mentioned" || exit 1
echo ""

echo "Test 5: No prototype-then-rewrite..."
output=$(run_claude "In developing-with-subagents, should Claude ask for a prototype/reference and then rewrite it later?" 60)
assert_contains "$output" "[Dd]o not|should not|avoid|[Nn]o\.|[Nn]ever" "Prohibited pattern is rejected" || exit 1
assert_contains "$output" "prototype|reference" "Mentions prototype/reference" || exit 1
echo ""

echo "Test 6: Output contract..."
output=$(run_claude "In developing-with-subagents, how does the worker return its work: by pasting a prose prototype, or by editing files directly via MCP write tools and reporting via External Response Protocol v1.1?" 60)
assert_contains "$output" "External Response Protocol v1\\.1|MCP|edit files|FILES MODIFIED" "External execution contract" || exit 1
echo ""

echo "Test 7: Cross-validation is rare..."
output=$(run_claude "When should developing-with-subagents use cross-validation?" 60)
assert_contains "$output" "rare|only when|unresolved|ambigu" "Cross-validation is constrained" || exit 1
echo ""

echo "=== All developing-with-subagents skill tests passed ==="
