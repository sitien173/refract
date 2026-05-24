# phase-1.task-2 decision note

## Decisions made (not in spec)
- Added a small shared helper (`_assert_live_result`) to keep both live tests consistent.
- Skip reasons are prefixed with backend name (`agy`/`codex`) for clearer pytest output.

## Spec deviations
- none

## Tradeoffs accepted
- The helper accepts an untyped backend result object to avoid introducing extra protocol/typing boilerplate in tests.

## Assumptions
- For successful live runs, marker extraction is functioning and returns non-empty `SESSION_ID`.

## Follow-ups for human
- none