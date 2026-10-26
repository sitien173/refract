## User Request
Continue Phase 3 of worker-ask-coordinator and skip independent review. This waiver covers Phase 2 acceptance and Phase 3 review only. Coordinator verification and the planned live backend probes remain required.

## Phase
Complete the worker ask command and coordinator workflow. Preserve the accepted server ask channel and eight-tool MCP contract. This is the final phase.

## Tasks
- task-1: Add refract ask "<question>" in server/src/refract/cli.py. Read REFRACT_ASK_URL and REFRACT_ASK_TOKEN from the environment, POST token/question using only standard-library HTTP, wait for the answer, and print it. Print the exact server no-answer text on server ask timeout. Exit nonzero with a clear error when env is missing, server unreachable, or HTTP rejects the request. Never disclose token values in errors or logs. Handle this command before loading daemon config so a worker needs only the injected env.
- task-2: Add concise worker-contract guidance: ask only for unresolved decisions the plan does not answer; run refract ask; continue with the response; fall back to BLOCKED when the command fails. Add the corresponding coordinator Gate 2 flow: when job_wait returns result.pending_question, answer using job_answer, then resume job_wait with the same job ID. Keep the existing default heartbeat and paging rules.
- task-3: Add live-marked probes for codex, claude, agy and pi, each in normal and read_only mode. Exercise actual target argument translation and parent-env passthrough through backend tool shells. Check that an actual refract ask reaches a local loopback listener and returns its answer. Tokens/URLs remain in env, not prompts. Record all eight observed results in server/CLI_ARGUMENTS.md, including any backend/mode requiring BLOCKED fallback. Do not weaken read_only/sandbox controls to make a probe pass. Distinguish successful reachability, blocked tools/network, missing executable, authentication failure, timeout and not-run evidence. A mock is not live backend evidence.

## Context
- Confirmed design: /home/ngosi/projects/refract/docs/plans/worker-ask-coordinator/DESIGN.md
- Plan: /home/ngosi/projects/refract/docs/plans/worker-ask-coordinator/PLAN.md
- Phase 1 accepted ask registry and loopback POST /ask.
- Phase 2 accepted bounded job_answer and pending_question in job_wait, with independent review explicitly waived by the user.
- Existing no-answer text: No answer from coordinator; use your best judgment or end with BLOCKED.
- Existing tests mark live backends with pytest.mark.live and exclude them from default pytest.
- Use backend wrappers/DriverRegistry and TargetConfig already present. Read target argument translation before writing probes; direct transport-only execute does not apply read_only target fields.
- server/CLI_ARGUMENTS.md documents current read_only modes. Some intentionally lack shell tools. Report observed fallback rather than granting tools.
- The refract executable may not be on worker PATH. Verify command availability and document a supported invocation; do not invent flags.

## Files
- server/src/refract/cli.py
- server/tests/test_smoke.py
- server/tests/test_live_backends.py
- server/CLI_ARGUMENTS.md
- plugin/shared/worker-contract.md
- plugin/skills/coordinating-multi-model-work/SKILL.md
- docs/plans/worker-ask-coordinator/phase-03/notes.md
- docs/plans/worker-ask-coordinator/phase-03/journal.md

Out of scope: every other file, Git state, handover, credentials, ~/.refract/ content, server registry/MCP redesign, dependency additions, and pre-existing revoked-token retention debt. If another path is essential, return BLOCKED with a reason.

## Done When
- Test-first CLI coverage proves missing env, unreachable server, successful answer, exact no-answer timeout output, HTTP rejection and token secrecy.
- Worker and coordinator documents describe the same ask/answer/re-wait flow without routine unnecessary questions.
- Eight live backend/mode outcomes are recorded with actual command, date, status and evidence; any missing prerequisite is explicit, not a pass.
- Live probes stay excluded from default tests and are bounded to finite runtime per backend/mode.
- cd /home/ngosi/projects/refract/server && uv run pytest -q
- cd /home/ngosi/projects/refract && bash plugin/tests/run.sh
- Run the new live probe selection explicitly and record its exact invocation and complete outcomes. Do not run unrelated old live smoke cases unless needed.

## Rules
Follow bundled contracts:
- /home/ngosi/projects/refract/plugin/shared/worker-contract.md
- /home/ngosi/projects/refract/plugin/shared/erp.md
- /home/ngosi/projects/refract/plugin/shared/notes-template.md
- /home/ngosi/projects/refract/plugin/shared/journal-template.md
Use RED then GREEN and record exact commands, failing assertions and pass counts, not invented test names. Match existing style and keep edits surgical. Read /home/ngosi/.agents/skills/writing-for-agents/SKILL.md and its SKILL-MECHANICS.md reference before changing the skill or worker contract. Keep file-size/line-count contract assertions in mind. Apply current CLI docs or verified --help for any new backend flag; never guess flags. Use finite subprocess/test timeouts. Do not put token or URL in a worker prompt, diagnostics, transcript or documentation. Prompt workers only with the command to run and how to report success/fallback, using env implicitly. Use temporary probe directories and local ephemeral listener state; preserve user files and backend auth configuration. No Git mutations. No independent review job; user waived it. Append notes and ERP journal. Return BLOCKED if live prerequisites cannot be safely resolved, listing exact statuses and needed decisions. Do not claim unsupported backend success.

## Response Format
Return full ERP # EXTERNAL RESPONSE with NEXT status. List every touched path and exact test/probe evidence.
