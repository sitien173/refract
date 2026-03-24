# CCCG Workflow Architecture Diagrams

> Generated from 3-way CROSS_VALIDATION (Codex + Gemini + Cursor) analysis on 2026-03-24.
> Render with any Mermaid-compatible tool (GitHub, VS Code, mermaid.live).

---

## 1. High-Level System Architecture

```mermaid
graph TB
    subgraph USER["👤 User"]
        REQ[User Request]
        FB[Feedback / Override]
    end

    subgraph CLAUDE["🧠 Claude Opus — Orchestrator"]
        direction TB
        SKILL[Skill Discovery<br><i>1% Rule</i>]
        CLASSIFY[Task Complexity<br>Classification]
        ROUTE[Semantic Routing<br>Decision]
        CP1[CP1: Task Analysis]
        CP2[CP2: Mid-Review]
        CP3[CP3: Quality Gate]
        INTEGRATE[Result Integration<br>& Arbitration]
    end

    subgraph EXTERNAL["⚡ External Models — Implementation"]
        direction LR
        CODEX["🔧 Codex MCP<br><i>Backend: API, DB,<br>auth, algorithms</i>"]
        GEMINI["🎨 Gemini MCP<br><i>Frontend: UI,<br>components, styles</i>"]
        CURSOR["🔨 Cursor MCP<br><i>General: debug,<br>refactor, DevOps</i>"]
    end

    subgraph REVIEW["🔍 Quality Review"]
        direction LR
        OPUS_REV["Opus Reviewer<br><i>Reviews Cursor's work</i>"]
        CURSOR_REV["Cursor Reviewer<br><i>Reviews Codex/Gemini work</i>"]
    end

    subgraph GATE["🚧 Fail-Closed Gate"]
        STRICT[Strict Mode<br>BLOCKED on failure]
        DEGRADED[Degraded Mode<br>Unverified proposal]
        INCIDENT[Incident Mode<br>Pause for user]
    end

    REQ --> SKILL
    SKILL --> CLASSIFY
    CLASSIFY --> ROUTE
    ROUTE --> CP1
    CP1 -->|"Routing != CLAUDE"| GATE
    GATE --> CODEX
    GATE --> GEMINI
    GATE --> CURSOR
    CODEX --> CP3
    GEMINI --> CP3
    CURSOR --> CP3
    CP3 --> CURSOR_REV
    CP3 --> OPUS_REV
    CURSOR_REV --> INTEGRATE
    OPUS_REV --> INTEGRATE
    INTEGRATE --> FB
    FB --> CLAUDE
    CP2 -.->|"retries>=2 / stall / ambiguity"| ROUTE
```

---

## 2. Complete Task Lifecycle (Step-by-Step)

