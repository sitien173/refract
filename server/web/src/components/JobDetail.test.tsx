import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { JobDetail } from "./JobDetail";
it("shows loading and 404 deep-link messages", () => {
  const { rerender } = render(<JobDetail detail={null} events={[]} actions={null} loading />);
  expect(screen.getByText("Loading job…")).toBeInTheDocument();
  rerender(<JobDetail detail={null} events={[]} actions={null} error={{ status: 404, message: "missing" }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Job not found");
});
it("surfaces output loading and unavailable state", () => {
  render(
    <JobDetail
      detail={{ id: "j1", state: "succeeded", prompt: "Prompt", result: { text: "Answer" } } as never}
      events={[]}
      actions={null}
      outputLoading
      outputStatus={{ events: [], next: 0, has_more: false, available: false, state: "succeeded", terminal: true }}
    />,
  );
  expect(screen.getByText("Loading output…")).toBeInTheDocument();
  expect(screen.getByText("Output is not available.")).toBeInTheDocument();
});
it("shows job metadata and transcript output", () => {
  render(
    <JobDetail
      detail={{ id: "j1", state: "succeeded", prompt: "Prompt", result: { text: "Answer" } } as never}
      events={[{ kind: "assistant.text.delta", data: { text: "event text" } }]}
      actions={<div>Actions</div>}
    />,
  );
  expect(screen.getByText("Job j1")).toBeInTheDocument();
  expect(screen.getByText("Answer")).toBeInTheDocument();
});
it("keeps the loaded detail and actions mounted with a warning when a later refresh fails", () => {
  const detail = { id: "j1", state: "running", prompt: "Prompt", result: { text: "Answer" } } as never;
  render(
    <JobDetail
      detail={detail}
      events={[]}
      actions={<button>Keep me</button>}
      error={{ status: 500, message: "server down" }}
    />,
  );
  expect(screen.getByText("Job j1")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Keep me" })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("server down");
  expect(screen.getByRole("status")).toHaveClass("tds-announcement--warning");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
it("replaces the detail with an error only when nothing has loaded", () => {
  render(<JobDetail detail={null} events={[]} actions={null} error={{ status: 500, message: "server down" }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("server down");
});
