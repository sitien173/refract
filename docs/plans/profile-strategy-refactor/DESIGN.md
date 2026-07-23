# Profile Strategy Refactor — Design

## Purpose

Two goals, sequenced. First remove fabricated config defaults so operators must
declare targets and profiles explicitly. Then replace the implicit
"inherit-from-default" profile behavior with explicit, chained inheritance and
allow partial profiles.

## Decisions

- Cleanup scope: full strict rewrite.
- Missing workflow at submission: reject with a clear error (no hidden fallback).
- Inheritance: single parent via `extends`, chained, cycles rejected.
- Same-name across layers: project profile replaces the base one; build on it
  only via explicit `extends`.

## Part 1 — Strict cleanup (prerequisite)

Remove fabrication and legacy scaffolding in `config.py`:

- Delete `_default_targets`, `_default_profiles`, `_default_legacy_routes`.
- Delete the whole legacy-routes path: `_legacy_routes`, `include_defaults`,
  the `routes` section, and `routing_profiles`/`default_routing_profile`
  aliases. `_target_selection` no longer takes `legacy_routes`; a string value
  is a single target id only.
- `load_config` requires `config.toml` to exist. Missing file is an error, not
  an empty dict.
- `[targets]` is required and non-empty; otherwise error.
- `[profiles]` is required and non-empty; otherwise error.
- `default_profile` has no `"balanced"` fallback. It must be set in `[daemon]`
  and must name a defined profile. (`DaemonConfig.default_profile` keeps no
  meaningful class default; it is always supplied by load.)
- Remove `legacy_selections` from `DaemonConfig` and all readers.
- Update `_renamed_value` usage: drop the profiles/default_profile legacy names.
  Keep `backend_profile`/`profile` target rename only if still wanted; otherwise
  drop for full strictness. (Decision: keep the target `profile` -> `backend_profile`
  migration out of scope; leave as-is unless it conflicts.)

Ripple:

- `config_writer.py`: drop `routing_profiles` migration branch (config.py:128).
- `README.md` / `CLI_ARGUMENTS.md`: document required sections, no defaults.
- Tests: `test_smoke.py` uses `[routing_profiles.balanced]` — migrate to
  `[profiles.balanced]` + explicit `default_profile`. Other tests already build
  explicit configs; adjust any that relied on defaults or `legacy_selections`.

## Part 2 — Explicit inheritance and partial profiles

### Schema

Inside a profile table, `extends = "<parent-name>"` is a reserved key naming one
parent profile. It is not a workflow. All other keys are workflow selections as
today (`implement`, `review`, `consult`, or future workflows).

```toml
[profiles.base]
implement = ["forge-primary"]
review    = ["sentinel-primary"]
consult   = ["sage-primary"]

[profiles.fast]
extends   = "base"
implement = ["forge-primary", "canvas-primary"]   # override

[profiles.advisor]
consult   = ["sage-primary"]                        # partial: consult only
```

### Resolution

- Build the raw profile map first (name -> {extends?, workflow selections}).
- Resolve each profile lazily with memoization:
  1. If `extends` set, resolve the parent first.
  2. Start from the parent's resolved workflow map (copy); empty if no parent.
  3. Override per workflow with the child's declared selections. Granularity is
     per workflow (whole `TargetSelection` replaced), matching today's
     `dict.update`.
- Cycle detection: track the visiting set along the chain; a repeat is an error
  naming the cycle.
- `extends` target must exist in the same layer's namespace; unknown parent is
  an error.
- Declaration order within a file is irrelevant (lazy + memoized).

### Partial profiles

- Drop the load-time completeness check (`config.py:388-393`). A profile may map
  any subset of workflows, including one.
- No implicit fill from the default profile. `resolve_execution_plan`
  (`planning.py:113-115`) already raises "Profile X does not map workflow Y" —
  that becomes the single, intended submission-time rejection.
- `default_profile` need not be complete either; submitting an unspecified-profile
  job whose workflow the default lacks is rejected the same way.

### Layering (base -> project)

- `load_project_config` no longer passes `inherited_profile`/implicit base
  inheritance. Project profiles start from their own `extends`, not from the base
  default.
- Merged namespace for a project = base profiles overlaid by project profiles.
  A project profile with the same name **replaces** the base one.
- `extends` resolves against this merged namespace. A project profile
  `extends = "X"` where `X` is a base profile builds on the base `X`. A project
  profile named `X` that also `extends = "X"` resolves the parent from the base
  layer snapshot (self excluded), so it can extend the profile it shadows.

## Non-goals

- Multiple-parent inheritance.
- Deep-merge within a single workflow's selection.
- Per-workflow default fallback.
- New CLI surface; this is config-file only.

## Testing

- Config: missing file errors; missing `[targets]`/`[profiles]` error; unknown
  `default_profile` errors; unknown `extends` errors; cycle errors.
- Inheritance: chain A->B->C composes; child override wins; partial profile
  loads.
- Submission: consult-only profile + implement job rejects with the mapped-
  workflow error; consult job with same profile succeeds.
- Layering: project replaces same-name base; project `extends` base name builds
  on base; project self-name `extends` resolves base snapshot.
- Update `test_smoke.py` and any default-reliant tests.

## Verification commands

- `python -m pytest tests/test_config.py tests/test_planning.py tests/test_smoke.py`
- Full suite: `python -m pytest`
