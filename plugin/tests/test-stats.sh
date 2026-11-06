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

# An empty wave list adds nothing to any output.
mkdir -p "$tmp/empty/docs/plans/demo"
cp "$tmp/docs/plans/demo/PLAN.md" "$tmp/empty/docs/plans/demo/PLAN.md"
sed 's/^debt:/wave_base: null\nwave: []\ndebt:/' "$tmp/docs/plans/demo/.handover.md" > "$tmp/empty/docs/plans/demo/.handover.md"
test "$(printf '{"cwd":"%s"}' "$tmp/empty" | "$stats" --statusline)" = "$line"
test "$("$stats" "$tmp/empty")" = "$("$stats" "$tmp")"

mkdir -p "$tmp/wave/docs/plans/waves"
cp "$tmp/docs/plans/demo/PLAN.md" "$tmp/wave/docs/plans/waves/PLAN.md"
cat > "$tmp/wave/docs/plans/waves/.handover.md" <<'MD'
---
status: ACTIVE
current_phase: 3
next_action: "Integrate Phase 2"
checklist: []
wave_base: abc1234
wave:
  - { phase: 2, state: implementing, worktree: /w/phase-02, branch: refract/waves/phase-02, implementation_job: j2 }
  - { phase: 3, state: integrated, worktree: null, branch: refract/waves/phase-03, implementation_job: j3 }
debt: []
---
MD
wave_line="$(printf '{"cwd":"%s"}' "$tmp/wave" | "$stats" --statusline)"
test "$wave_line" = "waves ACTIVE P3/3 debt 0 wave 2:implementing,3:integrated > Integrate Phase 2"
HOOK_OUTPUT="$(printf '{"hook_event_name":"Stop","cwd":"%s"}' "$tmp/wave" | "$stats" --hook)" python3 - <<'PY'
import json
import os

message = json.loads(os.environ["HOOK_OUTPUT"])["systemMessage"]
assert "  wave: phase 2 implementing, phase 3 integrated" in message, message
PY
"$stats" "$tmp/wave" | grep -qF '  wave: phase 2 implementing, phase 3 integrated'

printf 'stats tests passed\n'
