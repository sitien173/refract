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
if ! rg -n 'stellaris.*Grok Search|Grok Search.*stellaris' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-order.txt 2>/dev/null; then
  echo "  [FAIL] Missing stellaris + Grok Search CP0 ordering"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3: Stellaris search_code role is documented..."
if ! rg -n 'stellaris.*search_code.*local|stellaris.*search_code.*semantic|stellaris.*search_code.*code context|stellaris.*search_code.*mandatory|mandatory.*stellaris' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-stellaris-role.txt 2>/dev/null; then
  echo "  [FAIL] Missing stellaris search_code local/semantic/mandatory role"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 4: Stellaris is mandatory before CP1..."
if ! rg -n 'stellaris.*(mandatory|required|[Mm][Uu][Ss][Tt])|\b(mandatory|required|MUST)\b.*stellaris' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-mandatory.txt 2>/dev/null; then
  echo "  [FAIL] Missing mandatory stellaris wording"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 5: Stellaris fail-closed BLOCKED behavior is documented..."
if ! rg -n 'stellaris.*(error|unavailable|permission-blocked|tool failure).*BLOCKED|BLOCKED.*stellaris|stop before CP1.*stellaris|stellaris.*stop before CP1' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-blocked.txt 2>/dev/null; then
  echo "  [FAIL] Missing fail-closed BLOCKED behavior for stellaris failures"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 6: Active CP0 docs do not contain fail-open skip/fallback wording..."
if rg -n -e 'skip[^[:cntrl:]\n]{0,40}stellaris' -e 'stellaris[^[:cntrl:]\n]{0,40}(when useful|optional)' -e 'fallback to[^[:cntrl:]\n]*(Grok Search|file tools|grep|glob|read tools)' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-fail-open.txt 2>/dev/null; then
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

echo "Test 8: Active CP0 docs do not mention legacy local tools..."
LEGACY_LOCAL_TOOL_PATTERN='Aug''gie|aug''gie'
if rg -n "$LEGACY_LOCAL_TOOL_PATTERN" "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-legacy-local-tool.txt 2>/dev/null; then
  echo "  [FAIL] Active CP0 docs still mention a legacy local tool"
  cat /tmp/cp0-guards-legacy-local-tool.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 9: Active CP0 docs do not reference codebase-retrieval as mandatory..."
if rg -n 'codebase-retrieval.*(mandatory|required|must)|mandatory.*codebase-retrieval|MUST.*codebase-retrieval' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-legacy-codebase-retrieval.txt 2>/dev/null; then
  echo "  [FAIL] Active CP0 docs still reference codebase-retrieval as mandatory (replaced by stellaris)"
  cat /tmp/cp0-guards-legacy-codebase-retrieval.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 10: Architecture diagram includes CP0 before CP1..."
if ! rg -n 'CP0: Context Acquisition.*CP1: Routing|START\[User Request\] --> CP0' "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md" >/tmp/cp0-guards-diagram.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP0 in architecture diagram"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 11: Stellaris drill-down tools documented..."
if ! rg -n 'get_file_outline|get_file_folded|get_symbol' "${ACTIVE_CP0_TARGETS[@]}" >/tmp/cp0-guards-stellaris-drilldown.txt 2>/dev/null; then
  echo "  [FAIL] Missing stellaris drill-down tools (get_file_outline/get_file_folded/get_symbol)"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== CP0 context acquisition guard tests passed ==="
