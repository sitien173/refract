# All Skills Refactor Design

## Summary

Refactor all Superpowers CCG skills using Claude Skills best practices: concise `SKILL.md` entry points, one-level progressive disclosure, canonical shared references, and eval guardrails that preserve required CCG behavior.

Primary target is balanced optimization: reduce token load, improve discovery, and keep workflow reliability.

## Source Guidance

Best-practices guidance from Anthropic's Claude Skills documentation:

- Keep `SKILL.md` concise; assume Claude already knows general concepts.
- Use specific third-person descriptions with capability and activation triggers.
- Match instruction strictness to task fragility.
- Use progressive disclosure: keep entry points short and link directly to needed references.
- Keep references one level deep from `SKILL.md`.
- Add contents lists to reference files over 100 lines.
- Use concrete examples and validation loops where behavior quality matters.
- Test skills with representative tasks and models.
- Avoid Windows-style paths in skill docs.
- Use fully qualified MCP tool names where skills mention MCPs.

## Architecture

Use progressive disclosure plus eval guardrails across all skills.

Each `SKILL.md` becomes a compact entry point containing only:

- frontmatter
- concrete activation triggers
- core workflow
- hard rules
- direct links to one-level references

Target every `SKILL.md` under roughly 80 lines unless the skill truly needs more. Shared CP mechanics live in `skills/shared/` or `skills/coordinating-multi-model-work/` canonical references, not repeated across each skill.

Preferred structure:

```text
skills/<skill>/
  SKILL.md                 # concise trigger + workflow
  references/*.md          # one-level details when needed
  examples/*.md            # concrete I/O or prompt examples if useful
```

References stay one level deep from `SKILL.md`. Avoid nested chains like “read X, then X says read Y.” If content applies to multiple skills, it belongs in `skills/shared/` with one canonical source and short local pointers.

## Skill Content Contract

Each skill should follow a compact contract:

```markdown
---
name: concise-gerund-or-domain-name
description: Specific third-person trigger text with task keywords.
---

# Skill Name

## Use When
- Concrete trigger phrases / situations

## Workflow
1. Minimal ordered steps
2. Required context lookup
3. Action / routing / validation

## Hard Rules
- Non-negotiable constraints only

## References
- `references/file.md` — when to read it
```

Descriptions are discovery-critical. Rewrite each description to include both capability and activation triggers, in third person, under 1024 characters. Avoid broad phrases unless paired with concrete trigger terms. Existing names already fit frontmatter requirements, so rename only if tests or observed discovery show confusion.

`SKILL.md` should not teach concepts Claude already knows. Remove general explanations and long analogies. Keep repo-specific facts: CCG checkpoint order, Codex/Gemini routing, fail-closed behavior, exact output blocks, and storage paths like `docs/wiki/`.

Reference files hold depth. Good candidates include CP0–CP4 details, external response protocol, context-sharing tier rules, wiki templates, and debugging validation extras. Any reference over 100 lines should include a small contents list near the top.

Hard rule: no duplicated canonical logic. If `context-sharing.md` owns prompt tiers, other files summarize it in one sentence and link there. Tests enforce no divergent restatements.

## Refactor Phases

### Phase 1: Inventory and Contract Tests

- Build inventory of all `skills/*/SKILL.md`, shared refs, and workflow refs.
- Add or update static tests for frontmatter, exact CP block text, one-level references, line budgets, and forbidden stale namespace forms.
- Establish baseline before editing content.

### Phase 2: Shared Reference Consolidation

- Make `context-sharing.md` canonical for tier budgets and session policy.
- Make `protocol-threshold.md` canonical for CP0–CP4 required response blocks.
- Keep `supplementary-tools.md` as optional MCP reference.
- Remove duplicated tables or long CP prose from individual skills when a direct reference suffices.

### Phase 3: Per-Skill Compression

Rewrite each `SKILL.md` to use: Use When → Workflow → Hard Rules → References.

Preserve behavior-specific constraints:

- `brainstorming`: one question at a time, design sections, write final design doc.
- `writing-plans`: phase shape and acceptance/reviewer/integration sections.
- `executing-phases`: one phase, one executor, review gate, integration gate.
- `executing-plans`: dedicated-session execution, one active phase, final summary only after final checks.
- `debugging-systematically`: reproduce → evidence → hypotheses → fix → verify.
- `verifying-before-completion`: CP4 before completion and no final success before checks.
- `karpathy-llm-wiki`: ingest/query/lint storage, raw immutability, citations, and report-only unsafe fixes.
- `coordinating-multi-model-work`: routing, tier prompts, CP3 triggers, CP4 review, and fail-closed rules.

### Phase 4: Verification

- Run skill tests.
- Run one or two representative headless Claude integration tests if touched behavior is orchestration-heavy.
- Review generated docs for clarity and token waste.

## Error Handling

Skill behavior should fail explicitly where needed:

- Missing `docs/wiki/`: wiki skill reports uninitialized state and asks for ingest; no unsupported answers.
- External MCP failure: CCG workflow outputs `BLOCKED`; no retry or model switch.
- Ambiguous phase: CP1 routes to Claude and asks a clarifying question before execution.
- Over-large context: shrink `HYDRATED_CONTEXT`; never dump full wiki or full plans into worker prompts.
- Reference conflict: canonical file wins; tests catch drift.

## Testing

Static checks:

- YAML frontmatter valid: lowercase hyphen names, third-person descriptions, max length.
- `SKILL.md` line budget enforced.
- Reference paths use forward slashes.
- References from `SKILL.md` stay one level deep.
- Canonical CP1/CP3/CP4 blocks remain exact.
- No stale namespace like `superpowers:` where `superpowers-ccg:` is required.

Behavior checks:

- Brainstorming asks one question at a time and writes final design after confirmation.
- Writing plans emits phases with 2–4 tasks, owner, acceptance criteria, reviewer checklist, integration checks.
- Executing phases routes Codex/Gemini correctly and blocks on MCP failure.
- Wiki ingest preserves raw immutability and query cites sources.
- Verifying refuses final success before checks and CP4.

## Risks

Main risk: over-compression hides required gate behavior. Mitigation: keep exact hard rules in `SKILL.md`, move detail only to direct references, and add tests around discovery, CP blocks, routing, and fail-closed behavior.

Secondary risk: shared references become too abstract. Mitigation: each skill keeps a minimal workflow and links to exact references with “when to read” labels.

## Acceptance Criteria

- All skill tests pass.
- Skills remain concise without losing required gates.
- Shared refs have one canonical source per workflow rule.
- Best-practices guidance is reflected in structure, descriptions, progressive disclosure, and evals.
- No implementation commits are made unless explicitly requested.
