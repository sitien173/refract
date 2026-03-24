#!/usr/bin/env bash
# Test: Verify no stale superpowers-ccg: (2-C) namespace references remain
# All references should use superpowers-cccg: (3-C) or superpowers: (no suffix)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$SCRIPT_DIR/test-helpers.sh"

echo "=== Test: namespace consistency ==="
echo ""

# Search for superpowers-ccg: (exactly 2 C's, not 3) in all relevant files
# Exclude: superpowers-ccg.md filename itself, node_modules, docs/plans (archived), .git
echo "Test 1: No stale superpowers-ccg: references..."
STALE_REFS=$(grep -rn "superpowers-ccg:" \
  --include="*.md" --include="*.sh" --include="*.json" --include="*.js" \
  "$REPO_ROOT" 2>/dev/null \
  | grep -v "superpowers-cccg:" \
  | grep -v "superpowers-ccg\.md" \
  | grep -v "node_modules" \
  | grep -v "docs/plans/" \
  | grep -v "tests/" \
  | grep -v "\.git/" \
  || true)

if [ -n "$STALE_REFS" ]; then
  echo "  [FAIL] Found stale superpowers-ccg: references (should be superpowers-cccg:):"
  echo "$STALE_REFS" | sed 's/^/    /'
  exit 1
fi

echo "  [PASS] All namespace references are consistent"
echo ""
