#!/usr/bin/env bash
# Test: static CP0 context-acquisition guardrails remain aligned
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Test: CP0 context acquisition guards ==="
echo ""

TARGETS=(
  "$REPO_ROOT/hooks/session-start.sh"
  "$REPO_ROOT/hooks/user-prompt-submit.sh"
  "$REPO_ROOT/README.md"
  "$REPO_ROOT/superpowers-ccg.md"
  "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md"
  "$REPO_ROOT/skills/shared/protocol-threshold.md"
  "$REPO_ROOT/skills/shared/supplementary-tools.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md"
)

echo "Test 1: CP0 is explicitly documented in workflow docs..."
if ! rg -n '\bCP0\b' "${TARGETS[@]}" >/tmp/cp0-guards-cp0.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP0 references in workflow docs"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 2: Hybrid Context Engine tool order is documented..."
if ! rg -n 'Auggie.*Morph WarpGrep.*Serena.*Grok Search|Auggie → Morph WarpGrep → Serena → Grok Search' "${TARGETS[@]}" >/tmp/cp0-guards-order.txt 2>/dev/null; then
  echo "  [FAIL] Missing Hybrid Context Engine order"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3: CP0 tool matrix is embedded in active docs..."
if ! rg -n '\| Need \| Primary Tool \| When to Trigger Grok Search \| Fallback \||Semantic "Where/What/How" in codebase \| Auggie \||Fast parallel search inside the codebase \| Morph WarpGrep \||Symbol navigation & references \| Serena \||Persistent project memory / graph \| Serena \||External / real-world knowledge \| Grok Search \|' \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" >/tmp/cp0-guards-csv.txt 2>/dev/null; then
  echo "  [FAIL] Active docs do not include the expected CP0 tool matrix"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 4: Architecture diagram includes CP0 before CP1..."
if ! rg -n 'CP0: Context Acquisition.*CP1: Routing|START\[User Request\] --> CP0' "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md" >/tmp/cp0-guards-diagram.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP0 in architecture diagram"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== CP0 context acquisition guard tests passed ==="
