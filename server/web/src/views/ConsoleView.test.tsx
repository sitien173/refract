import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ConsoleView } from "./ConsoleView";

it("renders job navigation, a resizable split pane, and an announcements region", () => {
  render(
    <ConsoleView
      jobs={[]}
      selectedId={null}
      onSelect={() => {}}
      filters={{}}
      options={{ states: [], projects: [], workflows: [], targets: [] }}
      onFilter={() => {}}
      detail={null}
      events={[]}
      tab="transcript"
      onTabChange={() => {}}
      actions={null}
      announcement="Retry started"
    />,
  );
  expect(screen.getByRole("region", { name: "Job console" })).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Jobs" })).toBeInTheDocument();
  expect(screen.getByRole("separator", { name: "Resize job list and detail" })).toBeInTheDocument();
  expect(screen.getByRole("status", { name: "Announcements" })).toHaveTextContent("Retry started");
});
