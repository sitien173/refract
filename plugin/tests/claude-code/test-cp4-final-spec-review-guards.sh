#!/usr/bin/env bash
# Test: static CP4 phase review guardrails remain aligned
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Test: CP4 phase review guards ==="
echo ""

TARGETS=(
  "$REPO_ROOT/hooks/session-start.sh"
  "$REPO_ROOT/hooks/user-prompt-submit.sh"
  "$REPO_ROOT/skills/shared/protocol-threshold.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/INTEGRATION.md"
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md"
  "$REPO_ROOT/README.md"
  "$REPO_ROOT/superpowers-ccg.md"
  "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md"
)

echo "Test 1: CP4 is explicitly named Phase Review..."
if ! rg -n 'CP4: Phase Review|CP4 \(Phase Review\)|CP4 Phase Review|Phase Review after each phase' "${TARGETS[@]}" >/tmp/cp4-guards-name.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP4 Phase Review language"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 2: Exact CP4 phase review block exists in injected docs..."
if ! rg -n '^# CP4 SPEC REVIEW COMPLETE|^## Result|^\- \*\*Status\*\*: PASS / PASS_WITH_DEBT / FAIL|^\- \*\*Explanation\*\*: \[Clear, concise explanation\]|^## Recommendation|Phase is complete|Non-blocking debt|Specific gaps \+ suggested next action' \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" >/tmp/cp4-guards-block.txt 2>/dev/null; then
  echo "  [FAIL] Missing exact CP4 spec review block"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3: CP4 avoids broad style review unless checklist requires it..."
if ! rg -n 'Do not perform broad code quality, style, redundancy, or best-practice review|do not perform broad style review|do not review broad style|unless listed in the phase checklist' \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" >/tmp/cp4-guards-spec-only.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP4 spec-only restriction"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 4: Diagram labels CP4 as Phase Review..."
if ! rg -n 'CP4\[CP4: Phase Review\]' "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md" >/tmp/cp4-guards-diagram.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP4 Phase Review label in diagram"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== CP4 phase review guard tests passed ==="
