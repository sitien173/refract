# CCG Workflow Architecture Diagrams

> Updated 2026-05-16 — includes stellaris reindex, CP3.5, CP4.5, failure paths.
> Render with any Mermaid-compatible tool.

## 1. High-Level System Architecture

```mermaid
graph TB
    USER[User Request]
    CLAUDE[Claude<br/>Planner / Reviewer / Integrator]
    CODEX[Codex MCP<br/>Default Executor]
    GEMINI[Gemini MCP<br/>UI-heavy Executor]
    STELLARIS[Stellaris MCP<br/>Semantic Search / Index]
    CAVECREW[cavecrew-reviewer<br/>Quality Review]

    USER --> CLAUDE
    CLAUDE -->|CP0 context| STELLARIS
    STELLARIS -->|search results| CLAUDE
    CLAUDE -->|CP2 execution| CODEX
    CLAUDE -->|CP2 execution| GEMINI
    CODEX -->|ERP v1.1| CLAUDE
    GEMINI -->|ERP v1.1| CLAUDE
    CLAUDE -->|reindex_file| STELLARIS
    CLAUDE -->|CP4.5 review| CAVECREW
    CAVECREW -->|findings| CLAUDE
```

## 2. Routing Decision Tree

```mermaid
flowchart TD
    PHASE[Phase from CP0] --> DECIDE{Task Category}

    DECIDE -->|Backend / Logic / API<br/>Tests / CI / Infra<br/>Bug fix / Debug<br/>Large refactor<br/>Data / ML| CODEX_R[CODEX]
    DECIDE -->|UI / CSS / Animation<br/>Canvas / SVG<br/>Multimodal input<br/>Large context >200K<br/>Visual regression / OCR<br/>PDF / diagram extraction| GEMINI_R[GEMINI]
    DECIDE -->|Architecture conflict<br/>Multi-domain uncertainty| CROSS[CROSS_VALIDATION<br/>Codex + Gemini]
    DECIDE -->|Docs / Coordination<br/>Planning / Review<br/>Simple edits<br/>Ambiguous / Unclear| CLAUDE_R[CLAUDE]

    CODEX_R --> SECURITY{Security /<br/>Compliance?}
    SECURITY -->|Yes| GATE[Mandatory Claude<br/>Review Gate]
    SECURITY -->|No| CP2

    GEMINI_R --> CP2[CP2 Execution]
    CROSS --> CP2
    CLAUDE_R --> DIRECT[Handle Directly]
    GATE --> CP2

    subgraph Tiebreakers
        direction LR
        T1["1. Hallucination-sensitive → Codex + review gate"]
        T2["2. Multimodal input → Gemini"]
        T3["3. Context >200K → Gemini"]
        T4["4. UI-dominant → Gemini"]
        T5["5. Else → Codex"]
    end
```

## 3. Full Checkpoint Flow

