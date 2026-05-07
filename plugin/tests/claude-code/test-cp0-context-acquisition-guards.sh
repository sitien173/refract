#!/usr/bin/env bash
# Test: static CP0 context-acquisition guardrails remain aligned
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ACTIVE_CP0_TARGETS=(
  "$REPO_ROOT/hooks/session-start.sh"
  "$REPO_ROOT/hooks/user-prompt-submit.sh"
  "$REPO_ROOT/CLAUDE.md"
  "$REPO_ROOT/README.md"
  "$REPO_ROOT/superpowers-ccg.md"
  "$REPO_ROOT/rules/ccg-workflow.mdc"
  "$REPO_ROOT/skills/shared/protocol-threshold.md"
  "$REPO_ROOT/skills/shared/supplementary-tools.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/context-sharing.md"
)

CP0_DOC_TARGETS=(
  "${ACTIVE_CP0_TARGETS[@]}"
  "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md"
)

echo "=== Test: CP0 context acquisition guards ==="
echo ""

echo "Test 1: CP0 is explicitly documented in workflow docs..."
if ! rg -n '\bCP0\b' "${CP0_DOC_TARGETS[@]}" >/tmp/cp0-guards-cp0.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP0 references in workflow docs"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 2: CP0 tool ordering is documented..."
if ! rg -n 'context-retrieval.*Grok Search|Grok Search.*context-retrieval' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-order.txt 2>/dev/null; then
  echo "  [FAIL] Missing context-retrieval + Grok Search CP0 ordering"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3: Context-retrieval single-tool role is documented..."
if ! rg -n 'codebase-retrieval.*semantic|semantic.*codebase-retrieval|codebase-retrieval.*local codebase|local codebase.*codebase-retrieval' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-codebase-retrieval.txt 2>/dev/null; then
  echo "  [FAIL] Missing codebase-retrieval semantic/local codebase role"
  exit 1
fi
LEGACY_CONTEXT_TOOL_PATTERN='codebase_''retrieve|codebase_''map|codebase_''grep'
if rg -n "$LEGACY_CONTEXT_TOOL_PATTERN" "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-legacy-context-retrieval.txt 2>/dev/null; then
  echo "  [FAIL] Active CP0 docs still mention obsolete context-retrieval tool names"
  cat /tmp/cp0-guards-legacy-context-retrieval.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 4: Grok Search remains external/current-only..."
if ! rg -n 'Grok Search.*external|Grok Search.*current|external.*Grok Search|current.*Grok Search' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-grok.txt 2>/dev/null; then
  echo "  [FAIL] Missing Grok Search external/current-only guidance"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 5: Active CP0 docs do not mention the legacy local tool..."
LEGACY_LOCAL_TOOL_PATTERN='Aug''gie|aug''gie'
if rg -n "$LEGACY_LOCAL_TOOL_PATTERN" "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-legacy-local-tool.txt 2>/dev/null; then
  echo "  [FAIL] Active CP0 docs still mention the legacy local tool"
  cat /tmp/cp0-guards-legacy-local-tool.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 6: Architecture diagram includes CP0 before CP1..."
if ! rg -n 'CP0: Context Acquisition.*CP1: Routing|START\[User Request\] --> CP0' "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md" >/tmp/cp0-guards-diagram.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP0 in architecture diagram"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== CP0 context acquisition guard tests passed ==="
