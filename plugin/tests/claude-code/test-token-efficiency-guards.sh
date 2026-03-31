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
  "$REPO_ROOT/skills/developing-with-subagents/SKILL.md"
  "$REPO_ROOT/skills/developing-with-subagents/implementer-prompt.md"
  "$REPO_ROOT/skills/writing-plans/SKILL.md"
)

echo "Test 1: No stale CURSOR routing in active token-path docs..."
if rg -n "\bCURSOR\b|mcp__cursor__cursor" "${TARGETS[@]}" >/tmp/token-guards-cursor.txt 2>/dev/null; then
  echo "  [FAIL] Found stale CURSOR references:"
  sed 's/^/    /' /tmp/token-guards-cursor.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 2: No prototype-then-rewrite language in active execution docs..."
if rg -n "use .*prototype|ask .*prototype|prototype first|reference implementation.*later|Claude will later rewrite|rewrite it as production|rewrite later" "${TARGETS[@]}" >/tmp/token-guards-prototype.txt 2>/dev/null; then
  echo "  [FAIL] Found prototype/rewrite language:"
  sed 's/^/    /' /tmp/token-guards-prototype.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3: Bounded-task language is present..."
if ! rg -n 'bounded task|one bounded task|one worker|diff-or-questions|Reuse.*SESSION_ID|same worker `SESSION_ID`|same worker SESSION_ID' "${TARGETS[@]}" >/tmp/token-guards-bounded.txt 2>/dev/null; then
  echo "  [FAIL] Missing bounded-task / worker ownership language"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 4: Cross-validation is explicitly rare..."
if ! rg -n 'rare|Do not use cross-validation|Before escalating to `CROSS_VALIDATION`|Use `CROSS_VALIDATION` only' "${TARGETS[@]}" >/tmp/token-guards-cross.txt 2>/dev/null; then
  echo "  [FAIL] Missing strict cross-validation limits"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== Token efficiency guard tests passed ==="
