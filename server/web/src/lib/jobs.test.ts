import { describe, expect, it, vi } from "vitest";
import { groupByProject, jobLabel } from "./jobs";

describe("jobs logic", () => {
  describe("jobLabel", () => {
    const fixedNow = new Date("2026-11-08T12:00:00Z").getTime();

    it("formats full job label with workflow, session, target, relative time, and short id", () => {
      const label = jobLabel(
        {
          id: "1234567890abcdef",
          workflow: "consult",
          session: "s1",
          target: "local",
          updated_at: "2026-11-08T11:55:00Z",
          created_at: "2026-11-08T11:00:00Z",
        },
        fixedNow,
      );
      expect(label.title).toBe("consult · s1");
      expect(label.meta).toBe("local · 5 minutes ago · 12345678");
    });

    it("omits session when session is null or empty", () => {
      const withNullSession = jobLabel({
        id: "12345678",
        workflow: "plan",
        session: null,
        target: "local",
      });
      expect(withNullSession.title).toBe("plan");

      const withEmptySession = jobLabel({
        id: "12345678",
        workflow: "plan",
        session: "",
        target: "local",
      });
      expect(withEmptySession.title).toBe("plan");
    });

    it("falls back to 'job' when workflow is null or empty", () => {
      const nullWfWithSession = jobLabel({
        id: "12345678",
        workflow: null,
        session: "s1",
        target: null,
      });
      expect(nullWfWithSession.title).toBe("job · s1");

      const nullWfNoSession = jobLabel({
        id: "12345678",
        workflow: null,
        session: null,
        target: null,
      });
      expect(nullWfNoSession.title).toBe("job");

      const emptyWfNoSession = jobLabel({
        id: "12345678",
        workflow: "",
        session: "",
        target: null,
      });
      expect(emptyWfNoSession.title).toBe("job");
    });

    it("skips missing parts in meta", () => {
      const onlyId = jobLabel({
        id: "1234567890",
        workflow: "run",
        target: null,
      });
      expect(onlyId.meta).toBe("12345678");

      const onlyTime = jobLabel(
        {
          id: "",
          workflow: "run",
          target: null,
          updated_at: "2026-11-08T11:55:00Z",
        },
        fixedNow,
      );
      expect(onlyTime.meta).toBe("5 minutes ago");

      const allMissing = jobLabel({
        id: "",
        workflow: null,
        target: null,
      });
      expect(allMissing.meta).toBe("");
    });

    it("formats relative time using system timers when now is not provided", () => {
      vi.useFakeTimers();
      try {
        vi.setSystemTime(new Date("2026-11-08T12:00:00Z"));
        const label = jobLabel({
          id: "12345678",
          workflow: "consult",
          target: null,
          updated_at: "2026-11-08T11:55:00Z",
        });
        expect(label.meta).toBe("5 minutes ago · 12345678");
      } finally {
        vi.useRealTimers();
      }
    });

    it("skips relative time part when updated_at is an invalid date string", () => {
      const label = jobLabel({
        id: "12345678",
        workflow: "consult",
        target: "local",
        updated_at: "invalid-date",
      });
      expect(label.meta).toBe("local · 12345678");
    });
  });

  describe("groupByProject", () => {
    it("groups items in first appearance order", () => {
      const items = [
        { id: "1", root: "/proj/alpha" },
        { id: "2", root: "/proj/beta" },
        { id: "3", root: "/proj/alpha" },
      ];
      const groups = groupByProject(items, (item) => item.root);
      expect(groups).toEqual([
        {
          root: "/proj/alpha",
          name: "alpha",
          items: [items[0], items[2]],
        },
        {
          root: "/proj/beta",
          name: "beta",
          items: [items[1]],
        },
      ]);
    });

    it("groups null, undefined, or empty roots under root '' and name 'No project'", () => {
      const items = [
        { id: "1", root: null },
        { id: "2", root: "/work/project" },
        { id: "3", root: "" },
        { id: "4", root: undefined },
      ];
      const groups = groupByProject(items, (item) => item.root);
      expect(groups).toEqual([
        {
          root: "",
          name: "No project",
          items: [items[0], items[2], items[3]],
        },
        {
          root: "/work/project",
          name: "project",
          items: [items[1]],
        },
      ]);
    });

    it("returns empty array when items list is empty", () => {
      expect(groupByProject([], (item: { root: string }) => item.root)).toEqual([]);
    });

    it("extracts project name from Windows backslash paths", () => {
      const items = [{ id: "1", root: "C:\\work\\repo" }];
      const groups = groupByProject(items, (item) => item.root);
      expect(groups).toEqual([
        {
          root: "C:\\work\\repo",
          name: "repo",
          items: [items[0]],
        },
      ]);
    });
  });
});
