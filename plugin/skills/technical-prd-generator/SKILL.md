---
name: technical-prd-generator
description: generate, improve, or review product requirements documents, technical prds, software requirement specs, mvp specs, feature briefs, and build plans from rough user requirements. use when the user asks to turn an idea, product concept, technical architecture, market problem, or notes into a strong prd with goals, non-goals, personas, requirements, success metrics, architecture, risks, milestones, and acceptance criteria. also use for prd critique, strengthening vague requirements, adding research-backed constraints, or converting a previous answer into a reusable product spec.
---

# Technical PRD Generator

## Objective

Turn rough product or technical requirements into a clear, buildable, research-backed PRD. Produce a document that a product manager, founder, engineering lead, or agent can use to decide what to build, what not to build, how to validate it, and how to measure success.

## Operating Principles

- Prefer a strong, opinionated recommendation over a generic menu of options.
- State assumptions explicitly when requirements are incomplete, then continue with a best-effort PRD.
- Do not promise guaranteed outcomes when they depend on external systems, markets, networks, regulations, or user behavior.
- Make requirements testable: use IDs, priorities, measurable targets, and acceptance criteria.
- Separate product goals from implementation details, but include technical architecture when the product is technical.
- Include non-goals to prevent scope creep.
- Include risks, mitigations, and validation milestones.
- Preserve the user's constraints and domain language.
- Avoid filler, obvious textbook definitions, and vague success metrics.

## Workflow

1. **Extract the brief**
   - Identify product type, target users, problem, goals, constraints, existing assets, desired platform, technical preferences, and business context.
   - If a critical input is missing, infer a reasonable default and label it as an assumption. Ask at most 2 clarifying questions only when the PRD would be misleading without them.

2. **Research when needed**
   - For current, niche, technical, legal, platform, security, pricing, market, or ecosystem facts, research when available unless the user explicitly says not to.
   - Prefer primary sources for technical/platform claims: official docs, standards, vendor docs, project docs, legal/regulatory sources, and reputable research.
   - Cite load-bearing facts directly in the PRD.
   - See `references/research-protocol.md` for citation and source-selection rules.

3. **Choose the product stance**
   - Compare realistic approaches if there are meaningful alternatives.
   - Recommend one primary approach and explain why it best satisfies the stated constraints.
   - Include a reality check where the user's goal has unavoidable limits.

4. **Generate the PRD**
   - Use the default structure in `references/prd-blueprint.md`.
   - Adapt sections to the domain; omit irrelevant sections only when they would add noise.
   - For technical products, include architecture, security/privacy, operations, telemetry, failure modes, and rollout.

5. **Validate quality before responding**
   - Run the checklist in `references/quality-checklist.md` mentally before final output.
   - Ensure every P0 requirement is actionable and testable.
   - Ensure the final recommendation is clear.

6. **Save and hand off**
   - Save the final PRD to `docs/plans/YYYY-MM-DD-<product>-prd.md` and report the path (same convention `brainstorming` uses for design docs).
   - Offer to turn the PRD into a phase-based implementation plan via `writing-plans`. Commit only if the user asks.

## Default Output Behavior

Use a polished PRD format with headings and tables. Prefer this ordering:

1. Title and product summary
2. Reality check / key recommendation
3. Problem statement
4. Goals and non-goals
5. Target users and personas
6. Success metrics
7. Core user stories
8. Functional requirements with IDs and priorities
9. Non-functional requirements
10. Technical architecture / system design
11. MVP scope and out-of-scope items
12. UX / user flows
13. Data, privacy, security, compliance, and safety requirements
14. Acceptance criteria and test plan
15. Risks and mitigations
16. Milestones / rollout plan
17. Open questions
18. Final decision

When the user asks for a shorter artifact, output a compact PRD with the same logic but fewer details.

## Requirement Formatting

Use stable IDs and priorities:

- `FR-001`, `FR-002` for functional requirements.
- `NFR-001`, `NFR-002` for non-functional requirements.
- `SEC-001`, `PRIV-001`, `OPS-001`, `QA-001`, or domain-specific prefixes when useful.
- Priorities: `P0` must ship, `P1` should ship soon, `P2` later/optional.

Requirement rows should answer: what must happen, why it matters when non-obvious, and how it can be verified.

## Technical PRD Standards

For software, networking, infrastructure, security, AI, fintech, health, games, or developer-tool products, include:

- System architecture diagram in text form.
- Client/server/component responsibilities.
- State transitions and failure handling.
- Performance budgets and measurable targets.
- Security model and privilege boundaries.
- Logging, telemetry, and diagnostics.
- Deployment, operations, rollback, and support expectations.
- Compatibility matrix when platform details matter.
- Abuse, safety, compliance, and anti-cheat/anti-fraud concerns when relevant.

## Style Rules

- Write in a direct, senior product/engineering style.
- Be concrete and decisive.
- Use tables for dense requirements.
- Include concise explanations before long tables so the PRD does not feel mechanical.
- Avoid saying “it depends” without giving a decision rule.
- End with a short final recommendation or product rule.

## Routing

PRD authoring is a Gate-1 ideation task — the coordinator handles it directly, like `brainstorming`. Route to a worker only when a sub-task is clearly side-owned (e.g. a large-context research sweep → Gemini). Follow `coordinating-multi-model-work` for routing and gate semantics.

## References

- Use `references/prd-blueprint.md` for the full PRD section blueprint and templates.
- Use `references/research-protocol.md` when the PRD needs current or technical facts.
- Use `references/quality-checklist.md` before finalizing the PRD.
- Use `references/example-patterns.md` for style patterns and sample snippets.
- `skills/coordinating-multi-model-work/SKILL.md` — 3-gate workflow and routing.
- `skills/writing-plans/SKILL.md` — turn the saved PRD into a phase-based plan.
