# Phase 5 — Journal: Status output shows wave progress

## Coordinator Direct Execution

- Direct execution by user decision; no Refract job, no independent review.
- `refract-stats`: `plan_stats` reads `wave` items via `item_field`; statusline appends ` wave <phase>:<state>,...` after debt; summary and hook add `  wave: phase <N> <state>, ...`. Only when the list is non-empty. Stdlib only.
- `test-stats.sh`: existing fixture and assertions unchanged (no removed lines); added an empty-wave fixture asserting byte-identical statusline and summary, and a two-item wave fixture asserting statusline, hook, and summary.
- RED: wave statusline assertion failed (`waves ACTIVE P3/3 debt 0 > Integrate Phase 2`). GREEN: `plugin/tests/run.sh` exit 0; `server/src` diff exit 0.