```mermaid
flowchart TD
    START([User Request]) --> CP0

    subgraph CP0 [CP0: Context Acquisition]
        WIKI{wiki useful?}
        WIKI -->|Yes| WIKI_LOOKUP[docs/wiki/ lookup]
        WIKI -->|No| SKIP_WIKI[skip]
        WIKI_LOOKUP --> STELLARIS_SEARCH[stellaris search_code<br/>MANDATORY]
        SKIP_WIKI --> STELLARIS_SEARCH
        STELLARIS_SEARCH -->|error / unavailable| BLOCKED_CP0([BLOCKED<br/>Stop before CP1])
        STELLARIS_SEARCH -->|success| DRILLDOWN[get_file_outline /<br/>get_file_folded /<br/>get_symbol]
        DRILLDOWN --> ARTIFACTS[Context Artifacts]
    end

    ARTIFACTS --> CP1

    subgraph CP1 [CP1: Phase Assessment & Routing]
        ASSESS[Summarize phase<br/>Classify task<br/>Choose model + Session-Policy]
        ASSESS --> CP1_BLOCK[/"# CP1 ROUTING DECISION"/]
    end

    CP1_BLOCK --> ROUTE{Route?}
    ROUTE -->|Claude| CLAUDE_WORK[Claude handles directly]
    ROUTE -->|Codex / Gemini / Cross-Val| CP2

    subgraph CP2 [CP2: External Execution]
        TIER{Session-Policy}
        TIER -->|FRESH| T1_CALL[Tier 1: Initial call<br/>≤1500 tokens]
        TIER -->|CONTINUE| T3_CALL[Tier 3: Continuation<br/>≤600 tokens]
        T1_CALL --> WORKER[Worker executes<br/>edits files via MCP]
        T3_CALL --> WORKER
        WORKER --> ERP[/"ERP v1.1 response<br/>## FILES MODIFIED"/]
        WORKER -->|MCP failure| BLOCKED_CP2([BLOCKED<br/>Ask human])
    end

    ERP --> REINDEX

    subgraph REINDEX [Stellaris Index Refresh]
        PARSE_FILES[Parse ## FILES MODIFIED]
        PARSE_FILES --> REINDEX_CALLS[reindex_file per file<br/>parallel, non-blocking]
    end

    REINDEX --> CP3_CHECK{CP3 trigger?}

    CP3_CHECK -->|Cross-validation /<br/>NO or WITH_DEBT /<br/>CLARIFICATIONS /<br/>CONTINUE_SESSION /<br/>overlapping edits| CP3
    CP3_CHECK -->|None| SKIP_CP3[Skip CP3]

    subgraph CP3 [CP3: Reconciliation]
        PARSE_ERP[Parse all ERP blocks]
        PARSE_ERP --> RESOLVE[Compare SUMMARY /<br/>FILES MODIFIED /<br/>SPEC COMPLIANCE /<br/>CLARIFICATIONS /<br/>NEXT STEPS]
        RESOLVE --> CP3_DECIDE{Decision}
        CP3_DECIDE -->|Proceed| CP3_BLOCK[/"# CP3 RECONCILIATION COMPLETE"/]
        CP3_DECIDE -->|Retry| CP2
        CP3_DECIDE -->|Ask user| HUMAN_INPUT([Ask User])
    end

    CP3_BLOCK --> CP35
    SKIP_CP3 --> CP35

    subgraph CP35 ["CP3.5: Integration Checks"]
        RUN_CHECKS[Run build / lint /<br/>type-check / tests]
        RUN_CHECKS -->|All pass| CHECKS_PASS[Record results]
        RUN_CHECKS -->|Any fail| CHECKS_FAIL[Record failure<br/>→ CP4 must FAIL]
        RUN_CHECKS -->|No checks declared| NO_CHECKS[Record 'none declared']
    end

    CHECKS_PASS --> CP4
    CHECKS_FAIL --> CP4
    NO_CHECKS --> CP4
    CLAUDE_WORK --> CP4

    subgraph CP4 [CP4: Phase Review]
        REVIEW[Review: user request /<br/>CP1 criteria / checklist /<br/>integration results]
        REVIEW --> CP4_BLOCK[/"# CP4 SPEC REVIEW COMPLETE<br/>PASS / PASS_WITH_DEBT / FAIL"/]
    end

    CP4_BLOCK --> CP45_CHECK{CP4 result?}
    CP45_CHECK -->|FAIL| DISPATCH_FIX[Dispatch Tier-2 fix<br/>or ask user]
    CP45_CHECK -->|PASS or PASS_WITH_DEBT| CP45

    subgraph CP45 ["CP4.5: Quality Review"]
        SPAWN[Spawn cavecrew-reviewer<br/>on ## FILES MODIFIED]
        SPAWN --> REVIEW_ITEMS[Check: edge cases /<br/>error handling / security /<br/>naming / duplication /<br/>correctness]
        REVIEW_ITEMS --> FINDINGS{Findings?}
        FINDINGS -->|CRITICAL or HIGH| DOWNGRADE_FAIL[Downgrade → FAIL]
        FINDINGS -->|MEDIUM| DOWNGRADE_DEBT[Downgrade PASS →<br/>PASS_WITH_DEBT]
        FINDINGS -->|LOW or None| NO_CHANGE[No downgrade]
        DOWNGRADE_FAIL --> CP45_BLOCK[/"# CP4.5 QUALITY REVIEW COMPLETE"/]
        DOWNGRADE_DEBT --> CP45_BLOCK
        NO_CHANGE --> CP45_BLOCK
    end

    CP45_BLOCK --> FINAL{Final status?}
    FINAL -->|PASS| DONE([Phase Complete])
    FINAL -->|PASS_WITH_DEBT| DONE_DEBT([Phase Complete<br/>with noted debt])
    FINAL -->|FAIL| FIX[Dispatch Tier-2 fix<br/>or ask user for CRITICAL]
    DISPATCH_FIX --> CP2

    style BLOCKED_CP0 fill:#e74c3c,color:#fff
    style BLOCKED_CP2 fill:#e74c3c,color:#fff
    style DONE fill:#2ecc71,color:#fff
    style DONE_DEBT fill:#f39c12,color:#fff
```

## 4. Tier Prompt System

```mermaid
flowchart LR
    subgraph "Tier 1: Fresh Session"
        T1[New SESSION_ID<br/>≤1500 tokens<br/>Full context bundle]
    end

    subgraph "Tier 2: Same-Phase Fix"
        T2[Reuse SESSION_ID<br/>≤400 tokens<br/>Delta only]
    end

    subgraph "Tier 3: Cross-Phase Continue"
        T3[Reuse SESSION_ID<br/>≤600 tokens<br/>New phase context]
    end

    T1 -->|"CP4/CP4.5 FAIL<br/>same phase"| T2
    T1 -->|"Phase complete<br/>next phase CONTINUE"| T3
    T2 -->|"Still failing"| T2
    T3 -->|"CP4/CP4.5 FAIL<br/>in continued phase"| T2
```

## 5. Failure & Recovery Paths

```mermaid
flowchart TD
    FAIL_TYPE{Failure Type}

    FAIL_TYPE -->|stellaris search_code<br/>error / unavailable| B1([BLOCKED<br/>Stop before CP1])
    FAIL_TYPE -->|MCP timeout /<br/>tool-unavailable /<br/>session-failed| B2([BLOCKED<br/>Ask human to retry<br/>or consent alternate])
    FAIL_TYPE -->|command line too long| B3([BLOCKED<br/>Use file-backed input])
    FAIL_TYPE -->|CP3.5 integration<br/>check failure| F1[CP4 must return FAIL<br/>→ Tier-2 fix]
    FAIL_TYPE -->|CP4.5 CRITICAL finding| F2[Downgrade to FAIL<br/>→ Ask user before fix]
    FAIL_TYPE -->|CP4.5 HIGH finding| F3[Downgrade to FAIL<br/>→ Tier-2 fix]
    FAIL_TYPE -->|ERP Meets Spec? NO| F4[CP3 reconciliation<br/>→ retry or ask user]

    style B1 fill:#e74c3c,color:#fff
    style B2 fill:#e74c3c,color:#fff
    style B3 fill:#e74c3c,color:#fff
    style F1 fill:#e67e22,color:#fff
    style F2 fill:#e67e22,color:#fff
    style F3 fill:#e67e22,color:#fff
    style F4 fill:#e67e22,color:#fff
```
