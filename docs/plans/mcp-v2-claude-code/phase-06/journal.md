# Phase 6 Journal: Companion v12 Bridge

## META

- Root: /home/ngosi/projects/superpowers-ccg
- Primary artifact root: /home/ngosi/projects/openmcp
- Project: faf74d56-be72-4f88-8a2f-e05b1e185bbd
- Saved profiles: consult, implement, review
- Started: 2026-10-08T01:01:01Z
- Companion preflight/base: 85283559ec9c8241a32d10557fa6b1ba49b57d5c
- Primary prior phase: refs/plans/mcp-v2-claude-code/phase-05/impl
- Companion artifact tracking: untracked
- Primary artifact tracking: tracked

## Coordinator Setup

Both roots were clean on attached main. The companion project was already registered and had no active job. Task guidance was called once through the legacy project-only schema; the full phase request is preserved in the companion PLAN/prompt. `/tmp/mcp-v2-phase06-route-validation.py` validated selected profiles and all four workflows without emitting execution identity. Literal audit found no scope omission.

Fresh `bash tests/run.sh` failed before edits. `/tmp/mcp-v2-phase06-baseline-contracts.trace` ended at `test 101 -le 100` for implementer-prompt. This pre-existing failure is not new v2 RED evidence. Keep the trace and `/tmp/mcp-v2-phase06-baseline.log`.

Only companion Phase6 source is implemented. Companion anchors retain that source; primary Phase6 anchors, when created, retain this evidence bridge. Do not resolve one root's refs in the other.

## Consultation Response

Consultation `c5dd27b3-9548-4fc8-baa8-18564d3ab39c` succeeded at `2026-10-08T01:17:02.631244+00:00`. Initial wait `kjgndatwz` completed running; replacement returned terminal success synchronously. No wait remains active. Both roots stayed clean at companion85283559ec9c8241a32d10557fa6b1ba49b57d5c and primary18e352e5b33bf5ad3bdbaefeb464d55027534788.

Full original ERP: `phase-06/consultation.md`, exactly21840UTF-8bytes, copied from terminal result.text without v1 private job metadata. Consultation found no scope expansion or blocking question. It verified public signatures, DTOs, task-guide limits, waits/paging/errors/bounds from source; dependency/admission behavior came from the confirmed design, not fresh runtime proof. No implementation or independent quality sign-off.

The finalized prompt carries six corrections: project-only guidance with full request in submission; recover a saved job missing from recent by zero-timeout wait; four-call standard cycle distinct from resume/page/recovery; one outstanding wait, same-ID reconnect and full terminal paging; immutable dependencies preserve sequential gates; new v2 RED precedes the baseline cap failure, with fourteen paths a permission boundary rather than mandatory edits.

## Implementation Response

Fresh implementation `1a8cb683-4101-499f-9f2f-be0422a3eec7` was submitted from companion clean attached main85283559ec9c8241a32d10557fa6b1ba49b57d5c and primary clean attached maind9a10cb9a3e8b4ee88f5e2aa1061f3d2a4d856fd. Full absolute bundled role/ERP/notes/journal pointers were supplied. Saved implement workflow/profile and shared context_key were used with fresh_session true. The fourteen-source-path boundary and append-only companion notes/journal are unchanged. Companion root is frozen until terminal; its handover is intentionally not hydrated while the job is active. Outside-root receipt: `/tmp/mcp-v2-phase06-live-receipt.json`. Coordinator will retain full returned ERP and completed evidence after terminal state. No restart or source checkpoint is authorized while running.

## Initial Implementation Validation

Implementation `1a8cb683-4101-499f-9f2f-be0422a3eec7` succeeded at2026-10-08T01:46:19.514883+00:00. Waitkn9s6kq4q completed terminal; no replacement wait is active. Full terminal result.text is retained unchanged in `phase-06/implementation-01.md`,3362UTF-8bytes, copied without private v1 metadata. Eleven source paths match ERP and the fourteen-path allowlist; primary changes are Coordinator bridge files only.

Fresh checks: `timeout --kill-after=5s 120s bash tests/run.sh` passed session-start tests, contract tests and marketplace validation, exit0. `timeout --kill-after=5s 30s bash -n tests/test-contracts.sh` and `git diff --check` passed; chained tgrep prohibited-pattern audit reached its expected exit1 with no matches. No deadline timed out.

Specification FAIL despite green tests. The reference invents thirteen uppercase error names and omits approved lower-case codes, alias, defaults/ranges and return envelopes. Exact approved-code audit returned exit1, no matches. Its tests assert invented CAPACITY_EXCEEDED, remove unchanged freeze/checkpoint and explicit-other guards, and omit new mechanics from policy separation. Setup resolves before requested worktree creation and loses unavailable-service behavior. Contract loses read-only enforcement and changes the resume-key concept. Worker notes contain only Task1 despite five tasks. Full actionable batch is `phase-06/fix-01.md`; independent quality remains blocked. This is automatic fix cycle1 of2.

