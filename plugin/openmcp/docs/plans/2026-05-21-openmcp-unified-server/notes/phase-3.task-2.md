# phase-3.task-2

## Decisions made (not in spec)
- Used `pytest.mark.asyncio` for async tests to keep assertions direct and avoid manual `asyncio.run` wrappers.
- Verified SESSION_ID forwarding by recording the `SESSION_ID` seen by each stub invocation (`calls == ["", "sess-1"]`).

## Spec deviations
- none

## Tradeoffs accepted
- Retry test uses very small backoff (`retry_base_ms=1`) to keep suite runtime fast while still exercising retry path.

## Assumptions
- Non-existent path `C:/definitely/not/real/path` is reliably absent in this environment.

## Follow-ups for human
- none
