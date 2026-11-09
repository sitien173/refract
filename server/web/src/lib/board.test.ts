import { describe, expect, it } from "vitest";
import type { CardSummary } from "../api";
import { BOARD_COLUMNS, COLUMN_LABELS, diffCardMoves, formatMoveAnnouncement, formatRelativeTime, shortCardId, sortCards } from "./board";

const card = (id: string, overrides: Partial<CardSummary> = {}): CardSummary => ({
  id,
  project_id: "p1",
  project_root: "/path/to/p1",
  title: `Title ${id}`,
  state: "todo",
  job_ids: [],
  created_at: "2026-11-08T01:00:00Z",
  updated_at: "2026-11-08T01:00:00Z",
  ...overrides,
});

describe("board logic", () => {
  it("defines columns in exact order and labels", () => {
    expect(BOARD_COLUMNS).toEqual(["todo", "in_progress", "in_review", "done", "cancelled"]);
    expect(COLUMN_LABELS).toEqual({
      todo: "TODO",
      in_progress: "IN PROGRESS",
      in_review: "IN REVIEW",
      done: "DONE",
      cancelled: "CANCELLED",
    });
  });

  it("sorts TODO by created_at ascending", () => {
    const c1 = card("1", { created_at: "2026-11-08T03:00:00Z" });
    const c2 = card("2", { created_at: "2026-11-08T01:00:00Z" });
    const c3 = card("3", { created_at: "2026-11-08T02:00:00Z" });
    const sorted = sortCards([c1, c2, c3], "todo");
    expect(sorted.map((c) => c.id)).toEqual(["2", "3", "1"]);
  });

  it("sorts other columns by updated_at descending then id descending", () => {
    const c1 = card("1", { updated_at: "2026-11-08T01:00:00Z" });
    const c2 = card("2", { updated_at: "2026-11-08T03:00:00Z" });
    const c3 = card("3", { updated_at: "2026-11-08T02:00:00Z" });
    const c4 = card("4", { updated_at: "2026-11-08T02:00:00Z" }); // same updated_at as c3, id 4 > 3
    const sorted = sortCards([c1, c2, c3, c4], "in_progress");
    expect(sorted.map((c) => c.id)).toEqual(["2", "4", "3", "1"]);
  });

  it("returns 8-character short ID", () => {
    expect(shortCardId("abcdef1234567890")).toBe("abcdef12");
  });

  it("formats relative update time using Intl.RelativeTimeFormat", () => {
    const now = new Date("2026-11-08T12:00:00Z").getTime();
    expect(formatRelativeTime("2026-11-08T11:55:00Z", now)).toBe("5 minutes ago");
    expect(formatRelativeTime("2026-11-08T10:00:00Z", now)).toBe("2 hours ago");
    expect(formatRelativeTime("2026-11-07T12:00:00Z", now)).toBe("1 day ago");
  });

  describe("diffCardMoves", () => {
    it("returns moves between two snapshots", () => {
      const c1 = card("1", { title: "Fix bug", state: "todo" });
      const c2 = card("2", { title: "Write tests", state: "in_progress" });
      const c3 = card("3", { title: "Docs", state: "todo" });

      const c1Moved = { ...c1, state: "in_progress" as const };
      const c2Moved = { ...c2, state: "done" as const };
      const c4New = card("4", { title: "New task", state: "todo" });

      // c1 moved todo -> in_progress, c2 moved in_progress -> done, c3 unchanged, c4 added
      const moves = diffCardMoves([c1, c2, c3], [c1Moved, c2Moved, c3, c4New]);
      expect(moves).toHaveLength(2);
      expect(moves[0]).toEqual({
        card: c1Moved,
        fromState: "todo",
        toState: "in_progress",
      });
      expect(moves[1]).toEqual({
        card: c2Moved,
        fromState: "in_progress",
        toState: "done",
      });
    });

    it("returns empty array when no card states changed", () => {
      const c1 = card("1", { state: "todo" });
      const moves = diffCardMoves([c1], [{ ...c1, title: "Updated title" }]);
      expect(moves).toEqual([]);
    });
  });

  describe("formatMoveAnnouncement", () => {
    it("formats one move announcement with title in single quotes and target column label", () => {
      const c1 = card("1", { title: "Refactor engine", state: "in_review" });
      const announcement = formatMoveAnnouncement([{ card: c1, fromState: "in_progress", toState: "in_review" }]);
      expect(announcement).toBe("'Refactor engine' moved to IN REVIEW");
    });

    it("formats several moves announcement with count", () => {
      const c1 = card("1", { title: "Task 1", state: "in_progress" });
      const c2 = card("2", { title: "Task 2", state: "done" });
      const announcement = formatMoveAnnouncement([
        { card: c1, fromState: "todo", toState: "in_progress" },
        { card: c2, fromState: "in_progress", toState: "done" },
      ]);
      expect(announcement).toBe("2 cards moved");
    });

    it("returns empty string when there are no moves", () => {
      expect(formatMoveAnnouncement([])).toBe("");
    });
  });
});
