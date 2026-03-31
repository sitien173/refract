#!/usr/bin/env bash
# UserPromptSubmit hook for superpowers-ccg plugin

set -euo pipefail

REMINDER_TEXT="[CP Protocol Threshold]

Before the first Task call, output a short standalone [CP1 Assessment] block.
Before claiming completion, output a short standalone [CP3 Assessment] block.

Use the minimal format below. Do not add extra narration to the checkpoint itself.

[CP1 Assessment]
- Task type: [Frontend/Backend/Full-stack/Other]
- Complexity: [Trivial/Standard/Critical]
- Routing decision: [CLAUDE/CODEX/GEMINI/CROSS_VALIDATION]
- Rationale: [one sentence]

Compact trivial form:
[CP1] Routing: CLAUDE | Trivial: <reason>

[CP3 Assessment]
- Task type: [Frontend/Backend/Full-stack/Other]
- Routing decision: [CLAUDE/CODEX/GEMINI/CROSS_VALIDATION]
- Rationale: [one sentence]

Compact trivial form:
[CP3] Verified: <evidence>
"

printf '%s\n' "$REMINDER_TEXT"