```mermaid
flowchart TD
    START([User Request]) --> SKILL_CHECK{Skill applies?<br><i>1% Rule</i>}
    SKILL_CHECK -->|Yes| LOAD_SKILL[Load skill via<br>Skill tool]
    SKILL_CHECK -->|No| RESPOND([Direct response])

    LOAD_SKILL --> CLASSIFY{Classify<br>Complexity}
    CLASSIFY -->|Trivial| TRIVIAL[Compact CP1<br>Route: CLAUDE<br>Skip review]
    CLASSIFY -->|Standard| STANDARD[Full CP1 block<br>Standard review]
    CLASSIFY -->|Critical| CRITICAL[Full CP1 block<br>Cross-validation<br>Enhanced review]

    TRIVIAL --> IMPLEMENT_T[Execute directly]
    IMPLEMENT_T --> COMPACT_CP3["[CP3] Verified: evidence"]
    COMPACT_CP3 --> DONE([Complete])

    STANDARD --> ROUTE_S{Semantic<br>Routing}
    CRITICAL --> ROUTE_C{Semantic<br>Routing}

    ROUTE_S --> ENFORCE{Enforcement<br>Mode}
    ROUTE_C --> ENFORCE

    ENFORCE -->|"auth/payment/core"| STRICT_M[Strict Mode]
    ENFORCE -->|"single-file/config"| DEGRADED_M[Degraded Mode]

    STRICT_M --> MCP_CALL[Call MCP Tool]
    DEGRADED_M --> MCP_CALL

    MCP_CALL -->|Success| IMPL_DONE[Implementation<br>Complete]
    MCP_CALL -->|Fail + Strict| BLOCKED([BLOCKED<br>Stop & report])
    MCP_CALL -->|"Fail + Degraded"| UNVERIFIED["⚠️ Unverified<br>Proposal"]
    UNVERIFIED -->|User approves| IMPL_DONE
    UNVERIFIED -->|User rejects| BLOCKED

    MCP_CALL -->|"3+ failures"| INCIDENT_M[Incident Mode<br>Pause for user]
    INCIDENT_M -->|Retry| MCP_CALL
    INCIDENT_M -->|Manual override| IMPL_DONE
    INCIDENT_M -->|Troubleshoot| BLOCKED

    IMPL_DONE --> CP3_FULL[CP3: Quality Gate]

    CP3_FULL --> SPEC_REV{Spec Review<br><i>Opus</i>}
    SPEC_REV -->|Pass| QUAL_REV{Quality Review<br><i>Deterministic</i>}
    SPEC_REV -->|Fail| FIX_SPEC[Implementer<br>fixes spec gaps]
    FIX_SPEC --> SPEC_REV

    QUAL_REV -->|"Codex/Gemini implemented"| CURSOR_REVIEWS[Cursor reviews]
    QUAL_REV -->|"Cursor implemented"| OPUS_REVIEWS[Opus reviews]

    CURSOR_REVIEWS -->|Approve| DONE
    CURSOR_REVIEWS -->|"Issues (≤3 loops)"| FIX_Q[Fix quality issues]
    FIX_Q --> CURSOR_REVIEWS

    OPUS_REVIEWS -->|Approve| DONE
    OPUS_REVIEWS -->|"Issues (≤3 loops)"| FIX_Q2[Fix quality issues]
    FIX_Q2 --> OPUS_REVIEWS

    CURSOR_REVIEWS -->|"Loop limit"| ESCALATE([Escalate to user])
    OPUS_REVIEWS -->|"Loop limit"| ESCALATE
```

---

## 3. Multi-Model Routing Decision Tree

```mermaid
flowchart LR
    TASK[Task] --> ANALYZE{Analyze<br>Domain}

    ANALYZE -->|"API, DB, auth,<br>algorithms, security"| CODEX_R["CODEX<br>mcp__codex__codex"]
    ANALYZE -->|"UI, components,<br>styles, interactions"| GEMINI_R["GEMINI<br>mcp__gemini__gemini"]
    ANALYZE -->|"Debug, refactor,<br>DevOps, scripts"| CURSOR_R["CURSOR<br>mcp__cursor__cursor"]
    ANALYZE -->|"Full-stack,<br>uncertain,<br>architectural"| CROSS["CROSS_VALIDATION<br>Parallel: Codex+Gemini<br>±Cursor"]
    ANALYZE -->|"Docs only,<br>coordination"| CLAUDE_R["CLAUDE<br>Orchestrator"]

    CODEX_R --> REV_C[Reviewer: Cursor]
    GEMINI_R --> REV_C
    CURSOR_R --> REV_O[Reviewer: Opus]
    CROSS --> REV_BOTH["Reviewer: Depends<br>on implementer"]
    CLAUDE_R --> NO_REV[No review needed]
```

---

## 4. Checkpoint Protocol Flow

