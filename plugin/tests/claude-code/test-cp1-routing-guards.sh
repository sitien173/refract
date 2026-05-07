#!/usr/bin/env bash
# Test: static CP1 routing guardrails remain aligned
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Test: CP1 routing guards ==="
echo ""

TARGETS=(
  "$REPO_ROOT/hooks/user-prompt-submit.sh"
  "$REPO_ROOT/skills/shared/protocol-threshold.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/routing-decision.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md"
  "$REPO_ROOT/README.md"
  "$REPO_ROOT/superpowers-ccg.md"
  "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md"
)

echo "Test 1: CP1 is explicitly named Phase Assessment & Routing..."
if ! rg -n 'CP1: Phase Assessment & Routing|CP1 \(Phase Assessment & Routing\)|Phase assessment and routing' "${TARGETS[@]}" >/tmp/cp1-guards-name.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP1 Phase Assessment & Routing language"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 2: Exact CP1 routing block exists in the injected docs..."
if ! rg -n '^# CP1 ROUTING DECISION|^## Task Summary|^## Route|Model: Gemini / Codex / Cross-Validation \(Codex \+ Gemini\) / Claude|Cross-Validation: Yes / No|^## Next Action' \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" >/tmp/cp1-guards-block.txt 2>/dev/null; then
  echo "  [FAIL] Missing exact CP1 routing decision block"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3: Legacy CP1 formats are absent from active docs..."
if rg -n '^\[CP1 Assessment\]$|^\[CP1\] Routing:' \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/routing-decision.md" >/tmp/cp1-guards-legacy.txt 2>/dev/null; then
  echo "  [FAIL] Found legacy CP1 format references in active docs"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 4: CP1 routing matrices are embedded in active docs..."
if ! rg -n '^\| Task Category \| Examples \| CP0 Context Tools \| Model \| Cross-Validation \| Notes / Triggers \|$' \
  "$REPO_ROOT/skills/coordinating-multi-model-work/routing-decision.md" >/tmp/cp1-guards-routing-csv.txt 2>/dev/null; then
  echo "  [FAIL] Detailed CP1 routing matrix is missing"
  exit 1
fi
if ! rg -n '^\| Task Category \| Model \| Cross-Validation \| Notes / Triggers \|$|Backend / Logic / API \| Codex \| No \||UI components / CSS / animation / canvas / SVG \| Gemini \| No \||Multimodal input -> code \| Gemini \| No \||Large-context sweep \(>200K tokens\) \| Gemini \| No \||Security / compliance / legal-sensitive code \| Codex \| No \(mandatory Claude review gate\) \||Uncategorized / Ambiguous \| Claude \| No \|' \
  "$REPO_ROOT/skills/coordinating-multi-model-work/routing-decision.md" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" >/tmp/cp1-guards-cp1-csv.txt 2>/dev/null; then
  echo "  [FAIL] Compact CP1 routing guide is missing or out of sync"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 5: Diagram labels CP1 as Phase Assessment & Routing..."
if ! rg -n 'CP1\[CP1: Phase Assessment & Routing\]' "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md" >/tmp/cp1-guards-diagram.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP1 Phase Assessment & Routing label in diagram"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 6: Tiebreaker and New Routing Axes sections exist in routing decision..."
if ! rg -n '^## Tiebreaker Order$' "$REPO_ROOT/skills/coordinating-multi-model-work/routing-decision.md" >/tmp/cp1-guards-tiebreaker-section.txt 2>/dev/null; then
  echo "  [FAIL] Missing Tiebreaker Order section in routing-decision.md"
  exit 1
fi
if ! rg -n '^## New Routing Axes$' "$REPO_ROOT/skills/coordinating-multi-model-work/routing-decision.md" >/tmp/cp1-guards-new-axes-section.txt 2>/dev/null; then
  echo "  [FAIL] Missing New Routing Axes section in routing-decision.md"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 7: Tiebreaker priority text is present in routing decision..."
if ! rg -n 'Hallucination-sensitive|Multimodal input present|Context >200K|UI-dominant' "$REPO_ROOT/skills/coordinating-multi-model-work/routing-decision.md" >/tmp/cp1-guards-tiebreaker-priority.txt 2>/dev/null; then
  echo "  [FAIL] Missing tiebreaker priority text in routing-decision.md"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 8: Canonical compact matrix is synced to hook script..."
if ! rg -n 'Multimodal input -> code \| Gemini' "$REPO_ROOT/hooks/user-prompt-submit.sh" >/tmp/cp1-guards-hook-sync.txt 2>/dev/null; then
  echo "  [FAIL] Hook script compact matrix is missing canonical Multimodal row"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== CP1 routing guard tests passed ==="
