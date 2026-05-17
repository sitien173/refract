#!/usr/bin/env bash
# PreToolUse hook for Task tool — keep Task usage aligned with the 3-gate workflow

echo "Routing check: use Task for coordination, review, or exploration only. Route implementation phases by side — Codex for back-side (backend/database/system/infra), Gemini for front-side (UI/CSS/motion/multimodal), Claude for simple tasks. New features → CROSS_VALIDATION first. Run Review in the Claude main thread." >&2
