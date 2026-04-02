#!/usr/bin/env bash
# Test: static CP3 reconciliation guardrails remain aligned
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Test: CP3 reconciliation guards ==="
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

echo "Test 1: CP3 is explicitly named Reconciliation..."
if ! rg -n 'CP3: Reconciliation|CP3 \(Reconciliation\)|CP3 Reconciliation|Reconciliation: after cross-validation' "${TARGETS[@]}" >/tmp/cp3-guards-name.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP3 Reconciliation language"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 2: Exact CP3 reconciliation block exists in the injected docs..."
if ! rg -n '^# CP3 RECONCILIATION COMPLETE|^## Summary|^## Changes Applied|^## Status|^Ready for CP4$' \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" >/tmp/cp3-guards-block.txt 2>/dev/null; then
  echo "  [FAIL] Missing exact CP3 reconciliation block"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3: Legacy CP3 formats are absent from active docs..."
if rg -n '^\[CP3 Assessment\]$|^\[CP3\] Verified:' \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" >/tmp/cp3-guards-legacy.txt 2>/dev/null; then
  echo "  [FAIL] Found legacy CP3 format references in active docs"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 4: Diagram labels CP3 as Reconciliation..."
if ! rg -n 'CP3\[CP3: Reconciliation\]' "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md" >/tmp/cp3-guards-diagram.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP3 Reconciliation label in diagram"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== CP3 reconciliation guard tests passed ==="