Provenance: original ERP Started2026-10-08T01:17:02Z predates actual job creation2026-10-08T01:42:35.250145+00:00. Preserve original report; its Started value is not actual worker-start or tool-duration evidence. Source defects are direct source/design comparisons, not inferred from that metadata. H1 confirmed: tests enforce invented names rather than the approved error family; all thirteen approved names are absent from the reference.

## Fix Batch 1 Dispatch

Resumed implementation `f43e482a-b23f-4ec3-ae7e-9943158423e8` was submitted from clean attached companion main2b499ab3a345d0e6cac09bf405e9feec54a43002 and primary main45f086de53e58a6fbfb8501cfdeb7f0c04b4cabe. Authoritative source phasebase remains85283559ec9c8241a32d10557fa6b1ba49b57d5c. Same context_key/workflow/profile; fresh_session omitted. Thin prompt points to exact fix and phase files. Three source paths plus append-only companion notes/journal, no broadened scope. This is automatic batch1 of2. Companion root is frozen. One3600-second heartbeat wait is recorded outside-root; no short repeated polling. Hydrate companion handover only after terminal. No restart.

## Quality Review

Pending. Specification failures block independent quality review.

## Review Result

- Spec Status: PASS, validated candidate after fix batch1; initial failure is preserved above
- Quality Status: PENDING
- Debt: none

## Final Checkpoint

- Companion plan base: refs/plans/mcp-v2-claude-code/base
- Companion phase base: refs/plans/mcp-v2-claude-code/phase-06/base, resolved85283559ec9c8241a32d10557fa6b1ba49b57d5c
- Companion initial implementation checkpoint: 2b499ab3a345d0e6cac09bf405e9feec54a43002, declared checks passed; specification FAIL, not phase closure
- Companion phase impl: refs/plans/mcp-v2-claude-code/phase-06/impl, pending
- Primary evidence bridge base: refs/plans/mcp-v2-claude-code/phase-06/base, to be set from the finalized clean metadata checkpoint
- Prior consultation checkpoint: 17c3352dde5ccc80656f27bace0555cf8497fa73
- Primary evidence bridge impl: refs/plans/mcp-v2-claude-code/phase-06/impl, pending

The phase_base cache in the primary handover refers to companion source8528355; its phase_base_ref is resolved in the companion root. The same-named primary ref retains only this evidence bridge. Prompt finalized after successful consultation, no source edit or implementation job yet.

The daemon remains on Phase1 code. Native v2 acceptance and both-root consolidation remain pending.

## Fix Batch 1 Validation

Fix f43e482a-b23f-4ec3-ae7e-9943158423e8 succeeded with creation2026-10-08T02:08:02.455790+00:00 and terminal update2026-10-08T02:20:57.668590+00:00. Its 3600-second wait kimfmawhq completed terminal, with no replacement. These are lifecycle timestamps, not native acceptance duration. Full exact terminal result.text is retained in implementation-fix-01.md,3135UTF-8bytes, without private v1 job fields. ERP NEXT is CONTINUE_CONTEXT and the matching continuing line is present; success alone is not phase completion.

Exactly the three authorized fix sources changed from2b499ab: coordinator SKILL, tool-contract reference and tests/test-contracts.sh. Companion notes/journal were appended and all prior content preserved. Source inspection matched the seven signatures/envelopes, all13 approved errors and safe handling, defaults/ranges/paging/bounds, worktree-before-resolve and unavailable-service behavior, read-only/private/session semantics and restored guards. Task2 to Task5 notes now exist. Semantic RED before production failed at the newly asserted alias signature; GREEN includes exact error-set, setup-order and preserved policy tests. Original faulty metadata remains preserved with provenance correction, not silently rewritten.

Fresh full verification passed: timeout --kill-after=5s 120s bash tests/run.sh, session-start and contract tests plus marketplace validation, exit0; timeout --kill-after=5s 30s bash -n tests/test-contracts.sh, exit0; git diff --check, exit0; tgrep prohibited-pattern audit, no matches and expected exit1. Historical diff confirms only three manifest version values, four shared markers and minimal prompt compression changed in those files. No source scope expansion, deadline timeout or new debt.

Spec Status: PASS for the validated candidate; Quality Status: PENDING. Source checkpoint fe7fee0fb68d6f26b76827f2995b134117c318e6 is clean and preserves initial checkpoint2b499ab. No phase impl anchor or closure yet. Follow CONTINUE_CONTEXT with one resumed Continue Phase06 job, continuation1 of2, then fresh validation and first fresh independent review. The live interface remains the planned pre-restart interface until Phase7; current session skill cache is not proof of fresh v12 loading. CLI-only preparation is /tmp/mcp-v2-phase7-docs-20261008-085455/phase7-preparation.md; installed2.1.293 flags were verified but no live cutover probe ran.
