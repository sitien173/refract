import { expect, it } from "vitest";
import { jobPath, readRoute } from "./router";
it("restores deep-linked job and filters under the Vite dashboard base", () => {
  const route = readRoute(new URL("http://localhost/dashboard/jobs/job%2F1?state=running&q=abc&target=pi"));
  expect(route).toEqual({ view: "console", jobId: "job/1", filters: { state: "running", target: "pi", q: "abc" } });
  expect(jobPath("job/1")).toBe("/dashboard/jobs/job%2F1");
});
it("does not interpret the job ID targets as the targets screen", () => {
  expect(readRoute(new URL("http://localhost/dashboard/jobs/targets")).view).toBe("console");
  expect(readRoute(new URL("http://localhost/dashboard/targets")).view).toBe("targets");
});
