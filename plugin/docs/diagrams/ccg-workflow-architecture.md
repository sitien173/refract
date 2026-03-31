# CCG Workflow Architecture Diagrams

> Generated from CCG workflow analysis on 2026-03-24.
> Render with any Mermaid-compatible tool.

## 1. High-Level System Architecture

```mermaid
graph TB
    USER[User Request]
    CLAUDE[Claude Orchestrator]
    CODEX[Codex MCP<br/>Backend and Systems]
    GEMINI[Gemini MCP<br/>Frontend]
    OPUS[Opus Review]

    USER --> CLAUDE
    CLAUDE --> CODEX
    CLAUDE --> GEMINI
    CODEX --> OPUS
    GEMINI --> OPUS
    OPUS --> CLAUDE
```

## 2. Routing Decision Tree

```mermaid
flowchart LR
    TASK[Task] --> DECIDE{Domain}
    DECIDE -->|Backend, scripts, CI/CD, infra| CODEX_R[CODEX]
    DECIDE -->|UI, components, styling| GEMINI_R[GEMINI]
    DECIDE -->|Full-stack or unclear| CROSS[CROSS_VALIDATION]
    DECIDE -->|Docs only| CLAUDE_R[CLAUDE]
```

## 3. Checkpoint Flow

```mermaid
flowchart TD
    START[User Request] --> CP1[CP1: Routing]
    CP1 --> MODEL[External Model]
    MODEL --> CP2[CP2: Re-evaluate if stalled]
    CP2 --> CP3[CP3: Verification and Opus review]
    CP3 --> DONE[Complete]
```
