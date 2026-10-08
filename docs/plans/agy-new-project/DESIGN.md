# Initialize New Agy Sessions as Projects

## Purpose

Ensure new `agy` sessions initialize project context. Preserve resumed session
behavior.

## Research basis

Verified on 2026-08-28 against Antigravity CLI documentation.

- `agy --new-project` initializes a new project.
- `agy --conversation <id>` resumes an existing conversation.
- Resumed conversations retain their associated project.

## Root cause

`src/openmcp/backends/agy.py` builds every command without `--new-project`.
New headless sessions therefore lack explicit project initialization. Project
context files may not load.

## Approaches

1. Always pass `--new-project`. This is smallest, but conflicts with resumed
   conversations.
2. Pass `--new-project` only without `SESSION_ID`. This matches documented
   session semantics and preserves resume behavior.
3. Add a configuration option. This adds unnecessary policy and user burden.

Use approach 2.

## Argv contract

New session:

```text
agy --dangerously-skip-permissions [target args] --log-file <path> \
    --new-project --print <prompt>
```

Resumed session:

```text
agy --dangerously-skip-permissions [target args] --log-file <path> \
    --conversation <id> --print <prompt>
```

OpenMCP owns `--new-project`. Target arguments remain before OpenMCP transport
arguments.

## Testing

Add focused command-capture tests proving:

- new sessions include `--new-project`;
- resumed sessions omit `--new-project`;
- resumed sessions still pass `--conversation <id>`;
- existing target argument and prompt ordering remains unchanged.

## Non-goals

- Existing project selection through `--project`.
- New target configuration fields.
- Changes to continuation behavior.
- Changes to session identifier extraction.

## Compatibility

Existing resumed sessions remain unchanged. New sessions gain project
initialization. No migration is required.
