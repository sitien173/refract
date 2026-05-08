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
  "$REPO_ROOT/skills/executing-plans/SKILL.md"
  "$REPO_ROOT/skills/executing-plans/implementer-prompt.md"
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
  "$REPO_ROOT/skills/executing-plans/SKILL.md" \
  "$REPO_ROOT/skills/executing-plans/implementer-prompt.md" >/tmp/cp2-guards-protocol.txt 2>/dev/null; then
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
  "$REPO_ROOT/skills/executing-plans/SKILL.md" \
  "$REPO_ROOT/skills/executing-plans/implementer-prompt.md" >/tmp/cp2-guards-context-sharing.txt 2>/dev/null; then
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
  "$REPO_ROOT/skills/executing-plans/SKILL.md" \
  "$REPO_ROOT/skills/executing-plans/implementer-prompt.md" >/tmp/cp2-guards-full-context.txt 2>/dev/null; then
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
  "$REPO_ROOT/skills/executing-plans/SKILL.md" \
  "$REPO_ROOT/skills/executing-plans/implementer-prompt.md" >/tmp/cp2-guards-legacy.txt 2>/dev/null; then
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

echo "Test 7: Long prompt material is file-backed and monolithic raw prompt anti-pattern is absent..."
if ! rg -n 'file-backed|artifact file|referenced by path|read from disk|docs/plans/' \
  "$REPO_ROOT/hooks/session-start.sh" \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/context-sharing.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/INTEGRATION.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/codex-base.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/gemini-base.md" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md" \
  "$REPO_ROOT/skills/executing-plans/SKILL.md" \
  "$REPO_ROOT/skills/executing-plans/implementer-prompt.md" \
  "$REPO_ROOT/rules/bounded-tasks.mdc" >/tmp/cp2-guards-file-backed.txt 2>/dev/null; then
  echo "  [FAIL] Missing file-backed long-material CP2 guidance"
  exit 1
fi
if rg -n 'ship full report in prompt|embed full research in prompt|monolithic raw prompt (bundle|payload)|single giant prompt blob' \
  "$REPO_ROOT/hooks/session-start.sh" \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/context-sharing.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/INTEGRATION.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/codex-base.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/prompts/gemini-base.md" \
  "$REPO_ROOT/skills/shared/protocol-threshold.md" \
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md" \
  "$REPO_ROOT/skills/executing-plans/SKILL.md" \
  "$REPO_ROOT/skills/executing-plans/implementer-prompt.md" \
  "$REPO_ROOT/rules/bounded-tasks.mdc" >/tmp/cp2-guards-long-raw-antipattern.txt 2>/dev/null; then
  echo "  [FAIL] Found monolithic long raw prompt anti-pattern language"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 8: MCP failure docs require BLOCKED plus human retry/consent and reject automatic fallback/direct handling..."
if ! rg -n 'BLOCKED.*ask the human to retry|ask the human to retry|consent to an alternate route|consent to alternate route|explicit human consent after the block' \
  "$REPO_ROOT/hooks/session-start.sh" \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/rules/ccg-workflow.mdc" \
  "$REPO_ROOT/README.md" \
  "$REPO_ROOT/superpowers-ccg.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/GATE.md" \
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md" \
  "$REPO_ROOT/skills/executing-plans/SKILL.md" >/tmp/cp2-guards-blocked-consent.txt 2>/dev/null; then
  echo "  [FAIL] Missing BLOCKED + human retry/consent wording in active docs"
  exit 1
fi
if ! rg -n 'do not retry|do not switch|do not spawn|subagents?/Task/Agent fallback|do not handle implementation directly|without explicit human consent after the block' \
  "$REPO_ROOT/hooks/session-start.sh" \
  "$REPO_ROOT/hooks/user-prompt-submit.sh" \
  "$REPO_ROOT/rules/ccg-workflow.mdc" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/SKILL.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md" \
  "$REPO_ROOT/skills/coordinating-multi-model-work/GATE.md" \
  "$REPO_ROOT/skills/shared/multi-model-integration-section.md" \
  "$REPO_ROOT/skills/executing-plans/SKILL.md" >/tmp/cp2-guards-no-auto-fallback.txt 2>/dev/null; then
  echo "  [FAIL] Missing no-retry/no-switch/no-fallback/no-direct-handling guard wording"
  exit 1
fi
echo "  [PASS]"
echo ""

echo "=== CP2 external execution guard tests passed ==="
