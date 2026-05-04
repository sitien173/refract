#!/usr/bin/env bash
# Test: executing-phases skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

echo "=== Test: executing-phases skill ==="
echo ""

echo "Test 1: Skill loading..."
output=$(run_claude "What is the superpowers-ccg:executing-phases skill? Describe its key steps briefly. Do not describe executing-plans." 60)
assert_contains "$output" "executing-phases|Executing Phases|phase execution|current phase|active phase|implementation phases" "Skill is recognized" || exit 1
assert_contains "$output" "one implementation phase|one phase at a time|2-4 related tasks|phase" "Phase focus" || exit 1
echo ""

echo "Test 2: Final review stage..."
output=$(run_claude "In the executing-phases skill, what is the review step: CP4 phase review, or Sonnet code quality review?" 60)
assert_contains "$output" "CP4|phase review|PASS|PASS_WITH_DEBT|FAIL" "Mentions CP4 phase review" || exit 1
echo ""

echo "Test 3: Worker ownership..."
output=$(run_claude "How should executing-phases assign implementation work: one primary executor per phase, or multiple workers on the same implementation phase?" 60)
assert_contains "$output" "[Oo]ne primary executor|one worker|single worker" "Single executor ownership" || exit 1
assert_not_contains "$output" "multiple workers on the same task" "No duplicate worker ownership" || exit 1
echo ""

echo "Test 4: Session reuse..."
output=$(run_claude "Does executing-phases say to reuse the same worker SESSION_ID for fixes on the same phase?" 60)
assert_contains "$output" "same worker|SESSION_ID|reuse" "Session reuse mentioned" || exit 1
echo ""

echo "Test 5: No prototype-then-rewrite..."
output=$(run_claude "In executing-phases, should Claude ask for a prototype/reference and then rewrite it later?" 60)
assert_contains "$output" "[Dd]o not|should not|avoid|[Nn]o\.|[Nn]ever" "Prohibited pattern is rejected" || exit 1
assert_contains "$output" "prototype|reference" "Mentions prototype/reference" || exit 1
echo ""

echo "Test 6: Output contract..."
output=$(run_claude "In executing-phases, how does the worker return its work: by pasting a prose prototype, or by editing files directly via MCP write tools and reporting via External Response Protocol v1.1?" 60)
assert_contains "$output" "External Response Protocol v1\\.1|MCP|edit files|FILES MODIFIED" "External execution contract" || exit 1
echo ""

echo "Test 7: Cross-validation is rare..."
output=$(run_claude "When should executing-phases use cross-validation?" 60)
assert_contains "$output" "rare|only when|unresolved|ambigu" "Cross-validation is constrained" || exit 1
echo ""

echo "Test 8: MCP failure blocks..."
output=$(run_claude "In executing-phases, what happens if the Codex or Gemini MCP call fails: retry/fallback, or BLOCKED?" 60)
assert_contains "$output" "BLOCKED|blocked" "MCP failure blocks phase" || exit 1
assert_contains "$output" "do not retry|no retry|not retry|do not switch|no fallback|do not fall back" "No retry or fallback" || exit 1
echo ""

echo "=== All executing-phases skill tests passed ==="
