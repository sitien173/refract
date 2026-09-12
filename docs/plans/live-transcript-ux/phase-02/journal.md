<!-- ccg-shared-version: 10.6.0 -->

# Phase 2 — Journal: Build the conversation timeline

## META

- Plan: docs/plans/live-transcript-ux/PLAN.md
- Implementation Profile: google
- Consultation Profile: consult
- Review Profile: review
- Implementation Job: be965dbb-6a3e-426f-9882-9fd875af2800
- Review Job: 0962977e-d249-446f-bf82-446fbc9814e5
- Started: 2026-09-12T14:17:17+07:00
- Finished: 2026-09-12T14:33:00+07:00

## Implementation Response

# EXTERNAL RESPONSE
## META
- Phase: Phase 2 — Build the conversation timeline
- Started: 2026-09-12T14:17:17+07:00
- Finished: 2026-09-12T14:33:00+07:00
- Plan dir: docs/plans/live-transcript-ux/phase-02
## SUMMARY
Redesigned the live transcript into a chronological timeline with streaming assistant prose, collapsed-by-default native tool disclosure, raw payload formatting, measured TanStack virtualization, and follow-live auto-scrolling with manual pause detection and jump to live recovery.
## FILES MODIFIED
| Action | Path | Change |
| Modify | web/src/hooks/useJobStream.js | Consume data.input and data.output, match tool completions by entity_id, and preserve chronological assistant messages |
| Modify | web/src/hooks/useJobStream.test.jsx | Add unit tests for timeline ordering, interleaved tools, payloads, authoritative matching, and legacy aliases |
| Modify | web/src/components/JobTranscript.jsx | Implement ToolCallItem with native details/summary, lazy body, measured virtualization, and follow-live controls |
| Modify | web/src/components/JobTranscript.test.jsx | Add comprehensive tests for disclosure, formatting, measured virtualization, and follow-live scroll behavior |
| Modify | web/src/components/JobDetails.test.jsx | Add integration test for chronological transcript and expandable tool details in job details view |
| Modify | web/src/styles/app.css | Add styling for timeline layout, disclosure cards, monospace payloads, code wrapping, and jump button |
## NOTES
- phase-02/notes.md (## Task 1, ## Task 2, ## Task 3, ## Task 4)
## SPEC COMPLIANCE
- Meets Spec? YES — All acceptance criteria met, all verification test suites pass cleanly.
## CLARIFICATIONS NEEDED
None
## NEXT
TASK_COMPLETE

## Quality Review

# CODE QUALITY REVIEW

- Status: FAIL
- Findings:
  - High, `web/src/hooks/useJobStream.js:89-95`: Explicit tool completions can collide with another tool's call ID. Match explicit completion only by normalized entity ID.
  - High, `web/src/components/JobTranscript.jsx:184-198`: Global `measure()` clears cached sizes without synchronously remeasuring stable rows. Measure affected and mounted rows directly.
  - Medium, `web/src/components/JobTranscript.test.jsx:577-590,818-860`: Virtualization tests do not assert scrolling, changed heights, positions, reflow, or non-overlap.
  - Medium, `web/src/components/JobTranscript.test.jsx:360-573`: Add native disclosure keyboard activation coverage.
  - Medium, `web/src/components/JobTranscript.jsx:110,145-159,232-246`: Programmatic scroll marker is unused and its boundary is untested.
- Scope checked: Phase 2 frontend source and tests.

## Review Result

- Spec Status: PENDING
- Debt: none

## Final Commit

- Implementation: pending
- State record: this journal update's commit
