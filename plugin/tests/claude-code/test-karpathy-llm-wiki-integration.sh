#!/usr/bin/env bash
# Test: Karpathy LLM wiki skill and CP0 integration guardrails
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

SKILL="$REPO_ROOT/skills/karpathy-llm-wiki/SKILL.md"
WIKI_REFS="$REPO_ROOT/skills/karpathy-llm-wiki/references"
CP0_TARGETS=(
  "$REPO_ROOT/hooks/session-start.sh"
  "$REPO_ROOT/hooks/user-prompt-submit.sh"
  "$REPO_ROOT/superpowers-ccg.md"
  "$REPO_ROOT/rules/ccg-workflow.mdc"
  "$REPO_ROOT/rules/bounded-tasks.mdc"
  "$REPO_ROOT/skills/shared/protocol-threshold.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/checkpoints.md"
  "$REPO_ROOT/skills/coordinating-multi-model-work/context-sharing.md"
)

DOC_TARGETS=(
  "$REPO_ROOT/README.md"
  "$REPO_ROOT/tests/claude-code/README.md"
)

echo "=== Test: Karpathy LLM wiki integration ==="
echo ""

echo "Test 1: Bundled skill and templates exist..."
for file in \
  "$SKILL" \
  "$WIKI_REFS/raw-template.md" \
  "$WIKI_REFS/article-template.md" \
  "$WIKI_REFS/index-template.md" \
  "$WIKI_REFS/archive-template.md"; do
  if [ ! -f "$file" ]; then
    echo "  [FAIL] Missing $file"
    exit 1
  fi
done
echo "  [PASS]"
echo ""

echo "Test 2: Skill metadata and trigger wording are discoverable..."
if ! rg -n 'name: karpathy-llm-wiki' "$SKILL" >/tmp/wiki-skill-name.txt 2>/dev/null; then
  echo "  [FAIL] Missing skill name"
  exit 1
fi
for trigger in 'LLM wiki' 'Karpathy wiki' 'ingest' 'add to wiki' 'what do we know' 'lint wiki'; do
  if ! rg -n "$trigger" "$SKILL" >/tmp/wiki-trigger.txt 2>/dev/null; then
    echo "  [FAIL] Missing trigger: $trigger"
    exit 1
  fi
done
echo "  [PASS]"
echo ""

echo "Test 3: Skill is constrained to ingest/query/lint and docs/wiki storage..."
if ! rg -n 'exactly three operations' "$SKILL" >/tmp/wiki-three-ops.txt 2>/dev/null; then
  echo "  [FAIL] Missing exactly-three-operations constraint"
  exit 1
fi
for op in 'Operation: ingest' 'Operation: query' 'Operation: lint'; do
  if ! rg -n "$op" "$SKILL" >/tmp/wiki-operation.txt 2>/dev/null; then
    echo "  [FAIL] Missing operation: $op"
    exit 1
  fi
done
if ! rg -n 'docs/wiki/|docs/wiki/raw/' "$SKILL" "$WIKI_REFS"/*.md >/tmp/wiki-docs-paths.txt 2>/dev/null; then
  echo "  [FAIL] Missing docs/wiki path usage"
  exit 1
fi
if rg -n '(^|[[:space:]])`(raw|wiki)/|(^|[[:space:]])(raw|wiki)/[<A-Za-z0-9_-]' "$SKILL" "$WIKI_REFS"/*.md >/tmp/wiki-top-level-paths.txt 2>/dev/null; then
  echo "  [FAIL] Found top-level raw/wiki storage path"
  cat /tmp/wiki-top-level-paths.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 4: Ingest, query, and lint behavior guardrails exist..."
for pattern in \
  'Never overwrite existing wiki files' \
  'Ingest is incomplete unless both source capture and wiki compilation happen' \
  'immutable after ingest' \
  'wiki has not been initialized' \
  'run an ingest first' \
  'Cite each factual claim' \
  'Deterministic auto-fixes' \
  'Heuristic report-only findings'; do
  if ! rg -n "$pattern" "$SKILL" >/tmp/wiki-behavior.txt 2>/dev/null; then
    echo "  [FAIL] Missing behavior guard: $pattern"
    exit 1
  fi
done
echo "  [PASS]"
echo ""

echo "Test 5: CP0 wiki lookup is selective, advisory, and budget-safe..."
for pattern in \
  'Selectively consult `docs/wiki/`|selective `docs/wiki/`' \
  'Skip wiki lookup for trivial edits' \
  'wiki/relevant' \
  'wiki/decisions' \
  'wiki/conflicts' \
  'wiki/sources' \
  'advisory and citation-backed' \
  'current files.*override|current files, tests, and current user request override' \
  'never full `docs/wiki/` pages|No full CP0 discovery blobs or full `docs/wiki/` dumps' \
  'HYDRATED_CONTEXT.*300'; do
  if ! rg -n "$pattern" "${CP0_TARGETS[@]}" >/tmp/wiki-cp0.txt 2>/dev/null; then
    echo "  [FAIL] Missing CP0 guard: $pattern"
    exit 1
  fi
done
if rg -n 'always (read|consult|query|check) `?docs/wiki|must (read|consult|query|check) `?docs/wiki' "${CP0_TARGETS[@]}" >/tmp/wiki-always-on.txt 2>/dev/null; then
  echo "  [FAIL] CP0 wording implies always-on wiki lookup"
  cat /tmp/wiki-always-on.txt
  exit 1
fi
echo "  [PASS]"
echo ""

echo "Test 6: User-facing docs describe workflow and authority rule..."
for pattern in \
  'docs/wiki/' \
  'ingest' \
  'query' \
  'lint' \
  'current.*files.*win|current-code-wins|current files.*override'; do
  if ! rg -n "$pattern" "${DOC_TARGETS[@]}" >/tmp/wiki-docs.txt 2>/dev/null; then
    echo "  [FAIL] Missing docs pattern: $pattern"
    exit 1
  fi
done
echo "  [PASS]"
echo ""

echo "=== Karpathy LLM wiki integration guards passed ==="
