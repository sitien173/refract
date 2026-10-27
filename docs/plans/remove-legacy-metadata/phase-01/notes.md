<!-- refract-shared-version: 2.0.0 -->

# Phase 1 Decision Notes

Append one task block per task. Preserve earlier evidence.

## Task 1

### Decisions made
- Added strict, extra-forbid grouped Pydantic models and exact public telemetry keys. The failure enum matches all failure kinds currently emitted by execution.

### Spec deviations
- none

### Tradeoffs accepted
- Reused Measurement and TelemetryData rather than changing their existing accumulator/runtime behavior.

### Assumptions
- Strict canonical values use the existing telemetry source and quality rules.

### Follow-ups for human
- none

### Test evidence
- The first test invocation failed at collection because the new module did not yet exist (not counted as behavioral RED). Final focused tests: 29 passed, including strict aliases, extras, boolean/negative values, enums, unavailable defaults, and timestamp requirement.

## Task 2

### Decisions made
- Added a named explicit projection function, returning only the public seven measurements and completeness; internal TelemetryData remains separate.

### Spec deviations
- No changes to telemetry.py were required; projection is implemented alongside the canonical public contract.

### Tradeoffs accepted
- Kept accumulator and internal TelemetryData untouched to avoid altering accounting semantics.

### Assumptions
- Phase 2 callers will explicitly persist/use the separate internal TelemetryData result.

### Follow-ups for human
- none

### Test evidence
- RED: `cd server && uv run --extra dev python -m pytest tests/test_result_metadata.py::test_canonical_valued_measurement_requires_observation_time -q` -> failed as intended: “DID NOT RAISE ValidationError”.
- GREEN: same focused suite after implementation -> 29 passed; projection test verifies internal version, attribution, and completed-attempt fields are absent.

## Task 3

### Decisions made
- Converter accepts metadata itself, recognizes only documented flat fields plus `metadata.telemetry`, returns `(JobResultMetadata, TelemetryData)`, drops obsolete/unknown public fields and retry tokens, and checks historical timestamps before TelemetryData can fill them.
- Schema-15 legacy-only values are validated but never interpreted as normalized telemetry.

### Spec deviations
- none

### Tradeoffs accepted
- Internal historical telemetry is validated by the existing TelemetryData model; unknown telemetry extension keys follow its existing ignore behavior.

### Assumptions
- The already-listed flat legacy fields are the complete historical alias set; no alternate aliases or nesting are recognized.

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: historical timestamp omission is rejected by the converter; unsupported telemetry version and invalid recognized duration are rejected; normalized measurement/provenance remains intact when conflicting legacy counters are present. Focused suite: 29 passed.
- Verification: `(cd server && uv run --extra dev python -m pytest -m 'not live')` -> 735 passed, 15 deselected; `bash plugin/tests/test-session-start.sh` -> passed; `bash plugin/tests/test-contracts.sh` -> passed.

## Batch 1 Reconstruction Evidence (2026-10-27)

### Task 1 — strict public models and telemetry validation

- TDD reconstruction: added expanded behavior tests before replacing the prior result_metadata.py implementation. No product behavior was changed between those tests and the RED run.
- H1 diagnosis: inherited `Measurement` pre-validation canonicalized recognized fields and stripped unknown nested keys before strict validation; `PublicTelemetry` did not apply the existing field-specific token/percentage rules.
- RED: `(cd server && uv run --extra dev python -m pytest tests/test_result_metadata.py -q)` -> 19 failed, 78 passed. Failures named intended missing validation: nested Measurement extras accepted, float token measurements accepted, percentage 100.1 accepted, and other specified boundaries.
- GREEN: same command after reconstruction -> 97 passed; expanded combined metadata/telemetry suite -> 174 passed.
- Added tests cover every nested object’s extras, each measurement field, integer/float/bool/negative/non-finite cases, percentage bounds, nulls, qualities, provenance, completeness values, all failure kinds, and exact public keys.

### Task 3 — historical conversion strictness

- H2 diagnosis: TelemetryData’s permissive Pydantic integer coercion accepted string attribution attempt `"2"`; absent telemetry also incorrectly became default internal state.
- RED: the same pre-fix focused run showed intended failures for absent telemetry (`internal is None`) and recognized attribution values (`"2"`, bool, zero, negative) accepted.
- GREEN: `cd server && uv run --extra dev python -m pytest tests/test_result_metadata.py tests/test_telemetry.py -q` -> 174 passed. Historical recognized attribution and completed-attempt fields are now explicitly type/range validated before TelemetryData validation; absent telemetry returns None while an explicitly empty telemetry object returns typed defaults.
- Historical measurement values and provenance are retained; missing timestamp for valued data rejects before Measurement can apply defaults. Legacy counters do not override normalized metrics; stored routing tokens and unknown fields are discarded.

