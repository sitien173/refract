# Add the `other` Built-in Workflow

## Purpose

Add `other` as a fourth fixed workflow. It covers tasks that do not fit
`consult`, `implement`, or `review`.

## Decisions

- Use the exact lowercase name `other`.
- Keep workflow names fixed and centrally validated.
- Order built-ins as `consult`, `implement`, `other`, `review`.
- Require an explicit profile mapping before submission.
- Do not alias `other` to `implement` or another workflow.
- Keep existing profiles valid when they omit `other`.
- Return the existing missing-mapping error during submission.
- Store `other` as the job workflow and context role.
- Leave target policy, isolation, and tools unchanged.

## Routing

`other` follows the existing routing path:

1. Submission validates `other` as built-in.
2. The selected profile resolves its `other` mapping.
3. The execution plan snapshots that target selection.
4. The job persists `other` as its workflow.
5. Context history uses `other` as its role.

Profiles without an `other` mapping still load. They cannot submit `other`
until operators add the mapping. This avoids breaking existing configurations.

## Discovery

The workflows resource must expose `other`. Doctor guidance must check all four
built-ins. README examples must show an explicit `other` mapping.

## Non-goals

- Dynamic workflow names.
- Automatic fallback routing.
- Special mutation or read-only behavior.
- Automatic edits to operator configuration files.
- Changes to external clients that hard-code three workflows.

## Compatibility

- Existing job and execution-plan records remain valid.
- Existing profiles remain valid.
- Existing submissions behave unchanged.
- New `other` submissions fail clearly when unmapped.
- No database migration is required.

## Testing

- Validate and discover the four-workflow tuple.
- Accept `other` as a profile key.
- Resolve and round-trip an `other` execution plan.
- Submit and complete an `other` job.
- Reject `other` when the selected profile omits it.
- Preserve existing partial-profile behavior.
- Verify doctor guidance and README examples.
