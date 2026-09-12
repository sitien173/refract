# Live Transcript Filters Implementation Plan

**Design:** `docs/plans/live-transcript-filters/DESIGN.md`

### Phase 1: Normalize transcript categories safely

**Task Guide Input:** Extend the additive provider-neutral transcript contract
for safe content classification. Mark verified shell and terminal tool events as
`command`; retain other tools as `tool_call`. Add recorder support for the future
`assistant.reasoning_summary.delta` event while keeping unverified thinking,
reasoning, diagnostics, prompts, and provider internals excluded. Preserve raw
local tool values, lifecycle matching, durable ordering, quotas, pagination,
retention, and non-streaming results. Use exact provider event types or exact
test-backed names only.

**Goal:** New transcript events carry safe semantic categories.

**Files:**
- Modify: `src/openmcp/backends/__init__.py`
- Modify: `src/openmcp/backends/claude.py`
- Modify: `src/openmcp/backends/codex.py`
- Modify: `src/openmcp/backends/pi.py`
- Modify: `src/openmcp/backends/agy.py`
- Modify: `src/openmcp/streaming.py`
- Modify: `tests/test_streaming_backends.py`
- Modify: `tests/test_execution.py`
- Modify: `tests/test_streaming.py`

**Tasks:**
1. Add failing fixtures for exact Command classification.
2. Add negative fixtures for hidden or generic reasoning.
3. Add an exact shared activity classifier.
4. Add additive `data.activity` normalization.
5. Generalize text splitting for explicit reasoning summaries.
6. Preserve all existing lifecycle and payload behavior.

**Acceptance Criteria:**
- Verified shell activity emits `activity: "command"`.
- Other tools emit or default to `activity: "tool_call"`.
- Classification never examines tool payloads or substrings.
- Generic thinking and reasoning remain excluded.
- Reasoning-summary events obey existing text limits.
- Raw input and output preserve absent and falsy distinctions.
- Existing quotas, cursor semantics, and results remain unchanged.

**Reviewer Checklist:**
- Confirm every enabled alias has a provider fixture.
- Confirm hidden reasoning cannot enter durable events.
- Confirm provider diagnostics and prompts remain excluded.
- Confirm tool completion matches the correct entity.
- Confirm no database migration or quota change appears.

**Verification Checks:**
- `uv run pytest -q tests/test_streaming_backends.py tests/test_streaming.py tests/test_execution.py`
- `git diff --check`

**Commit:** `feat(streaming): classify transcript activities`

### Phase 2: Add transcript filter controls

**Task Guide Input:** Add accessible Live transcript filters with Role checkboxes
for User and Assistant and Content checkboxes for Text, Thinking, Tool Call, and
Command. Use OR within groups and AND across groups. Add one User/Text entry from
the stored `job.prompt` only. Add Assistant/Thinking rendering for safe normalized
summaries. Split Commands from other tools while preserving expandable raw local
input and output. Filter before virtualization. Preserve chronological ordering,
retry grouping, bounded rows, dynamic measurements, follow-live intent, reconnect,
truncation, unavailable history, and final-result behavior.

**Goal:** Operators can focus the transcript without losing context or position.

**Files:**
- Modify: `web/src/hooks/useJobStream.js`
- Modify: `web/src/hooks/useJobStream.test.jsx`
- Modify: `web/src/components/JobTranscript.jsx`
- Modify: `web/src/components/JobTranscript.test.jsx`
- Modify: `web/src/components/JobDetails.jsx`
- Modify: `web/src/components/JobDetails.test.jsx`
- Modify: `web/src/integration/dashboard-flow.test.jsx`
- Modify: `web/src/styles/app.css`

**Tasks:**
1. Add failing reducer tests for semantic categories.
2. Add failing tests for filter defaults and combinations.
3. Pass only stored `job.prompt` into the transcript.
4. Add the two native checkbox groups.
5. Add Thinking, Command, empty, and reset rendering.
6. Preserve virtualization and follow-live state across filtering.

**Acceptance Criteria:**
- User and Assistant combine using role OR semantics.
- Content selections combine using content OR semantics.
- Role and content groups combine using AND semantics.
- Defaults enable everything except Thinking.
- User Text exactly matches stored `jobs.prompt`.
- User Text appears once and never exposes expanded history.
- Thinking renders only normalized summaries.
- Commands and Tool Calls remain distinct.
- Empty matches show the approved message and reset action.
- Unavailable history remains unavailable.
- Filtering never resumes manually paused following.
- Filtered and expanded rows remain measured and bounded.

**Reviewer Checklist:**
- Confirm no prompt source except `job.prompt` is used.
- Confirm structural notices retain correct visibility.
- Confirm historical tools default to Tool Call.
- Confirm checkbox semantics and labels are accessible.
- Confirm empty filtering differs from unavailable streaming.
- Confirm Command disclosures preserve raw payload behavior.

**Verification Checks:**
- `npm --prefix web test -- src/hooks/useJobStream.test.jsx src/components/JobTranscript.test.jsx src/components/JobDetails.test.jsx src/integration/dashboard-flow.test.jsx`
- `npm --prefix web test -- --poolOptions.threads.maxThreads=2`
- `git diff --check`

**Commit:** `feat(dashboard): filter live transcript entries`

### Phase 3: Package and verify transcript filters

**Task Guide Input:** Rebuild packaged dashboard assets after the completed
backend and frontend changes. Run full relevant Python and frontend suites.
Restart the local daemon so browser verification uses current backend code.
Verify the real Job Detail route at desktop and narrow widths. Exercise defaults,
role and content combinations, filtered-empty reset, Command disclosure,
follow-live pause, and unavailable-history behavior. Confirm generated hashes
match source and no stale assets remain.

**Goal:** Ship source-matched, browser-verified transcript filtering.

**Files:**
- Modify: `src/openmcp/dashboard_static/index.html`
- Replace: `src/openmcp/dashboard_static/assets/`

**Tasks:**
1. Build production dashboard assets.
2. Run full relevant backend and frontend verification.
3. Restart the local dashboard server.
4. Verify filters through Playwright.
5. Confirm generated asset parity and diff scope.

**Acceptance Criteria:**
- Packaged assets match current frontend source.
- Every filter is keyboard and pointer accessible.
- Default and combined filtering match the design.
- Filtering preserves chronology and follow-live intent.
- Expanded Commands and Tool Calls remain readable.
- Desktop and narrow layouts remain usable.
- Security exclusions hold in API and rendered HTML.
- No unexpected browser console errors remain.

**Reviewer Checklist:**
- Confirm generated changes contain build output only.
- Confirm stale hashes are removed.
- Confirm browser verification used current server code.
- Confirm historical limitations remain explicit.
- Confirm hidden reasoning and expanded prompts remain absent.

**Verification Checks:**
- `npm --prefix web run build`
- `uv run pytest -q`
- `npm --prefix web test -- --poolOptions.threads.maxThreads=2`
- `git diff --check`

**Commit:** `build(dashboard): package transcript filters`
