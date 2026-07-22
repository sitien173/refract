<!-- ccg-shared-version: 7.3.0 -->

# Phase 3 — Decision Notes

## Task 1

### Decisions made
- Used atomic temp directory writing in target_path.parent to validate via load_task_guide before replacing target_path.
- Preserved existing file permissions and created task_guide.json.bak backup on write.

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
  RED: `ImportError: cannot import name 'write_task_guide' from 'openmcp.config_writer'`
  GREEN: `tests/test_dashboard.py` passed `test_write_task_guide_valid_and_backup` and `test_write_task_guide_invalid_leaves_file_untouched`.
- Root cause (bugfix only): n/a


## Task 2

### Decisions made
- Added GET /dashboard/api/task-guide returning active runtime's task guide or empty dict if non-existent.
- Added PUT /dashboard/api/task-guide calling write_task_guide and returning 400 on validation failure.

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
  RED: `AssertionError: assert 404 == 200`
  GREEN: `tests/test_dashboard.py` passed `test_dashboard_api_get_task_guide`, `test_dashboard_api_put_task_guide_valid`, and `test_dashboard_api_put_task_guide_invalid`.
- Root cause (bugfix only): n/a


## Task 3

### Decisions made
- Implemented Task Guide editing view in SPA with dual structured-recommendations form and raw JSON editor.
- Implemented client-side validation checking for valid non-empty JSON object and inline error display banner.

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
  RED: `AssertionError: assert 'Task Guide' in res.text`
  GREEN: `tests/test_dashboard.py` passed `test_dashboard_static_index` along with full 91-test suite in `uv run pytest`.
- Root cause (bugfix only): n/a

