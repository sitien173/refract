## User Request
Continue worker-ask-coordinator with Phase 2 only. Implement the coordinator MCP contract from the confirmed design and plan. Phase 1 is accepted at refs/plans/worker-ask-coordinator/phase-01/impl.

## Phase
Expose pending worker questions through job_wait and accept coordinator answers through job_answer. Stop after this phase; worker CLI and coordinator workflow changes belong to Phase 3.

## Tasks
- task-1: Add job_answer(job_id, answer) in server.py and Runtime. Deliver the supplied answer to the pending ask. Return invalid_state when no question is pending or the job is terminal. Preserve existing unknown-job conventions.
- task-2: Wake Runtime.wait and job_wait when a new pending question appears. Return the running job with result.pending_question containing question_id and text. Preserve terminal paging, nonterminal timeouts and jobs without questions.
- task-3: Update exact tool-list assertions and public contract documentation from seven tools to eight tools, including job_answer and pending_question. Keep prose and schemas consistent.

## Context
Read these existing documents and modules before changing them:
- /home/ngosi/projects/refract/docs/plans/worker-ask-coordinator/DESIGN.md
- /home/ngosi/projects/refract/docs/plans/worker-ask-coordinator/PLAN.md
- /home/ngosi/projects/refract/server/src/refract/ask.py
- /home/ngosi/projects/refract/server/src/refract/runtime.py
- /home/ngosi/projects/refract/server/src/refract/server.py
Phase 1 provides an in-memory AskRegistry, token revocation, pending asks and asynchronous HTTP answer waits. Preserve its locking, cancellation, remaining workflow deadline and escaped-surrogate authentication fixes. DB schema stays v15. Existing revoked-token retention is assigned nonblocking debt, not work for this phase.

## Files
- server/src/refract/server.py
- server/src/refract/runtime.py
- server/src/refract/ask.py
- server/tests/test_server.py
- server/tests/test_mcp_schema_contract.py
- plugin/tests/test-contracts.sh
- plugin/skills/coordinating-multi-model-work/references/tool-contract.md
- README.md
- server/README.md
- docs/plans/worker-ask-coordinator/phase-02/notes.md
- docs/plans/worker-ask-coordinator/phase-02/journal.md

Out of scope: every other file; Phase 3 CLI, worker contract and coordinator SKILL.md; credentials, ~/.refract/ and environment secrets. If another path is essential, return BLOCKED with the exact reason rather than widening scope.

## Done When
- Tests prove job_wait wakes early with pending_question and job_answer releases the HTTP ask with the exact supplied answer.
- Tests prove invalid_state when no question is pending and when the job is terminal.
- Tests preserve nonterminal waits without questions, terminal results and existing size bounds. Answer and pending-question payloads are treated as bounded data.
- Tool schema, contract test and documentation agree on exactly eight tools.
- No schema migration or dependency is added.
- cd /home/ngosi/projects/refract/server && uv run pytest -q
- cd /home/ngosi/projects/refract && bash plugin/tests/run.sh

## Rules
Follow these bundled files:
- Contract: /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- Response: /home/ngosi/projects/refract/plugin/shared/erp.md
- Notes: /home/ngosi/projects/refract/plugin/shared/notes-template.md
- Journal: /home/ngosi/projects/refract/plugin/shared/journal-template.md
Use test-driven development: run a focused regression RED before changing behavior, then implement minimally and record exact commands and outcomes. Follow existing errors, event/wake primitives and response size handling; inspect before introducing helpers. Keep prose changes limited to this contract. Read /home/ngosi/.agents/skills/writing-for-agents/SKILL.md when editing the agent-facing tool-contract reference. No Git mutations, handover changes, unrelated refactoring or token disclosure. Append task notes and ERP without overwriting prior entries. The coordinator owns Git, verification and independent review.

## Response Format
Return the full ERP # EXTERNAL RESPONSE block with NEXT status.
