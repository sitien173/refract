# Phase 2 — SessionStart hook extension

- Status: DONE
- Owner: Codex
- Started: 2026-05-17
- Finished: 2026-05-17

## Route
- Reason: back-side shell script extending existing hook
- Done When:
  - `bash hooks/session-start.sh` exits 0 with no active plan (static context still injected)
  - With mock `docs/plans/_resume_test/.handover.md` containing `status: ACTIVE`, hook output JSON's `additionalContext` includes `<RESUME>` block with parsed fields
  - Tolerates missing `.sessions.json` (reports `absent`)
- Files:
  - `hooks/session-start.sh`

## Files Modified
| Action  | Path                       | Change |
|---------|----------------------------|--------|
| Edited  | hooks/session-start.sh     | Added `extract_frontmatter_value` + `build_resume_context` functions; walks `docs/plans/*/.handover.md`, picks newest ACTIVE by mtime, extracts `plan`/`current_phase`/`owner`/`next_action`/`read_first`, reports `.sessions.json` codex/gemini presence, appends `<RESUME>` block to `additionalContext`. Fail-soft on any error. |

## Review
- Spec Status: PASS — RESUME block emitted with expected fields; static context preserved; sessions correctly reported `absent` when file missing.
- Quality Findings:

| Severity | path:line | Problem | Fix |
|----------|-----------|---------|-----|
| LOW | hooks/session-start.sh:144 | `read_first` awk prints blank lines under section verbatim | Cosmetic only; could `if (line != "") print line` |
| LOW | hooks/session-start.sh:188 | `${resume_escaped:+\n${resume_escaped}}` relies on unquoted-heredoc `\n` literal semantics — works but subtle | Could split var assembly out; not required |

- Final Status: PASS

## Decisions
- Use `ls -1t` + glob, not `find`: Git-Bash on Windows portable; no extra deps.
- Frontmatter parsing via awk, not jq: shell-only constraint met.
- `.sessions.json` presence detection via grep for `"codex":` + non-null check: avoids JSON parser dependency.
- Fail-soft `|| true` around `build_resume_context`: any parse error degrades to static-only output, never breaks session start.

## Handoff
Phase 3 (Claude direct): create example artifacts under `docs/plans/2026-05-17-session-resume/` (PLAN, PHASE-1, PHASE-2, .handover) and verify the hook detects the active handover by running it directly in this session.