```mermaid
sequenceDiagram
    participant U as User
    participant C as Claude (Orchestrator)
    participant M as External Model
    participant R as Quality Reviewer
    participant G as GATE.md

    U->>C: Task request
    Note over C: Classify: Trivial/Standard/Critical

    rect rgb(230, 245, 255)
        Note over C: CP1 — Task Analysis
        C->>C: Semantic routing decision
        C->>C: Set enforcement mode
        C->>G: Check GATE (Routing != CLAUDE?)
        G-->>C: Proceed / BLOCKED
    end

    C->>M: Route to Codex/Gemini/Cursor
    M-->>C: Implementation result

    opt CP2 Triggers Fire
        rect rgb(255, 245, 230)
            Note over C: CP2 — Mid-Review
            Note over C: Retries≥2 / Stall / Ambiguity
            C->>M: Cross-validate or re-route
            M-->>C: Updated result
        end
    end

    rect rgb(230, 255, 230)
        Note over C: CP3 — Quality Gate
        C->>R: Spec review (Opus)
        R-->>C: Pass/Fail
        C->>R: Quality review (Cursor or Opus)
        R-->>C: Approve / Issues
    end

    alt All Pass
        C->>U: Verified result + evidence
    else Issues Found
        C->>M: Fix issues (max 3-4 loops)
        M-->>C: Fixed
        C->>R: Re-review
    else BLOCKED
        C->>U: BLOCKED + retry instructions
    end
```

---

## 5. Skills Composition Pipeline

```mermaid
flowchart LR
    subgraph "Phase 1: Design"
        BS["/brainstorm<br>brainstorming"] --> WP["/write-plan<br>writing-plans"]
    end

    subgraph "Phase 2: Execution"
        WP -->|"Same session"| SDA["developing-with-<br>subagents"]
        WP -->|"Parallel session"| EP["/execute-plan<br>executing-plans"]
    end

    subgraph "Phase 3: Quality"
        SDA --> VBC["verifying-before-<br>completion"]
        EP --> VBC
        SDA --> RCR["requesting-<br>code-review"]
        EP --> RCR
    end

    subgraph "Phase 4: Complete"
        VBC --> FDB["finishing-<br>development-branches"]
        RCR --> FDB
    end

    subgraph "Cross-Cutting Skills"
        TDD["practicing-TDD"]
        DEBUG["debugging-<br>systematically"]
        WORKTREE["using-git-<br>worktrees"]
        PARALLEL["dispatching-<br>parallel-agents"]
    end

    BS -.-> WORKTREE
    SDA -.-> TDD
    EP -.-> TDD
    SDA -.-> DEBUG
    SDA -.-> PARALLEL
```

---

## 6. Enforcement Modes & Failure Handling

```mermaid
flowchart TD
    MCP[MCP Call] --> SUCCESS{Success?}
    SUCCESS -->|Yes| EVIDENCE[Record Evidence<br>Proceed]

    SUCCESS -->|No| COUNT{Consecutive<br>failures ≥ 3?}
    COUNT -->|Yes| INCIDENT["🔴 INCIDENT MODE<br>Pause for user decision<br>(1) Retry<br>(2) Manual override<br>(3) Troubleshoot"]

    COUNT -->|No| MODE{Enforcement<br>Mode?}

    MODE -->|"Strict<br>(auth/payment/core)"| BLOCKED_S["🛑 BLOCKED<br>No proceed.<br>Provide retry command."]

    MODE -->|"Degraded<br>(config/single-file)"| PROPOSAL["⚠️ UNVERIFIED PROPOSAL<br>Claude generates proposal<br>marked as unverified"]
    PROPOSAL --> USER_APPROVE{User<br>approves?}
    USER_APPROVE -->|Yes| CONTINUE[Proceed<br>with warning]
    USER_APPROVE -->|No| BLOCKED_D["🛑 BLOCKED"]

    style BLOCKED_S fill:#ff6b6b,color:#fff
    style BLOCKED_D fill:#ff6b6b,color:#fff
    style INCIDENT fill:#ffa500,color:#fff
    style PROPOSAL fill:#ffd93d,color:#000
    style EVIDENCE fill:#6bcb77,color:#fff
```
