## User Request
Complete the confirmed mcp-v2-claude-code plan. This job implements only Phase 1.

## Phase
Heartbeat wait and progress-token probe, preserving the v1 MCP surface.

## Tasks
- task-1: Raise _MCP_WAIT_TIMEOUT_S to 3600 and introduce an injectable module-level heartbeat interval with default 30 seconds. job_wait reports progress immediately and every interval until terminal state or timeout. Every message carries the current job state. Retain v1 tool names and return shapes.
- task-2: Read the request progress token from ctx.request_context.meta. Log progress_token_present as a boolean on each job_wait request log, never the token value.
- task-3: Add deterministic tests covering several heartbeat intervals before completion, immediate terminal return, non-terminal timeout, timeout capping at 3600, cancellation cleanup, and progress token present and absent.
- task-4: Preserve the exact boolean progress_token_present field in production JSON and text logs. Preserve all other secret redaction. Never expose non-boolean values under this key. Add formatter regression tests covering true, false, rejected values, and token-value redaction. The user approved this scope extension on 2026-10-07 after a formatter reproduction confirmed the field was hidden.

## Context
Read docs/plans/mcp-v2-claude-code/PLAN.md Phase 1 and DESIGN.md waiting section. The live daemon is an editable install of this checkout but still runs the baseline code in memory. Do not restart it or call OpenMCP. The coordinator owns the live restart and six-minute probes after implementation and review.

## Files
- src/openmcp/server.py
- tests/test_server.py
- src/openmcp/logging_setup.py
- tests/test_logging.py
- docs/plans/mcp-v2-claude-code/phase-01/notes.md
- docs/plans/mcp-v2-claude-code/phase-01/journal.md

## Done When
- Heartbeats use the injectable interval and stop on completion, timeout, and cancellation.
- Tests are deterministic. Do not use sleep-based test timing.
- Terminal jobs return immediately.
- timeout_s above 3600 is capped at 3600, preserving v1 input handling.
- Both boolean values appear in production JSON and text output without exposing a token value. Non-boolean values under progress_token_present remain redacted or omitted.
- `uv run --extra dev pytest tests/test_server.py tests/test_logging.py -q`
- `uv run --extra dev pytest -q`
- Coordinator-only live acceptance remains pending and must be explicitly reported as pending, not claimed complete.

## SKILLS
- test-driven-development: /home/ngosi/projects/superpowers-ccg/skills/test-driven-development/SKILL.md
- verifying-before-completion: /home/ngosi/projects/superpowers-ccg/skills/verifying-before-completion/SKILL.md

## Rules
Follow the supplied worker contract, project conventions, and ERP format. Read existing files before editing. Change only the declared files. Do not commit, reset, stash, switch branches, edit runtime configuration, or restart services. Use mcp__auggie__codebase_retrieval for semantic code exploration and tgrep for exact code searches. Read is allowed for known paths. No other repository search tools. Maintain this phase's notes.md and journal.md. Verify any SDK behavior from installed code or current docs; use ctx7 for library documentation and tvly only for public web access. No secrets in prompts or logs.

## Response Format
Return the ERP # EXTERNAL RESPONSE block and matching status line.
