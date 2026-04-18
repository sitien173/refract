#!/usr/bin/env bash
# Test: static CP2 external execution guardrails remain aligned
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Test: CP2 external execution guards ==="
echo ""

TARGETS=(
  "$REPO_ROOT/hooks/session-start.sh"
  "$REPO_ROOT/hooks/user-prompt-submit.sh"
  "$REPO_ROOT/skills/shared/protocol-threshold.md"
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/INTEGRATION.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/codex-base.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/gemini-base.md"
  "$REPO_ROOT/skills/developing-with-subagents/SKILL.md"
  "$REPO_ROOT/skills/developing-with-subagents/implementer-prompt.md"
  "$REPO_ROOT/README.md"
  "$REPO_ROOT/superpowers-ccg.md"
  "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md"
)

echo "Test 1: CP2 is explicitly named External Execution..."
if ! rg -n 'CP2: External Execution|CP2 \(External Execution\)|External execution' "${TARGETS[@]}" >/tmp/cp2-guards-name.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP2 External Execution language"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 2: External Response Protocol v1.1 exists in active execution docs..."
if ! rg -n '^# EXTERNAL RESPONSE PROTOCOL v1\.1|External Response Protocol v1\.1|^## FILES MODIFIED|^## CONTEXT ARTIFACTS|edit files directly via MCP|MCP write tools' \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/INTEGRATION.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/codex-base.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/gemini-base.md" \
  "$REPO_ROOT/skills/developing-with-subagents/SKILL.md" \
  "$REPO_ROOT/skills/developing-with-subagents/implementer-prompt.md" >/tmp/cp2-guards-protocol.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP2 external response protocol language"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 3: Smart context-sharing prompt structure exists in active execution docs..."
if ! rg -n '## Task Context Bundle|## Context Refs|## Hydrated Context|TASK_CONTEXT_BUNDLE|CONTEXT_REFS|HYDRATED_CONTEXT|send deltas only|deltas only' \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/INTEGRATION.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/codex-base.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/gemini-base.md" \
  "$REPO_ROOT/skills/developing-with-subagents/SKILL.md" \
  "$REPO_ROOT/skills/developing-with-subagents/implementer-prompt.md" >/tmp/cp2-guards-context-sharing.txt 2>/dev/null; then
  echo "  [FAIL] Missing smart context-sharing execution contract"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 4: Full CONTEXT_PACKAGE prompts are absent from active execution docs..."
if rg -n 'full `CONTEXT_PACKAGE`|FULL CONTEXT_PACKAGE|## Context Package' \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/INTEGRATION.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/codex-base.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/gemini-base.md" \
  "$REPO_ROOT/skills/developing-with-subagents/SKILL.md" \
  "$REPO_ROOT/skills/developing-with-subagents/implementer-prompt.md" >/tmp/cp2-guards-full-context.txt 2>/dev/null; then
  echo "  [FAIL] Found stale full CONTEXT_PACKAGE execution contract"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 5: Legacy diff-or-questions contract is absent from active execution docs..."
if rg -n 'diff-or-questions|## DIFF|## QUESTIONS|patch-ready diff|blocking questions' \
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/INTEGRATION.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/codex-base.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/gemini-base.md" \
  "$REPO_ROOT/skills/developing-with-subagents/SKILL.md" \
  "$REPO_ROOT/skills/developing-with-subagents/implementer-prompt.md" >/tmp/cp2-guards-legacy.txt 2>/dev/null; then
  echo "  [FAIL] Found legacy CP2 execution contract language"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 6: Diagram labels CP2 as External Execution..."
if ! rg -n 'CP2\[CP2: External Execution\]' "$REPO_ROOT/docs/diagrams/ccg-workflow-architecture.md" >/tmp/cp2-guards-diagram.txt 2>/dev/null; then
  echo "  [FAIL] Missing CP2 External Execution label in diagram"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== CP2 external execution guard tests passed ==="
