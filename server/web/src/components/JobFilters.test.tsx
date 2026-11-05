import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { settle } from "../test/async";
import { warmUpComponents } from "../test/warmup";
import { JobFilters } from "./JobFilters";

beforeAll(warmUpComponents);
beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("shows project roots while submitting their IDs and avoids the all sentinel collision", async () => {
  const onChange = vi.fn();
  render(
    <JobFilters
      filters={{}}
      options={{ states: ["all"], projects: [{ id: "all", root: "/workspace/all" }], workflows: [], targets: [] }}
      onChange={onChange}
    />,
  );
  fireEvent.click(screen.getByRole("combobox", { name: "Filter by project" }));
  await settle();
  fireEvent.click(screen.getByRole("option", { name: "/workspace/all" }));
  expect(onChange).toHaveBeenCalledWith("project", "all");
});
it("submits search and state filter changes", () => {
  const onChange = vi.fn();
  render(
    <JobFilters
      filters={{}}
      options={{ states: ["running"], projects: [], workflows: [], targets: [] }}
      onChange={onChange}
    />,
  );
  fireEvent.change(screen.getByLabelText("Search jobs"), { target: { value: "needle" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  expect(onChange).toHaveBeenCalledWith("q", "needle");
});
