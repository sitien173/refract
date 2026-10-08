# Live Transcript UX Implementation Plan

**Design:** `docs/plans/live-transcript-ux/DESIGN.md`

### Phase 1: Persist complete tool activity

**Task Guide Input:** Extend the durable provider-neutral transcript contract to
retain available raw tool inputs and outputs for local dashboard display. Update
Claude, Codex, Pi, and Agy structured adapters without changing assistant text,
final result extraction, session handling, attempt lifecycle ordering, quota
logic, or non-streaming behavior. Replace prior tests that require tool payload
exclusion with explicit raw-payload persistence coverage. Verify database and
dashboard output preserve supported JSON values unchanged.

**Goal:** New jobs persist each provider's available tool details.

**Files:**
- Modify: `src/openmcp/backends/claude.py`
- Modify: `src/openmcp/backends/codex.py`
- Modify: `src/openmcp/backends/pi.py`
- Modify: `src/openmcp/backends/agy.py`
- Modify: `tests/test_streaming_backends.py`
- Modify: `tests/test_execution.py`
- Modify: `tests/test_dashboard.py`

**Tasks:**
1. Add failing provider fixtures for raw tool inputs and outputs.
2. Map available provider fields into normalized tool events.
3. Verify persistence and dashboard output retain nested payloads.
4. Preserve existing lifecycle, quota, and final-result behavior.

**Acceptance Criteria:**
- `tool.started.data` includes available raw tool input.
- `tool.completed.data` includes available raw tool output.
- Nested JSON values survive durable storage and dashboard retrieval.
- Missing provider details remain absent rather than fabricated.
- Existing transcript quotas remain unchanged.
- Assistant and final-result extraction remain unchanged.

**Reviewer Checklist:**
- Confirm each backend maps its real structured event shape.
- Confirm no diagnostics or unrelated provider events become public.
- Confirm tool payloads remain scoped to local transcript storage.
- Confirm stream ordering and attempt completion remain unchanged.

**Verification Checks:**
- `uv run pytest -q tests/test_streaming_backends.py tests/test_execution.py tests/test_dashboard.py`

**Commit:** `feat(streaming): persist raw tool transcript details`

### Phase 2: Build the conversation timeline

**Task Guide Input:** Redesign the job Live transcript as a chronological
conversation timeline. Merge raw tool inputs and outputs into expandable tool
entities. Improve assistant message readability. Keep tool details collapsed by
default. Implement reliable live-edge following, pause following after manual
upward scrolling, and expose a keyboard-accessible Jump to live control. Fix
variable-height virtualization so long messages and expanded tools never
overlap. Preserve reconnect, truncation, historical fallback, final-result
deduplication, and bounded DOM behavior.

**Goal:** Operators can follow assistant work and inspect every tool call.

**Files:**
- Modify: `web/src/hooks/useJobStream.js`
- Modify: `web/src/hooks/useJobStream.test.jsx`
- Modify: `web/src/components/JobTranscript.jsx`
- Modify: `web/src/components/JobTranscript.test.jsx`
- Modify: `web/src/components/JobDetails.test.jsx`
- Modify: `web/src/styles/app.css`

**Tasks:**
1. Add failing reducer tests for tool input and output merging.
2. Add failing component tests for disclosure and payload formatting.
3. Implement measured variable-height timeline virtualization.
4. Implement live-edge following, pause, and Jump to live behavior.

**Acceptance Criteria:**
- Assistant and tool entities retain chronological ordering.
- Tool rows expand to raw input and raw output.
- Structured payloads render as formatted JSON.
- Text payloads preserve line breaks.
- Long assistant messages never overlap later rows.
- Expanded tools never overlap later rows.
- New content follows only while at the live edge.
- Manual history inspection remains stable.
- DOM size remains bounded for large transcripts.

**Reviewer Checklist:**
- Confirm reducer matching cannot attach output to another tool.
- Confirm expansion works without mouse input.
- Confirm measured rows update after streaming and disclosure changes.
- Confirm auto-follow does not steal manual scroll position.
- Confirm existing terminal and truncation states remain correct.

**Verification Checks:**
- `npm --prefix web test -- --run web/src/hooks/useJobStream.test.jsx web/src/components/JobTranscript.test.jsx web/src/components/JobDetails.test.jsx`
- `npm --prefix web test`

**Commit:** `feat(dashboard): improve live transcript timeline`

### Phase 3: Package and verify the dashboard

**Task Guide Input:** Rebuild the packaged dashboard from the completed frontend
source. Replace generated hashed assets exactly as produced by Vite. Verify the
full Python and frontend suites. Inspect the referenced job details route at
desktop and narrow widths. Confirm assistant text, tool disclosure, scrolling,
status presentation, and variable-height layout. Do not change source behavior
unless verification exposes a requirement failure.

**Goal:** Ship matching static assets with browser-verified transcript UX.

**Files:**
- Modify: `src/openmcp/dashboard_static/index.html`
- Replace: `src/openmcp/dashboard_static/assets/`

**Tasks:**
1. Build the production dashboard into packaged static assets.
2. Run full backend and frontend verification.
3. Verify the referenced job route through Playwright.
4. Confirm generated asset references contain no stale bundles.

**Acceptance Criteria:**
- Packaged assets match the current frontend build.
- The referenced job page renders without transcript overlap.
- Tool disclosures remain keyboard and pointer accessible.
- Desktop and narrow layouts preserve readable content.
- No unexpected browser console errors remain.

**Reviewer Checklist:**
- Confirm generated files are build outputs only.
- Confirm stale hashed assets are removed.
- Confirm source and packaged behavior match.
- Confirm browser verification used the requested route.

**Verification Checks:**
- `npm --prefix web run build`
- `npm --prefix web test`
- `uv run pytest -q`
- `git diff --check`

**Commit:** `build(dashboard): package transcript improvements`
