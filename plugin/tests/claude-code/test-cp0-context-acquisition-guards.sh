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

echo "Test 4: codebase-retrieval is mandatory before CP1..."
if ! rg -n 'codebase-retrieval.*(mandatory|required|must)|\b(mandatory|required|must)\b.*codebase-retrieval' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-mandatory.txt 2>/dev/null; then
  echo "  [FAIL] Missing mandatory codebase-retrieval wording"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 5: codebase-retrieval fail-closed BLOCKED behavior is documented..."
if ! rg -n 'codebase-retrieval.*(error|unavailable|permission-blocked|tool failure).*BLOCKED|BLOCKED.*codebase-retrieval|stop before CP1.*codebase-retrieval|codebase-retrieval.*stop before CP1' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-blocked.txt 2>/dev/null; then
  echo "  [FAIL] Missing fail-closed BLOCKED behavior for codebase-retrieval failures"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 6: Active CP0 docs do not contain fail-open skip/fallback wording..."
if rg -n -e 'skip[^[:cntrl:]\n]{0,40}context-retrieval' -e 'context-retrieval[^[:cntrl:]\n]{0,40}(when useful|optional)' -e 'fallback to[^[:cntrl:]\n]*(Grok Search|file tools|grep|glob|read tools)' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-fail-open.txt 2>/dev/null; then
  echo "  [FAIL] Active CP0 docs contain fail-open skip/fallback wording"
  cat /tmp/cp0-guards-fail-open.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 7: Grok Search remains external/current-only..."
if ! rg -n 'Grok Search.*external|Grok Search.*current|external.*Grok Search|current.*Grok Search' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-grok.txt 2>/dev/null; then
  echo "  [FAIL] Missing Grok Search external/current-only guidance"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 8: Active CP0 docs do not mention the legacy local tool..."
LEGACY_LOCAL_TOOL_PATTERN='Aug''gie|aug''gie'
if rg -n "$LEGACY_LOCAL_TOOL_PATTERN" "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-legacy-local-tool.txt 2>/dev/null; then
  echo "  [FAIL] Active CP0 docs still mention the legacy local tool"
  cat /tmp/cp0-guards-legacy-local-tool.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 9: Architecture diagram includes CP0 before CP1..."
if ! rg -n 'CP0: Context Acquisition.*CP1: Routing|START\[User Request\] --> CP0' "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md" >/tmp/cp0-guards-diagram.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP0 in architecture diagram"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 10: Stellaris is documented as optional secondary CP0 source..."
if ! rg -n 'stellaris.*optional|optional.*stellaris|stellaris.*secondary|secondary.*stellaris|stellaris.*parallel|parallel.*stellaris' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-stellaris.txt 2>/dev/null; then
  echo "  [FAIL] Missing stellaris as optional/secondary/parallel CP0 source"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 11: Stellaris failure is explicitly non-blocking..."
if ! rg -n 'stellaris.*NOT.*BLOCKED|[Ss]tellaris failure.*non-blocking|[Ss]tellaris failure does NOT' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-stellaris-nonblocking.txt 2>/dev/null; then
  echo "  [FAIL] Missing stellaris non-blocking failure documentation"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== CP0 context acquisition guard tests passed ==="
