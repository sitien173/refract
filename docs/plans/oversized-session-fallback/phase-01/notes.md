<!-- ccg-shared-version: 11.0.1 -->

# Phase 1 - Decision Notes

## Task 1

### Decisions made
- Use the captured `context_length_exceeded` provider code as the canonical overflow signature.
- Represent the captured assistant payload through existing Pi `message_end` fixture conventions using a neutral synthetic session identifier.

### Spec deviations
- none

### Tradeoffs accepted
- Numeric estimates and account-specific details remain sanitized.

### Assumptions
- The persisted Pi assistant record matches the message payload emitted by JSON mode.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_pi_context_overflow_real_trace` initially failed with `AssertionError: assert 'no_agent_messages' == 'context_overflow'`; passed after implementing `_extract_output` structured error capture and `_is_context_overflow` classification.
- Root cause (bugfix only): Pi assistant `stopReason` and `errorMessage` were discarded during event parsing.

## Task 2

### Decisions made
- Extract `stopReason == "error"` and string `errorMessage` from `message_end` and `agent_end` messages in `pi._extract_output`.
- Return structured error from `_extract_output` and enforce failure even when partial assistant text is present.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_pi_structured_assistant_error_with_partial_content_is_fatal` failed with `AssertionError: assert 'OK' == 'FATAL'`; passed after enforcing `outcome = "FATAL"` when structured error is present.
- Root cause (bugfix only): `classify_backend_output` returned `OK` on non-empty `agent_messages` regardless of structured errors.

## Task 3

### Decisions made
- Match exact delimited regex token `\bcontext_length_exceeded\b` within diagnostic material only (`error_text`), avoiding case-insensitive substring matching.
- Verify negative cases for generic strings ("too long", "context error", "prompt too long", "maximum tokens exceeded"), boundary variations ("prefix_context_length_exceeded_suffix", "notcontext_length_exceeded", "context_length_exceededly"), case variations ("CONTEXT_LENGTH_EXCEEDED", "Context_Length_Exceeded"), and normal assistant prose.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- Final signatures derived directly from sanitized real trace `context_length_exceeded`.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_pi_is_context_overflow_boundary_and_case` initially failed with `AssertionError: assert True is False` on `prefix_context_length_exceeded_suffix`; passed after replacing substring check with exact delimited `\bcontext_length_exceeded\b` regex. Verified boundary and case negatives via `test_pi_boundary_and_case_negative_overflow_cases`.
- Root cause (bugfix only): `_is_context_overflow` used case-insensitive substring matching `any(sig in lowered)` which falsely matched boundary extensions and case variations.

## Task 4

### Decisions made
- Enforce strict error precedence: cancellation (`cancelled`) > confirmed overflow (`context_overflow`) > fatal backend (`fatal_backend`) > other structured assistant failures (`execution_error`) > ordinary process failures (`execution_error`).
- Ensure context overflow overrides generic `execution_error` on nonzero exit codes with partial output.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_pi_overflow_overrides_nonzero_exit_and_partial_output` failed with `AssertionError: assert 'execution_error' == 'context_overflow'`; passed after placing context overflow check before generic shell command error handling.
- Root cause (bugfix only): Generic `command_error` overrode backend classification with `execution_error`.

## Task 5

### Decisions made
- Preserve `DriverResult.outcome = RETRYABLE` and `DriverResult.error_code = context_overflow` for `BackendResult.error_class = context_overflow`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_pi_driver_normalizes_context_overflow_to_retryable` passed directly against `openmcp.drivers._normalize`.
- Root cause (bugfix only): none

## Task 6

### Decisions made
- Expose minimal `has_tool_activity` property on `StreamBridge` backed by thread-safe `threading.Event`, setting it when `event["kind"] == "tool.started"`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `test_stream_bridge_tool_activity_tracking` failed with `AttributeError: 'StreamBridge' object has no attribute 'has_tool_activity'`; passed after adding `_tool_activity` and `has_tool_activity` to `StreamBridge`.
- Root cause (bugfix only): none
