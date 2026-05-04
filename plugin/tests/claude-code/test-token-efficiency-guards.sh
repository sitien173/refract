#!/usr/bin/env bash
# Test: static token-efficiency guardrails remain in workflow docs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Test: token efficiency guards ==="
echo ""

TARGETS=(
  "$REPO_ROOT/hooks/user-prompt-submit.sh"
  "$REPO_ROOT/skills/shared/protocol-threshold.md"
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/INTEGRATION.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/cross-validation.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/codex-base.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/gemini-base.md"
  "$REPO_ROOT/skills/executing-phases/SKILL.md"
  "$REPO_ROOT/skills/executing-phases/implementer-prompt.md"
  "$REPO_ROOT/skills/writing-plans/SKILL.md"
)

echo "Test 2: No prototype-then-rewrite language in active execution docs..."
if rg -n "use .*prototype|ask .*prototype|prototype first|reference implementation.*later|Claude will later rewrite|rewrite it as production|rewrite later" "${TARGETS[@]}" >/tmp/token-guards-prototype.txt 2>/dev/null; then
  echo "  [FAIL] Found prototype/rewrite language:"
  sed 's/^/    /' /tmp/token-guards-prototype.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3: Phase-scoped and 3-tier language is present..."
if ! rg -n 'implementation phase|one phase|one primary executor|External Response Protocol v1\.1|SESSION_ID|SESSION_POLICY|Tier 1|Tier 2|Tier 3|Done When|HYDRATED_CONTEXT.*300|deltas only|300 tokens' "${TARGETS[@]}" >/tmp/token-guards-bounded.txt 2>/dev/null; then
  echo "  [FAIL] Missing phase / executor ownership / 3-tier prompt language"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3b: No stale budget numbers in active docs..."
if rg -n '2500 tokens|<= 800 tokens|1000 tokens' \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/hooks/session-start.sh" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/INTEGRATION.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/context-sharing.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/codex-base.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/gemini-base.md" \
  "$REPO_ROOT/rules/bounded-tasks.mdc" >/tmp/token-guards-stale-budget.txt 2>/dev/null; then
  echo "  [FAIL] Found stale budget numbers (2500/800/1000):"
  sed 's/^/    /' /tmp/token-guards-stale-budget.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3c: SESSION_POLICY present in routing docs..."
if ! rg -n 'Session-Policy|SESSION_POLICY' \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/routing-decision.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" >/tmp/token-guards-session-policy.txt 2>/dev/null; then
  echo "  [FAIL] SESSION_POLICY missing from routing docs"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3d: Worker templates use Done When, not separate Reviewer Checklist..."
if rg -n '## Reviewer Checklist|## Integration Checks|## Success Criteria' \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/codex-base.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/gemini-base.md" >/tmp/token-guards-old-sections.txt 2>/dev/null; then
  echo "  [FAIL] Found old sections in worker templates:"
  sed 's/^/    /' /tmp/token-guards-old-sections.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 4: Full CONTEXT_PACKAGE repetition is absent from active execution docs..."
if rg -n 'full `CONTEXT_PACKAGE`|FULL CONTEXT_PACKAGE|## Context Package' \
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/INTEGRATION.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/codex-base.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/gemini-base.md" \
  "$REPO_ROOT/skills/executing-phases/SKILL.md" \
  "$REPO_ROOT/skills/executing-phases/implementer-prompt.md" >/tmp/token-guards-context.txt 2>/dev/null; then
  echo "  [FAIL] Found stale full CONTEXT_PACKAGE repetition"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 5: Cross-validation is explicitly rare..."
if ! rg -n 'rare|Do not use cross-validation|Before escalating to `CROSS_VALIDATION`|Use `CROSS_VALIDATION` only' "${TARGETS[@]}" >/tmp/token-guards-cross.txt 2>/dev/null; then
  echo "  [FAIL] Missing strict cross-validation limits"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== Token efficiency guard tests passed ==="
