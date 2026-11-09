import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it } from "vitest";
import type { DashboardTab } from "../router";
import { JobDetail } from "./JobDetail";

function Harness({ initial = "transcript", ...props }: { initial?: DashboardTab } & Omit<React.ComponentProps<typeof JobDetail>, "tab" | "onTabChange">) {
  const [tab, setTab] = useState<DashboardTab>(initial);
  return <JobDetail {...props} tab={tab} onTabChange={setTab} />;
}
it("shows loading and 404 deep-link messages", () => {
  const { rerender } = render(<Harness detail={null} events={[]} actions={null} loading />);
  expect(screen.getByText("Loading job…")).toBeInTheDocument();
  rerender(<Harness detail={null} events={[]} actions={null} error={{ status: 404, message: "missing" }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Job not found");
});
it("surfaces output loading and unavailable state", () => {
  render(
    <Harness
      detail={{ id: "j1", state: "succeeded", prompt: "Prompt", result: { text: "Answer" } } as never}
      events={[]}
      actions={null}
      outputLoading
      outputStatus={{ events: [], next: 0, has_more: false, available: false, state: "succeeded", terminal: true }}
    />,
  );
  expect(screen.getByText("Loading output…")).toBeInTheDocument();
  expect(screen.getByText("Output unavailable")).toBeInTheDocument();
});
it("shows job metadata and transcript output", () => {
  render(
    <Harness
      detail={{ id: "j1", state: "succeeded", prompt: "Prompt", result: { text: "Answer" } } as never}
      events={[{ id: "assistant-0", attempt: 1, kind: "assistant", text: "event text" }]}
      actions={<div>Actions</div>}
    />,
  );
  expect(screen.getByText("Job j1")).toBeInTheDocument();
  expect(screen.getByText("event text")).toBeInTheDocument();
});
it("renders prompt, result, and metadata tabs with the detail fields", () => {
  const detail = {
    id: "j1",
    state: "succeeded",
    workflow: "wf",
    target: "pi",
    prompt: "The prompt",
    result: { text: "The answer", model: "m1", error: null },
    started_at: "2026-01-01T00:00:00Z",
    finished_at: null,
  } as never;
  render(<Harness detail={detail} events={[]} actions={null} />);
  expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Transcript", "Prompt", "Result", "Metadata"]);
  expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
  fireEvent.click(screen.getByRole("tab", { name: "Prompt" }));
  expect(screen.getByRole("tabpanel", { name: "Prompt" })).toHaveTextContent("The prompt");
  fireEvent.click(screen.getByRole("tab", { name: "Result" }));
  expect(screen.getByRole("tabpanel", { name: "Result" })).toHaveTextContent("The answer");
  fireEvent.click(screen.getByRole("tab", { name: "Metadata" }));
  const panel = screen.getByRole("tabpanel", { name: "Metadata" });
  expect(panel).toHaveTextContent("Started");
  expect(panel).toHaveTextContent("2026-01-01T00:00:00Z");
  expect(panel).toHaveTextContent("m1");
});
it("opens on the requested tab and keeps the transcript mounted while hidden", () => {
  const detail = { id: "j1", state: "succeeded", prompt: "P", result: { text: "R" } } as never;
  render(<Harness initial="result" detail={detail} events={[{ id: "assistant-0", attempt: 1, kind: "assistant", text: "kept row" }]} actions={null} />);
  expect(screen.getByRole("tab", { name: "Result" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("kept row")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Output transcript" })).not.toBeInTheDocument();
});
it("keeps the loaded detail and actions mounted with a warning when a later refresh fails", () => {
  const detail = { id: "j1", state: "running", prompt: "Prompt", result: { text: "Answer" } } as never;
  render(<Harness detail={detail} events={[]} actions={<button type="button">Keep me</button>} error={{ status: 500, message: "server down" }} />);
  expect(screen.getByText("Job j1")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Keep me" })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("server down");
  expect(screen.getByRole("status")).toHaveClass("callout-warning");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("replaces the detail with an error only when nothing has loaded", () => {
  render(<Harness detail={null} events={[]} actions={null} error={{ status: 500, message: "server down" }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("server down");
});
it("keeps expanded transcript rows after switching tabs and back", () => {
  const events = Array.from({ length: 120 }, (_, index) => ({ id: `assistant-${index}`, attempt: 1, kind: "assistant" as const, text: `row ${index}` }));
  render(<Harness detail={{ id: "j1", state: "succeeded", prompt: "Prompt", result: { text: "Answer" } } as never} events={events} actions={null} />);
  expect(screen.queryByText("row 0")).not.toBeInTheDocument();
  expect(screen.getByText("row 70")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Show earlier events" }));
  expect(screen.getByText("row 20")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", { name: "Prompt" }));
  expect(screen.getByRole("tabpanel", { name: "Prompt" })).toHaveTextContent("Prompt");
  fireEvent.click(screen.getByRole("tab", { name: "Transcript" }));
  expect(screen.getByText("row 20")).toBeInTheDocument();
  expect(screen.getByText("row 70")).toBeInTheDocument();
  expect(screen.queryByText("row 0")).not.toBeInTheDocument();
});
