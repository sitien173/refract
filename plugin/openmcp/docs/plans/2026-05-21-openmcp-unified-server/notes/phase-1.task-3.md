# phase-1.task-3

## Decisions made (not in spec)
- Added `CodexParams` dataclass to type backend input (`PROMPT`, `cd`, `SESSION_ID`, `model`, `profile`).
- Preserved legacy reconnecting tolerance while classifying reconnect/rate-limit/5xx/timeout conditions as `RETRYABLE`.

## Spec deviations
- none

## Tradeoffs accepted
- Treating any frame-level JSON decode as `FATAL` can stop partially successful runs, but matches the required classification table.

## Assumptions
- `thread_id` in Codex JSON stream is the canonical `SESSION_ID` continuity identifier.

## Follow-ups for human
- none
