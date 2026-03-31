#!/usr/bin/env bash
# Test: Verify no stale legacy namespace references remain
# All references should use superpowers-ccg: or superpowers: (no suffix)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

echo "=== Test: namespace consistency ==="
echo ""

# Search for stale legacy namespace references in all relevant files
LEGACY_NAMESPACE="superpowers-ccg""g:"
echo "Test 1: No stale legacy namespace references..."
STALE_REFS=$(grep -rn "$LEGACY_NAMESPACE" \
  --include="*.md" --include="*.sh" --include="*.json" --include="*.js" \
  "$REPO_ROOT" 2>/dev/null \
  | grep -v "node_modules" \
  | grep -v "tests/" \
  | grep -v "\.git/" \
  || true)

if [ -n "$STALE_REFS" ]; then
  echo "  [FAIL] Found stale legacy namespace references (should be superpowers-ccg:):"
  echo "$STALE_REFS" | sed 's/^/    /'
  exit 1
fi

echo "  [PASS] All namespace references are consistent"
echo ""
