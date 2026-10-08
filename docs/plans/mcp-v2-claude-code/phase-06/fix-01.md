# Phase 6 Fix Batch 1

## Context

Initial implementation `1a8cb683-4101-499f-9f2f-be0422a3eec7` returned TASK_COMPLETE. Coordinator freshly passed all declared commands, confirmed eleven source paths within the fourteen-path boundary, and found the specification failures below. The first source checkpoint and current pre-job HEAD are supplied on dispatch. This is the first of at most two automatic fix cycles. Preserve all source/version work and all previous ERP, journal and notes content.

## Findings

1. **Approved contract is not documented.** `references/tool-contract.md:66-70` invents thirteen uppercase error codes; exact approved-code tgrep returned no matches. `tests/test-contracts.sh:147` asserts the invented `CAPACITY_EXCEEDED`. Replace the error section with exactly the thirteen approved codes below and correct safe handling. No invented error family. Include `isError`, the four JSON fields, retry-once/request-ID handling for internal errors, and preservation of the actual outcome/root job or project ID after applied-mutation overflow.

   `unknown_project`, `invalid_path`, `alias_taken`, `unknown_job`, `unknown_profile`, `invalid_dependency`, `dependency_failed`, `invalid_state`, `config_invalid`, `daemon_stopping`, `invalid_request`, `response_too_large`, `internal_error`.

   Compare authoritative DESIGN lines72-138 and229-253, not memory. Table omits optional `alias` on project_resolve and all seven return envelopes. Document `project_resolve` -> `{project:{id,alias,path}}`; task_guide -> `{workflows,profiles:{default,available},guidance}`; submit/retry -> `{job:summary}`; wait -> `{job:summary,result:{text,error,next_offset}}`; list -> `{active,recent,more_recent}`; cancel -> `{job:summary,cancelled_dependents}`. Capture project.id/job.id correctly. Pass the actual Git root: server canonicalizes an existing directory but does not walk upward. Include real defaults, timeout0..3600 and nonnegative Unicode code-point result_offset default0. Preserve terminal-only paging, no silent omission and the complete serialized character/byte budgets. Do not add tool arguments or output fields.

2. **Setup/policy semantics changed.** Coordinator SKILL Setup calls project_resolve before its requested-worktree step. Restore worktree setup before resolving/retaining that Git root's project ID. Preserve the old unavailable-service behavior: report once, planning continues with skipped-consult reason, Execute/Review stop. Correct tool-contract session key: configured target key is not native session identity; it remains private and is not client input. Restore explicit partial-profile/other-mapping semantics and read-only enforcement for consult/review: workflow names do not enforce write safety. Preserve optional isolation, clean-root rules, sequential gates and all existing role/privacy/session contracts.

3. **Existing guards were weakened.** Restore the unchanged source-freeze and temporary-checkpoint assertions removed from tests. Restore the explicit-other-mapping guard with real documented semantics, not a generic task_guide presence assertion. Update the policy-separation mechanics guard for all seven v2 tool names; retain existing legacy/privacy/target/role/cap/Git guards. Add meaningful tests for the exact tool set, approved error set, signature/envelope details and worktree-before-resolve order. Show each new regression can fail against the current defective state or an isolated defective fixture before production corrections. Do not raise caps or delete assertions to pass.

4. **Task evidence is incomplete.** Worker notes contain only Task1, but the prompt defines Tasks1..5 and requires a block per task. Append factual blocks for Tasks2..5 and any fix evidence, with all prescribed sections and none where appropriate. Do not invent past RED or timestamps. Prior ERP Started01:17:02Z predates actual implementation creation01:42:35.250145+00:00. Preserve the original ERP unchanged and append a provenance correction distinguishing reported metadata from actual job lifecycle. Actual terminal update was01:46:19.514883+00:00. No whole-job/session timestamp is tool-duration evidence.

## Allowed paths

Only these source paths need changes for this batch:
- `skills/coordinating-multi-model-work/references/tool-contract.md`
- `skills/coordinating-multi-model-work/SKILL.md`
- `tests/test-contracts.sh`

Append only companion `phase-06/notes.md` and `journal.md`. Keep the seven12.0.0 values and the100-line implementer prompt untouched unless a demonstrated regression requires a change within the original fourteen-path permission boundary. The remaining original paths are permission, not required edits. No primary repository writes or coordinator artifact edits.

## Verification

Run every original command freshly with its hard deadline:
- `timeout --kill-after=5s 120s bash tests/run.sh`
- `timeout --kill-after=5s 30s bash -n tests/test-contracts.sh`
- `git diff --check`
- `tgrep -n 'project_register|openmcp://|resource_uri|timeout_s: 300' skills shared`

No audit matches is expected exit1. Report exact outputs/status and new semantic RED before production then GREEN. Do not silently rerun away failure or leave a timed-out command running. Keep coordinator265, reference90 and prompt100 caps and existing guard coverage. No Git writes, restart, OpenMCP calls, installs/upgrades, permission/configuration changes, live/global configuration/database/auth/session reads, private execution identity or scope expansion. Return the full ERP and append it with the matching status line.
