#!/usr/bin/env bash
# PreToolUse hook for Task tool - keep Task usage aligned with the CP workflow

echo "CP routing check: use Task for coordination, review, or exploration only; route implementation phases through CP1 to Codex first or Gemini for UI-heavy phases, then run CP4 Phase Review in the Claude main thread." >&2
