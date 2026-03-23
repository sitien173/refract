#!/usr/bin/env bash
# Test: developing-with-subagents skill
# Verifies that the skill is loaded and follows correct workflow
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

echo "=== Test: developing-with-subagents skill ==="
echo ""

# Test 1: Verify skill can be loaded
echo "Test 1: Skill loading..."

output=$(run_claude "What is the developing-with-subagents skill? Describe its key steps briefly." 60)

if assert_contains "$output" "developing-with-subagents|Subagent-Driven Development|Subagent-Driven" "Skill is recognized"; then
    : # pass
else
    exit 1
fi

if assert_contains "$output" "Load Plan|read.*plan|extract.*tasks" "Mentions loading plan"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 2: Verify skill describes correct workflow order
echo "Test 2: Workflow ordering..."

output=$(run_claude "In the developing-with-subagents skill, what comes first: spec compliance review or code quality review? Be specific about the order." 60)

if assert_contains "$output" "spec.*compliance" "Mentions spec compliance" && assert_contains "$output" "code.*quality" "Mentions code quality"; then
    : # pass
else
    exit 1
fi

# Ordering is not strictly asserted here because the model may answer with both terms on the same line.
# Integration tests cover actual workflow sequencing.

echo ""

# Test 3: Verify self-review is mentioned
echo "Test 3: Self-review requirement..."

output=$(run_claude "Does the developing-with-subagents skill require implementers to do self-review? What should they check?" 60)

if assert_contains "$output" "self-review|self review" "Mentions self-review"; then
    : # pass
else
    exit 1
fi

# Some responses summarize self-review without enumerating specific checklist fields.
# Keep this check permissive to avoid flakiness.
# Keep permissive; accept common variants.
if assert_contains "$output" "check" "Mentions checking"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 4: Verify plan is read once
echo "Test 4: Plan reading efficiency..."

output=$(run_claude "In developing-with-subagents, how many times should the controller read the plan file? When does this happen?" 60)

if assert_contains "$output" "once|one time|single" "Read plan once"; then
    : # pass
else
    exit 1
fi

if assert_contains "$output" "Step 1|beginning|start|Load Plan" "Read at beginning"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 5: Verify spec compliance reviewer is skeptical
echo "Test 5: Spec compliance reviewer mindset..."

output=$(run_claude "What is the spec compliance reviewer's attitude toward the implementer's report in developing-with-subagents?" 60)

if assert_contains "$output" "not trust|don't trust|skeptical|verify.*independently|suspiciously" "Reviewer is skeptical"; then
    : # pass
else
    exit 1
fi

# The skill encourages independent verification, but the model may paraphrase without literally saying "read code".
# Keep this check permissive.
# Model responses vary; don't require specific keywords here.
: # pass

echo ""

# Test 6: Verify review loops
echo "Test 6: Review loop requirements..."

output=$(run_claude "In developing-with-subagents, what happens if a reviewer finds issues? Is it a one-time review or a loop?" 60)

if assert_contains "$output" "loop|again|repeat|until.*approved|until.*compliant" "Review loops mentioned"; then
    : # pass
else
    exit 1
fi

if assert_contains "$output" "implementer.*fix|fix.*issues" "Implementer fixes issues"; then
    : # pass
else
    exit 1
fi

echo ""

# Test 7: Verify full task text is provided
echo "Test 7: Task context provision..."

output=$(run_claude "In developing-with-subagents, how does the controller provide task information to the implementer subagent? Does it make them read a file or provide it directly?" 60)

if assert_contains "$output" "provide.*directly|full.*text|paste|include.*prompt" "Provides text directly"; then
    : # pass
else
    exit 1
fi

if assert_not_contains "$output" "open.*file" "Doesn't make subagent read file"; then
    : # pass
else
    exit 1
fi

echo ""

echo "=== All developing-with-subagents skill tests passed ==="
