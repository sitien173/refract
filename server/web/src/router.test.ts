import { expect, it } from "vitest";
import { jobPath, readRoute, tabUrl } from "./router";

it("restores deep-linked job and filters under the Vite dashboard base", () => {
  const route = readRoute(new URL("http://localhost/dashboard/jobs/job%2F1?state=running&q=abc&target=pi"));
  expect(route).toEqual({ view: "console", jobId: "job/1", cardId: null, filters: { state: "running", target: "pi", q: "abc" }, tab: "transcript" });
  expect(jobPath("job/1")).toBe("/dashboard/jobs/job%2F1");
});
it("does not interpret the job ID targets as the targets screen", () => {
  expect(readRoute(new URL("http://localhost/dashboard/jobs/targets")).view).toBe("console");
  expect(readRoute(new URL("http://localhost/dashboard/targets")).view).toBe("targets");
});
it("reads the insights route with and without a trailing slash", () => {
  expect(readRoute(new URL("http://localhost/dashboard/insights")).view).toBe("insights");
  expect(readRoute(new URL("http://localhost/dashboard/insights/")).view).toBe("insights");
  expect(readRoute(new URL("http://localhost/dashboard/jobs/insights")).view).toBe("console");
});
it("reads board route and card query parameter", () => {
  expect(readRoute(new URL("http://localhost/dashboard/board")).view).toBe("board");
  expect(readRoute(new URL("http://localhost/dashboard/board/")).view).toBe("board");
  expect(readRoute(new URL("http://localhost/dashboard/board?card=card-1")).cardId).toBe("card-1");
  expect(readRoute(new URL("http://localhost/dashboard/board")).cardId).toBeNull();
  expect(readRoute(new URL("http://localhost/dashboard/")).cardId).toBeNull();
  expect(readRoute(new URL("http://localhost/dashboard/targets")).cardId).toBeNull();
});
it("reads a valid tab and falls back to transcript for an invalid one", () => {
  expect(readRoute(new URL("http://localhost/dashboard/jobs/j1?tab=result")).tab).toBe("result");
  expect(readRoute(new URL("http://localhost/dashboard/jobs/j1?tab=bogus")).tab).toBe("transcript");
  expect(readRoute(new URL("http://localhost/dashboard/jobs/j1")).tab).toBe("transcript");
});
it("builds a tab URL that keeps filters and drops the default tab", () => {
  const url = new URL("http://localhost/dashboard/jobs/j1?state=running");
  expect(tabUrl(url, "prompt").search).toBe("?state=running&tab=prompt");
  expect(tabUrl(url, "transcript").search).toBe("?state=running");
});
