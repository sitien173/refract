# Phase 1: Notifications config and dependency

## User Request
Complete desktop-notifications according to the confirmed DESIGN.md and PLAN.md.

## Phase
Add the required notify-py dependency and strict global notifications config. No runtime changes.

## Tasks
Follow Phase 1 tasks, acceptance criteria, reviewer checklist, and verification checks in `/home/ngosi/projects/openmcp/docs/plans/desktop-notifications/PLAN.md` exactly.
1. Add notify-py>=0.3.43,<0.4 to runtime dependencies and update uv.lock without unrelated upgrades.
2. Add frozen slotted NotificationsConfig, defaulted DaemonConfig.notifications, strict _notifications_config parsing, and allow the global table.
3. Test absent and empty tables, true and false flags, unknown keys, non-bool values including integer 1, non-table values, and project config rejection.

## Context
Read `/home/ngosi/projects/openmcp/docs/plans/desktop-notifications/DESIGN.md` and Phase 1 of PLAN.md. Mirror the existing _logging_config validation pattern. Existing constructor call sites must continue working.

## Files
- pyproject.toml
- uv.lock
- src/openmcp/config.py
- tests/test_config.py
- docs/plans/desktop-notifications/phase-01/notes.md
- docs/plans/desktop-notifications/phase-01/journal.md

## Done When
All Phase 1 acceptance criteria hold, and these fresh commands pass:
- `uv run python -c "from notifypy import Notify"`
- `uv run pytest tests/test_config.py -q`
- `uv run pytest -q`

## SKILLS
- TDD: `/home/ngosi/projects/superpowers-ccg/skills/test-driven-development/SKILL.md`
- Verification: `/home/ngosi/projects/superpowers-ccg/skills/verifying-before-completion/SKILL.md`

## Rules
Read existing files before editing. Use Auggie semantic retrieval and tgrep exact search for code exploration, with Read only for known paths. No grep, find, cat, ls, generic filesystem exploration, or other search tools. Stay within the listed files. Do not edit handover, prompts, Git, dashboard, or runtime. Do not read secrets or local credential/config files outside the declared source/test scope. For behavioral changes, record genuine intended-behavior RED before production code, then GREEN. Do not treat import errors as RED. Maintain per-task notes and append the ERP block to the journal. Coordinator owns commits and handover.

## Response Format
Return the ERP # EXTERNAL RESPONSE block and matching status line.
