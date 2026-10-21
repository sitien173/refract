<!-- refract-shared-version: 1.2.0 -->

# Phase 1 — Decision Notes

## Task 1

### Decisions made
- Added an enabled-state synchronization before submitting the project override form; did not increase timeout or retry.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- The form's initially disabled state is asynchronous readiness, not a product-side failure.

### Follow-ups for human
- The interrupted run's systematic reproduction notes were not present on disk. On subsequent full-suite runs, the targeted test passed twice, but other intermittent tests failed, so the requested three-consecutive-suite result is not established.

### Test evidence
- Root cause evidence: a full-suite failure showed the expected API spy had zero calls after submit, and the fixture form can be mounted before form readiness; gated the click on `toBeEnabled()` rather than adding timeouts. One following full suite passed (203/203); later full runs failed unrelated tests (`Profiles` dirty draft and subsequently integration/Targets). Evidence is insufficient to claim a stable whole-suite fix.

## Task 2

### Decisions made
- Reused the existing redacted real CLI captures; no recapture was performed, per handoff.

### Spec deviations
- The exact historical invocation commands were not preserved in the partial workspace, and were not fabricated.

### Tradeoffs accepted
- none

### Assumptions
- Existing fixture structures and usage values are genuine captures as stated in the handoff.

### Follow-ups for human
- Restore exact capture command lines from the interrupted implementer's records if phase completion requires auditable command history.

### Test evidence
- Four JSONL fixtures are present under `server/tests/fixtures/usage/` and the usage parsing test consumes them.

## Task 3

### Decisions made
- Kept the existing `usage` dataclass defaults and `_normalize` pass-through implemented by the interrupted job.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Usage number values are integers; malformed string values are discarded, while model names remain strings.

### Follow-ups for human
- none

### Test evidence
- Streaming tests confirm each backend result's usage dict is preserved by `drivers._normalize`.

## Task 4

### Decisions made
- Parse only provider fields verified in the fixtures; initialize absent values to `None`; reject malformed numeric values without affecting outcome/error classification.

### Spec deviations
- none

### Tradeoffs accepted
- Codex does not expose model or context window in this captured output; Pi and Agy likewise lack context-window values.

### Assumptions
- Claude's final result `modelUsage` single entry names the active model.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: existing `test_fixture_usage_parsing` and `test_malformed_usage_never_raises` failed before backend parsing; both pass after changes. `uv run pytest -q tests/test_streaming_backends.py`: 18 passed. Full Python suite: 548 passed, 3 deselected.

### Verified backend-by-key field paths

| Backend | model_name | input_tokens | output_tokens | cached_input_tokens | context_window_max | context_window_used |
|---|---|---|---|---|---|---|
| Claude | `result.modelUsage` key | `result.usage.input_tokens` | `result.usage.output_tokens` | `result.usage.cache_read_input_tokens` | `result.modelUsage.<model>.contextWindow` | absent |
| Codex | absent | `turn.completed.usage.input_tokens` | `turn.completed.usage.output_tokens` | `turn.completed.usage.cached_input_tokens` | absent | absent |
| Pi | `message.model` | `message.usage.input` | `message.usage.output` | `message.usage.cacheRead` | absent | absent |
| Agy | absent | `result.result.usage.input_tokens` | `result.result.usage.output_tokens` | `result.result.usage.cache_read_tokens` | absent | absent |

## Coordinator Resolution

### Capture commands
The interrupted job 8c78f2c9 did not persist its command lines. The commands below are reconstructed from each backend's argv builder with no target `args`; they are not verbatim records.

| Backend | Command |
|---|---|
| claude | `claude -p --permission-mode bypassPermissions --output-format stream-json --include-partial-messages -- "Reply with OK"` |
| codex | `codex exec --cd <repo> --yolo --json -o <tmpfile> -- "Reply with OK"` |
| pi | `pi --mode json "Reply with OK"` |
| agy | `agy --dangerously-skip-permissions --output-format stream-json --log-file <tmpfile> --new-project --print "Reply with OK"` |

### Web suite stability
Coordinator ran `npx vitest run` six consecutive times after job ef1b67e3: 203/203 passed each run. The worker's intermittent failures occurred while it ran other suites in parallel; not reproduced in isolation.
