#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
stats="${repo_root}/scripts/refract-stats"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

mkdir -p "$tmp/docs/plans/demo" "$tmp/docs/plans/old" "$tmp/src"
cat > "$tmp/docs/plans/demo/PLAN.md" <<'MD'
### Phase 1: One
### Phase 2: Two
### Phase 3: Three
MD
cat > "$tmp/docs/plans/demo/.handover.md" <<'MD'
---
status: ACTIVE
topic: Demo
current_phase: 2
next_action: "Execute Phase 2"
checklist:
  - { phase: 2, step: "Submit implement job", status: done }
  - { phase: 2, step: "Spec review, round 1", status: doing }
  - { phase: 2, step: "Quality review", status: todo }
completed_tasks: []
debt: [{ phase: 1, item: "Low: x", owner: "c" }]
---
MD
printf -- '---\nstatus: DONE\ncurrent_phase: 1\nchecklist: []\ndebt: []\n---\n' > "$tmp/docs/plans/old/.handover.md"

line="$(printf '{"workspace":{"current_dir":"%s/src"}}' "$tmp" | "$stats" --statusline)"
test "$line" = "demo ACTIVE P2/3 1/3 [Spec review, round 1] debt 1 > Execute Phase 2"

check_hook() {
    HOOK_OUTPUT="$1" python3 - <<'PY'
import json
import os

message = json.loads(os.environ["HOOK_OUTPUT"])["systemMessage"]
assert "demo: ACTIVE, phase 2/3, checklist 1/3 done, debt 1" in message
assert "doing: Spec review, round 1" in message
assert "old" not in message
PY
}

check_hook "$(printf '{"hook_event_name":"Stop","cwd":"%s"}' "$tmp" | "$stats" --hook)"
check_hook "$(printf '{"hook_event_name":"PostToolUse","cwd":"%s","tool_input":{"file_path":"%s/docs/plans/demo/.handover.md"}}' "$tmp" "$tmp" | "$stats" --hook)"
test -z "$(printf '{"hook_event_name":"PostToolUse","cwd":"%s","tool_input":{"file_path":"a.py"}}' "$tmp" | "$stats" --hook)"
test -z "$(printf '{"hook_event_name":"Stop","stop_hook_active":true,"cwd":"%s"}' "$tmp" | "$stats" --hook)"
test -z "$(cd / && printf '{"cwd":"/"}' | "$stats" --statusline)"

printf 'stats tests passed\n'
