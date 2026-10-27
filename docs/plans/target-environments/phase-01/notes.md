<!-- refract-shared-version: 2.0.0 -->

# Phase 1 Decision Notes

Append one task block per completed task. Use Decisions made, Spec deviations, Tradeoffs accepted, Assumptions, Follow-ups for human, and Test evidence headings. Record explicit RED failure lines and GREEN counts. Empty sections contain `- none`.


## Task 1

### Decisions made
- Configured environment keys and values in `TargetConfig` and `DaemonConfig` use `repr=False` to prevent secret leaking in dataclass repr strings.
- Target `envs_vars` defaults to empty tuple `()` and target `envs` defaults to a distinct empty dictionary instance to avoid shared mutable defaults.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server && uv run pytest tests/test_environment.py` failed 17 tests:
    `tests/test_environment.py:33: AttributeError: 'DaemonConfig' object has no attribute 'envs'`
    `src/refract/config.py:699: ValueError: Unsupported config sections: ['envs']`
    `tests/test_environment.py:310: AttributeError: 'TargetConfig' object has no attribute 'envs'`
  - GREEN: `cd server && uv run pytest` passed 827 passed, 15 deselected in 137.28s.
- Root cause (bugfix only): - none


## Task 2

### Decisions made
- `load_project_config` constructs fresh `TargetConfig` copies via `dataclasses.replace` for overridden targets and ensures local mapping dictionaries are not shared with base targets.
- Merged project shared sets update a shallow copy of base shared sets to keep global and sibling project catalogs isolated.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server && uv run pytest tests/test_environment.py` failed 15 tests:
    `src/refract/config.py:869: ValueError: Unsupported project config sections: ['envs']`
    `src/refract/config.py:869: ValueError: Unsupported project config sections: ['envs', 'targets']`
  - GREEN: `cd server && uv run pytest` passed 842 passed, 15 deselected in 182.63s.
- Root cause (bugfix only): - none


## Task 3

### Decisions made
- Implemented iterative dependency resolution with topological sorting and `ready` queue to eliminate recursion depth limitations on long valid reference chains.
- Inherited environment variables are read literally and never recursively evaluated for template syntax.
- Returns only configured environment variable overrides without mutating `os.environ`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server && uv run pytest tests/test_environment.py` failed 11 tests:
    `tests/test_environment.py:720: AssertionError: assert {} == {'COMMON': 'from_target', ...}`
    `tests/test_environment.py:744: KeyError: 'FIRST'`
    `tests/test_environment.py:842: Failed: DID NOT RAISE ValueError`
    `tests/test_environment.py:865: KeyError: 'V2000'`
  - GREEN: `cd server && uv run pytest` passed 853 passed, 15 deselected in 158.72s.
- Root cause (bugfix only): - none


## Task 4

### Decisions made
- Extended safe configuration error allow-list in `config_inspection.py` with `_environment_config_error` to strip target ids, set names, key names, variable references, and templates from diagnostics.
- Added comprehensive regression tests across `test_config_inspection.py`, `test_config.py`, and `test_environment.py` ensuring full coverage of declarations, precedence, overlays, diagnostics sanitization, and catalog metadata preservation.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server && uv run pytest tests/test_config_inspection.py` failed 1 test:
    `tests/test_config_inspection.py:211: AssertionError: assert 'Invalid configuration' == 'Malformed environment reference'`
  - GREEN: `cd server && uv run pytest` passed 874 passed, 15 deselected in 161.02s.
- Root cause (bugfix only): - none


## Fix Cycle 1

### Decisions made
- Removed target identifiers, reference names, and cycle keys from direct ValueError messages raised by `resolve_target_environment` and `_parse_env_template`.
- Raised strictly structural diagnostics (`Unknown target`, `Missing environment reference`, `Environment reference cycle detected`, `Protected environment reference`) directly at the resolver/parser boundary so diagnostic sanitization does not rely on downstream wrapping.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN:
  - RED: `cd server && uv run pytest tests/test_environment.py -k test_resolve_target_environment_errors_are_strictly_structural_without_markers` failed 1 test:
    `tests/test_environment.py:948: AssertionError: assert "Unknown target: 'unknown_target_SYNTHETIC_PRIVATE_MARKER_98765'" == 'Unknown target'`
  - GREEN: `cd server && uv run pytest` passed 875 passed, 15 deselected in 274.02s.
- Root cause (bugfix only):
  - `resolve_target_environment` and `_parse_env_template` embedded arbitrary target ids, reference names, and cycle keys directly into `ValueError` exception strings. Made exception strings strictly structural at the resolver/parser boundary.
