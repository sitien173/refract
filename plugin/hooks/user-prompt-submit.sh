#!/usr/bin/env bash
# UserPromptSubmit hook for superpowers-ccg plugin

set -euo pipefail

REMINDER_TEXT="[CP Protocol Threshold (Required)]

1) Before the first Task call: output a standalone [CP1 Assessment] block (the block itself must not include tool calls)
2) Before claiming completion / requesting review / claiming verification passed: output a standalone [CP3 Assessment] block (the block itself must not include tool calls)

Note: Put the CP block first; tool calls may follow in the same assistant reply.

[CP1 Assessment]
- Task type: [Frontend/Backend/Full-stack/Other]
- Routing decision: [CLAUDE/CODEX/GEMINI/CROSS_VALIDATION]
- Rationale: ...

[CP3 Assessment]
- Task type: [Frontend/Backend/Full-stack/Other]
- Routing decision: [CLAUDE/CODEX/GEMINI/CROSS_VALIDATION]
- Rationale: ...

If unmet -> immediately perform the CP assessment, then continue the flow right away; do not stop or interrupt.
"

# Claude Code hooks event JSON is passed via stdin; UserPromptSubmit stdout is appended to context.
# Therefore we print the reminder directly and no longer rely on /tmp/prompt.json.
printf '%s\n' "$REMINDER_TEXT"