### Fresh phase verification

- `(cd server && uv run --extra dev python -m pytest -m 'not live')` -> 880 passed, 15 deselected.
- `bash plugin/tests/test-session-start.sh` -> passed.
- `bash plugin/tests/test-contracts.sh` -> passed.

## Batch 2 Reconstruction and Provenance Evidence: 2026-10-27

### Finding 1: Historical and Public Quality Provenance Preservation

- Reproduction: Valued measurements omitting quality previously defaulted to reported.
- Confirmed with reproduction snippet on converter and metadata.
- Root cause: `_check_measurement` defaulted missing quality on valued measurements.
- Added tests asserting missing quality rejection on valued measurements.
- Added tests asserting non-string quality rejection without `TypeError`.
- Added tests asserting missing quality allowed on unavailable measurements.
- Added tests asserting valid quality preserved unchanged.
- RED: `cd server && uv run --extra dev python -m pytest tests/test_result_metadata.py::test_public_valued_measurement_rejects_missing_quality tests/test_result_metadata.py::test_converter_rejects_valued_measurement_missing_quality -q` -> 14 failed:
  - `tests/test_result_metadata.py:208: Failed: DID NOT RAISE ValidationError`
  - `tests/test_result_metadata.py:240: Failed: DID NOT RAISE ValueError`
- GREEN: Updated `_check_measurement` to require explicit supported quality.
- Result: `cd server && uv run --extra dev python -m pytest tests/test_result_metadata.py -k quality -q` -> 34 passed.

### Finding 2 and Task 1: Complete Discard and Redo TDD Reconstruction

- Discarded production implementation to inert scaffolding.
- Scaffolding retained importable types with no contract behavior.
- Scaffolding omitted `extra="forbid"`, `strict=True`, validators, and defaults.
- RED: `cd server && uv run --extra dev python -m pytest tests/test_result_metadata.py -q` -> 53 failed, 140 passed.
- Quoted behavioral failures: no `ImportError` or `AttributeError`.
- `tests/test_result_metadata.py:31: AssertionError: assert None == 'unavailable'`
- `tests/test_result_metadata.py:42: Failed: DID NOT RAISE ValidationError`
- `tests/test_result_metadata.py:56: Failed: DID NOT RAISE ValidationError`
- `tests/test_result_metadata.py:62: Failed: DID NOT RAISE ValidationError`
- `tests/test_result_metadata.py:75: Failed: DID NOT RAISE ValidationError`
- `tests/test_result_metadata.py:82: Failed: DID NOT RAISE ValidationError`
- `tests/test_result_metadata.py:88: Failed: DID NOT RAISE ValidationError`
- `tests/test_result_metadata.py:208: Failed: DID NOT RAISE ValidationError`
- GREEN: Minimal canonical models reconstructed under tests.
- Result: `cd server && uv run --extra dev python -m pytest tests/test_result_metadata.py -q` -> 193 passed.
- Combined suite: `cd server && uv run --extra dev python -m pytest tests/test_result_metadata.py tests/test_telemetry.py -q` -> 216 passed.

### Fresh Phase Verification

- `(cd server && uv run --extra dev python -m pytest -m 'not live')` -> 922 passed, 15 deselected.
- `bash plugin/tests/test-session-start.sh` -> passed.
- `bash plugin/tests/test-contracts.sh` -> passed.

## Targeted Review Correction: Explicit Null Historical Quality (2026-10-27)

### Test-first evidence

- Added parameterized canonical and historical regressions for explicit null quality across all seven measurement fields. Existing tests also verify that missing quality on unavailable/null measurements retains the unavailable default.
- RED: `cd server && uv run --extra dev python -m pytest tests/test_result_metadata.py -k explicit_null_quality -q` -> 7 failed, 7 passed, 193 deselected. All seven historical cases failed with `DID NOT RAISE ValueError`; canonical explicit-null cases already rejected as expected.
- GREEN: `cd server && uv run --extra dev python -m pytest tests/test_result_metadata.py -k 'quality or unavailable' -q` -> 68 passed, 139 deselected.
- Minimal fix: `_check_measurement` defaults quality only when the key is absent; explicitly provided null now fails the same quality validation as other invalid values. No timestamp, source, or valid provenance behavior changed.

### Fresh Phase Verification

- `(cd server && uv run --extra dev python -m pytest -m 'not live')` -> 936 passed, 15 deselected.
- `bash plugin/tests/test-session-start.sh` -> passed.
- `bash plugin/tests/test-contracts.sh` -> passed.
