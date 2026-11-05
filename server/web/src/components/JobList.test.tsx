import { render, screen, fireEvent } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { JobList } from "./JobList";
it("shows loading and fetch errors without claiming the list is empty", () => {
  const { rerender } = render(<JobList jobs={[]} selectedId={null} onSelect={vi.fn()} loading />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading jobs");
  expect(screen.queryByText("No jobs found.")).not.toBeInTheDocument();
  rerender(<JobList jobs={[]} selectedId={null} onSelect={vi.fn()} error="offline" />);
  expect(screen.getByRole("alert")).toHaveTextContent("offline");
  expect(screen.queryByText("No jobs found.")).not.toBeInTheDocument();
});
it("selects jobs from an accessible list", () => {
  const onSelect = vi.fn();
  render(<JobList jobs={[{ id: "j1", state: "running" } as never]} selectedId="" onSelect={onSelect} />);
  fireEvent.click(screen.getByRole("button", { name: /j1.*running/i }));
  expect(onSelect).toHaveBeenCalledWith("j1");
});
