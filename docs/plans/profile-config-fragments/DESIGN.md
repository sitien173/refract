# Profile Config Fragments Design

## Purpose

Load reusable target and profile definitions from `*.config.toml` fragments.
Fragments are supported globally and per project. Existing `config.toml` files
remain authoritative.

## Decisions

- Use source-aware, two-phase loading.
- Discover direct-child `*.config.toml` files only.
- Match filenames case-sensitively and non-recursively.
- Sort filenames for deterministic processing and diagnostics.
- Allow only `[[targets]]` and `[profiles.*]` in fragments.
- Main files replace matching definitions entirely.
- Fragment conflicts warn, then block configuration loading.
- Any invalid fragment blocks configuration loading.

## Discovery and precedence

Global fragments live beside the global `config.toml`. Project fragments live
inside the project's `.openmcp` directory.

Configuration precedence runs lowest to highest:

1. Global fragments.
2. Global `config.toml`.
3. Project fragments.
4. Project `.openmcp/config.toml`.

There is no precedence between fragment files. Sorting affects only processing
and error ordering. Duplicate target or profile identifiers between fragments
in one directory are conflicts.

Duplicates across global and project scopes are valid project overrides.
Duplicates between fragments and their same-scope main file are valid main-file
overrides. Higher layers replace the complete target or profile definition.
Fields and workflows never merge implicitly.

## Architecture

Add one source-aware fragment loading path in `config.py`. Each parsed source
retains its path for validation and diagnostics.

Loading has two phases:

1. Parse and validate each fragment independently.
2. Compose normalized definitions and validate the effective catalog.

Independent validation prevents a main-file override from hiding an invalid
fragment. Effective validation preserves target references, profile inheritance,
default profile checks, and existing configuration behavior.

Project configuration gains `[[targets]]` support. This allows project main
files to replace targets declared by project fragments. Every target still uses
the existing argument and policy validation.

## Data flow

Global loading:

1. Discover and parse all global fragments.
2. Reject unsupported or empty fragment declarations.
3. Normalize targets and profiles with source paths.
4. Detect fragment target and profile conflicts.
5. Validate fragment definitions before shadowing.
6. Overlay global `config.toml` definitions.
7. Resolve the effective targets and profiles.
8. Validate `[daemon].default_profile`.

Project loading repeats the fragment pipeline against the global catalog. It
then overlays project `config.toml` definitions and returns a new
`DaemonConfig`. The base catalog remains unchanged.

Profiles resolve against effective targets. Explicit `extends` remains the only
way to inherit workflows. Existing project self-extension behavior remains.

## Errors and warnings

All fragment failures include the source path. TOML parse failures retain line
and column details.

Malformed TOML, unsupported sections, invalid targets, unknown target
references, unknown parents, and inheritance cycles raise `ValueError`.

Cross-fragment duplicate identifiers emit one
`ConfigFragmentConflictWarning`. Loading then raises `ValueError` with the same
conflict details. Conflict output sorts by definition kind, identifier, and
source path.

The warning occurs before normal logging configuration. A dedicated Python
warning keeps behavior visible and directly testable.

## Compatibility and security

Existing installations behave unchanged when no fragments exist. No migration
is required.

Project targets expand repository trust. A project can replace global backend,
model, prompt, isolation, and argument settings. Existing target argument
guardrails remain mandatory. No new permission mechanism is included.

## Non-goals

- Recursive fragment discovery.
- Filename-based fragment precedence.
- Partial target field merging.
- Partial profile workflow merging.
- Server or logging settings inside fragments.
- New CLI configuration controls.

## Testing

Focused configuration tests cover:

- Global and project fragment discovery.
- Non-recursive and case-sensitive matching.
- Deterministic filename processing.
- Allowed section enforcement.
- Invalid shadowed fragment rejection.
- Target and profile conflict warnings.
- Main-file whole-definition replacement.
- Four-layer precedence.
- Cross-layer profile inheritance.
- Project target replacement.
- Existing self-extension behavior.
- Base catalog immutability.
- Existing behavior without fragments.

## Verification

- `uv run pytest tests/test_config.py`
- `uv run pytest`
