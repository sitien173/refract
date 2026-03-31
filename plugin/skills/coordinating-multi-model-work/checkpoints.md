# Collaboration Checkpoints

## Overview

Checkpoints exist to control routing and keep the orchestrator thread small.

## CP1: Task Analysis

- Reduce the work to one bounded task.
- Prefer one worker.
- Record routing in one short block.

## CP2: Mid-Review

Trigger only when:
- 2 or more attempts have failed on the same bounded task
- the worker returns blocking questions
- the task still has unresolved cross-domain ambiguity

Before escalating to `CROSS_VALIDATION`, first narrow the task further or split it.

## CP3: Quality Gate

- Review the artifact, not the whole session narrative.
- If code changed, run the Opus review chain.
- If no code changed, skip quality review.

## User Override

- "Use Codex" / "Use Gemini" / "Cross-validate" force corresponding routing.
- "Do not use external models" forces `CLAUDE` for docs and coordination only.
