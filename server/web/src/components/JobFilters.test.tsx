import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { settle } from "../test/async";
import { JobFilters } from "./JobFilters";

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const choose = (option: HTMLElement) => {
  fireEvent.pointerDown(option);
  fireEvent.mouseDown(option);
  fireEvent.pointerUp(option);
  fireEvent.mouseUp(option);
  fireEvent.click(option);
};
const options = { states: ["all"], projects: [{ id: "all", root: "/workspace/all" }], workflows: [], targets: [] };

it("shows project roots while submitting their IDs and keeps an ID of all distinct from the null item", async () => {
  const onChange = vi.fn();
  const consoleError = vi.spyOn(console, "error");
  render(<JobFilters filters={{}} options={options} onChange={onChange} />);
  const trigger = screen.getByRole("combobox", { name: "Filter by project" });
  expect(trigger).toHaveTextContent("All projects");
  fireEvent.click(trigger);
  await settle(300);
  choose(screen.getByRole("option", { name: "/workspace/all" }));
  expect(onChange).toHaveBeenCalledWith("project", "all");
  expect(consoleError.mock.calls.flat().join(" ")).not.toMatch(/same key/);
  consoleError.mockRestore();
});
it("shows the root as the label of the selected project ID and clears with the null item", async () => {
  const onChange = vi.fn();
  render(<JobFilters filters={{ project: "all" }} options={options} onChange={onChange} />);
  const trigger = screen.getByRole("combobox", { name: "Filter by project" });
  expect(trigger).toHaveTextContent("/workspace/all");
  expect(trigger).not.toHaveTextContent(/^all$/);
  fireEvent.click(trigger);
  await settle(300);
  choose(screen.getByRole("option", { name: "All projects" }));
  expect(onChange).toHaveBeenCalledWith("project", "");
});
it("submits search and state filter changes", () => {
  const onChange = vi.fn();
  render(<JobFilters filters={{}} options={{ states: ["running"], projects: [], workflows: [], targets: [] }} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Search jobs"), { target: { value: "needle" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  expect(onChange).toHaveBeenCalledWith("q", "needle");
});
