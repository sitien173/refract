<!-- ccg-shared-version: 7.3.0 -->

# Phase 2 — Decision Notes

## Task 1

### Decisions made
- Added `tomlkit>=0.12.0` to `pyproject.toml` dependencies for round-trip comment preservation.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `uv run python -c "import tomlkit"` failed before dependency installation and succeeded with version 0.15.0 after adding dependency.
- Root cause (bugfix only): none

## Task 2

### Decisions made
- Created `src/openmcp/config_writer.py` implementing `write_config`.
- Utilized temporary files in the target directory for validation with `load_config(tmp)` before atomic `os.replace()`.
- Created `.bak` backup copy of pre-existing `config.toml` before replace.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `pytest tests/test_dashboard.py` failed with `ModuleNotFoundError` before `config_writer.py` was created; passed 3 unit tests (`test_write_config_valid_and_backup`, `test_write_config_invalid_leaves_file_untouched`, `test_write_config_preserves_comments`) afterwards.
- Root cause (bugfix only): none

## Task 3

### Decisions made
- Implemented `GET /dashboard/api/config` to export parsed daemon config shaped for web forms.
- Implemented `PUT /dashboard/api/config` to validate, write, reload, and return `restart_required` status or 400 on error.
- Handled `None` values during dictionary-to-TOML serialization in `_dict_to_toml_doc`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `pytest tests/test_dashboard.py` failed with status 404 for `/dashboard/api/config` before registering endpoints in `dashboard.py`; passed `test_dashboard_api_get_config`, `test_dashboard_api_put_config_valid`, and `test_dashboard_api_put_config_invalid` afterwards.
- Root cause (bugfix only): none

## Task 4

### Decisions made
- Built Config forms tab in `index.html` with active job count indicator, restart required banner, and inline error feedback.
- Added client-side validation, target/profile manipulation, and API save handlers in `app.js`.
- Styled form controls and buttons in `styles.css`.

### Spec deviations
- none

### Tradeoffs accepted
- none

### Assumptions
- none

### Follow-ups for human
- none

### Test evidence
- RED -> GREEN: `pytest tests/test_dashboard.py` (17 passed) and `pytest` (86 passed) verified all frontend assets and backend routes cleanly.
- Root cause (bugfix only): none
