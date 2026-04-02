#!/usr/bin/env bash
# Test: static CP4 final spec review guardrails remain aligned
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Test: CP4 final spec review guards ==="
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

echo "Test 1: CP4 is explicitly named Final Spec Review..."
if ! rg -n 'CP4: Final Spec Review|CP4 \(Final Spec Review\)|CP4 Final Spec Review|Final Spec Review: always run last' "${TARGETS[@]}" >/tmp/cp4-guards-name.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP4 Final Spec Review language"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 2: Exact CP4 spec review block exists in injected docs..."
if ! rg -n '^# CP4 SPEC REVIEW COMPLETE|^## Result|^\- \*\*Status\*\*: PASS / PARTIAL / FAIL|^\- \*\*Explanation\*\*: \[Clear, concise explanation\]|^## Recommendation|Task is complete|Specific gaps \+ suggested next action' \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" >/tmp/cp4-guards-block.txt 2>/dev/null; then
  echo "  [FAIL] Missing exact CP4 spec review block"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3: CP4 is explicitly spec-only..."
if ! rg -n 'spec-only|pure spec review|Do not perform code quality, style, redundancy, or best-practice review|do not review code quality, style, redundancy, or best practices' \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" >/tmp/cp4-guards-spec-only.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP4 spec-only restriction"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 4: Diagram labels CP4 as Final Spec Review..."
if ! rg -n 'CP4\[CP4: Final Spec Review\]' "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md" >/tmp/cp4-guards-diagram.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP4 Final Spec Review label in diagram"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== CP4 final spec review guard tests passed ==="
