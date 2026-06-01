# Research and Citation Protocol

Use this protocol when a PRD relies on facts that may be current, niche, technical, regulatory, market-specific, platform-specific, or otherwise easy to misremember.

## When to Research

Research before finalizing claims about:
- Current product capabilities, pricing, limits, rules, or availability.
- Laws, regulations, platform policies, app store rules, anti-cheat rules, payment rules, privacy rules, and security requirements.
- Technical libraries, protocols, cloud providers, SDKs, operating system behavior, and hardware specs.
- Competitive landscape and market claims.
- Sports, games, network infrastructure, geographies, or routing where details change.
- Any unfamiliar term, acronym, vendor, or tool named by the user.

If the user explicitly says not to browse, avoid external research and label factual uncertainty.

## Source Selection

Prefer these sources in order:
1. Official documentation and primary sources.
2. Standards bodies, regulatory bodies, or legal text.
3. Vendor/project documentation and release notes.
4. Reputable technical blogs from maintainers or recognized experts.
5. Reputable news/research sources for market or current-event facts.

Avoid relying on SEO summaries, scraped docs, low-quality blogs, or unsourced forum claims unless they are the only evidence and you label them as weak.

## Citation Behavior

- Cite load-bearing claims directly where they appear.
- Do not collect citations in one unsupported block at the end.
- Use citations for facts that influence requirements, architecture, risk, or compliance.
- Do not cite obvious reasoning or assumptions.
- When sources conflict, mention the conflict and choose a conservative product requirement.

## How to Use Research in a PRD

Research should improve requirements, not create a literature review. Convert facts into build decisions:

- Platform policy -> compliance requirement.
- Protocol behavior -> architecture decision.
- Cloud limit -> capacity requirement.
- Anti-cheat rule -> explicit non-goal/safety requirement.
- Pricing or bandwidth limit -> operational risk and metric.

## Reality-Check Pattern

When the user's desired outcome is not fully controllable, include a reality check:

```markdown
A product cannot guarantee [outcome] because [external dependency]. It can control [specific mechanisms]. Therefore, the MVP should [decision] and measure [metric] before claiming success.
```

## Technical Comparison Pattern

When comparing technologies:

```markdown
| Criterion | Option A | Option B | Winner |
|---|---:|---:|---|
| local overhead | low | medium | option a |
| operational complexity | medium | high | option a |
```

Then state the decision:

```markdown
Choose [option] as the default because [top reasons]. Use [alternative] only when [condition].
```
