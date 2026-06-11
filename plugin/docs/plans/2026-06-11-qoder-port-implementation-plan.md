# Qoder Port — Implementation Plan
_Date: 2026-06-11 | Option A: shallow port (skills + hooks)_

## Context

Port superpowers-ccg to Qoder's extension system so users can install the plugin inside Qoder (IDE / CLI). Qoder's extension model supports Skills (SKILL.md — already compatible), Commands, MCP servers, and Hooks via `~/.qoder/settings.json`. The gap is: Qoder has no `SessionStart` event, so resume injection is handled via `UserPromptSubmit` instead.

Key assumption: Qoder's plugin-root env variable is `$QODER_PLUGIN_ROOT` (analogous to Codex's `$PLUGIN_ROOT`). If Qoder uses a different name this is the only thing to update.

---

## Phase 1 — Qoder plugin manifest, hooks, and script extensions

**Owner:** `coordinator`

**Goal:** Add all files needed to make superpowers-ccg installable and functional in Qoder: a plugin manifest, a Qoder hooks JSON, `--qoder` output branches in both hook scripts, and install docs in README.

**Files:**
- Create: `.qoder-plugin/plugin.json`
- Create: `hooks/hooks-qoder.json`
- Modify: `hooks/superpowers-ccg-session-start.sh`
- Modify: `hooks/superpowers-ccg-user-prompt-submit.sh`
- Modify: `README.md`

**Tasks:**
1. Create `.qoder-plugin/plugin.json` — Qoder plugin manifest with name, version, skills path, hooks path, and mcpServers path.
2. Create `hooks/hooks-qoder.json` — two `UserPromptSubmit` entries: one calling `session-start.sh --qoder` (for resume + compact context injection) and one calling `user-prompt-submit.sh --qoder` (for handover summary).
3. Add `--qoder` branch to `hooks/superpowers-ccg-session-start.sh` — emit `hookEventName: "UserPromptSubmit"` output (mirrors the `--codex` pattern in user-prompt-submit.sh; reuses existing `materialize_shared`, `build_resume_context`, and `escape_for_json` logic).
4. Add `--qoder` branch to `hooks/superpowers-ccg-user-prompt-submit.sh` — emit same dual `systemMessage` + `hookSpecificOutput` format as the `--codex` branch.
5. Add **Qoder** install section to `README.md` under `## Install` (after the Codex block).

**Acceptance Criteria:**
- `.qoder-plugin/plugin.json` is valid JSON referencing `./skills/`, `./hooks/hooks-qoder.json`, `./.mcp.json`.
- `hooks/hooks-qoder.json` is valid JSON with `UserPromptSubmit` array containing two hook entries.
- `bash hooks/superpowers-ccg-session-start.sh --qoder` exits 0 and emits valid JSON with `hookEventName: "UserPromptSubmit"`.
- `bash hooks/superpowers-ccg-user-prompt-submit.sh --qoder` exits 0 and emits valid JSON with both `systemMessage` and `hookSpecificOutput` fields (when no active handover, exits 0 with no output).
- README Qoder section documents install steps and the `$QODER_PLUGIN_ROOT` assumption.

**Reviewer Checklist:**
- `.qoder-plugin/plugin.json` fields match Qoder's documented plugin component model (skills / commands / mcpServers).
- Both `--qoder` branches are guarded so they don't affect existing `--codex` or default (Claude) paths.
- No new dependencies introduced in the shell scripts.
- `materialize_shared` is NOT duplicated — reused as-is from session-start.sh.

**Integration Checks:**
- `bash -n hooks/superpowers-ccg-session-start.sh` (syntax check)
- `bash -n hooks/superpowers-ccg-user-prompt-submit.sh` (syntax check)
- `python -m json.tool .qoder-plugin/plugin.json` (JSON validity)
- `python -m json.tool hooks/hooks-qoder.json` (JSON validity)
- `bash hooks/superpowers-ccg-session-start.sh --qoder | python -m json.tool` (valid JSON output)
