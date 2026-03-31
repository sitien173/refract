# Cursor Base Prompt Templates

> Invoke via `mcp__cursor__cursor` (required: `PROMPT`; optional: `SESSION_ID`, `model`).
> All prompts in English. Every template ends with the Response Protocol block.
> Cursor handles **DevOps tasks only**: CI/CD, shell scripts, Dockerfiles, Makefiles, infrastructure, repo tooling.
> Model: `claude-4.6-sonnet-medium-thinking` for implementation, `claude-4.5-opus-high-thinking` for cross-validation.

## Response Protocol Block (append to ALL prompts)

```
## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context, NO full file rewrites. Use the output format below.
```

---

## DevOps Implementation Template

```
## Task
{task_description}

## Code Location
File: {file_path}
Lines: {start_line}-{end_line}

Note: Use your CLI tools to read the file at the specified location.

## Requirements
1. {requirement_1}
2. {requirement_2}
3. {requirement_3}

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## APPROACH (≤100 words) → ## DIFF (changed hunks only) → ## VERIFY (commands to run) → ## ISSUES (limitations/risks).
```

## CI/CD Pipeline Template

```
## Task
{pipeline_task_description}

## Pipeline Location
File: {workflow_file_path}

Note: Use your CLI tools to read the file at the specified location.

## Requirements
1. {requirement_1}
2. {requirement_2}
3. Idempotent — safe to re-run without side effects

## Environment
Platform: {github_actions|azure_devops|gitlab_ci|other}
Runner: {runner_os}

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## APPROACH (≤100 words) → ## DIFF (changed hunks only) → ## VERIFY (how to test the pipeline) → ## ISSUES (risks/caveats).
```

## Shell Script Template

```
## Task
{script_task_description}

## Script Location
File: {script_path}

Note: Use your CLI tools to read the file at the specified location.

## Requirements
1. {requirement_1}
2. {requirement_2}
3. POSIX-compatible unless platform-specific (document why)
4. set -euo pipefail at top

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## APPROACH (≤100 words) → ## DIFF (changed hunks only) → ## VERIFY (how to test the script) → ## ISSUES (portability/edge cases).
```

## Dockerfile Template

```
## Task
{docker_task_description}

## File Location
File: {dockerfile_path}

Note: Use your CLI tools to read the file at the specified location.

## Requirements
1. {requirement_1}
2. {requirement_2}
3. Multi-stage builds where appropriate
4. Minimize layer count and image size

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## APPROACH (≤100 words) → ## DIFF (changed hunks only) → ## VERIFY (build and test commands) → ## ISSUES (security/size concerns).
```

## Infrastructure Review Template

```
## Files
{file_list_with_line_ranges}

## Changes
{change_summary}

Note: Use your CLI tools to read the files at the specified locations.

## Review Focus
1. Correctness — syntax, logic, environment variable handling
2. Security — secrets management, permissions, attack surface
3. Reliability — failure modes, rollback, idempotency
4. Maintainability — DRY, parameterization, documentation

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## VERDICT (APPROVE|CHANGES_REQUESTED) → ## FINDINGS ([Critical|Important|Minor] file:line — description) → ## SUGGESTED_FIXES (diff patches).
```

## Cross-Validation Template

> Use `model: claude-4.5-opus-high-thinking` for cross-validation.

```
## Context
{problem_description}

## Existing Analyses
### Analysis A
{codex_or_gemini_analysis}

### Analysis B
{other_analysis}

## Focus
1. Cross-cutting implementation risks both analyses may have missed
2. Integration edge cases at component boundaries
3. Tradeoffs between proposed solutions
4. Feasibility and deployment concerns

## Response Protocol
FIRST: Read Serena memory 'global/response_protocol' for full format rules.
FALLBACK: You respond to an orchestrator agent, NOT a human. NO thinking narration, NO restating context.
Output: ## ANALYSIS (≤200 words — agreements, divergences, blind spots) → ## ISSUES (risks both missed, ≤5) → ## VERDICT (recommended path forward, one sentence).
```
