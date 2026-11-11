import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { JobSummary } from "../api";
import { JobList } from "./JobList";

const makeJob = (overrides: Partial<JobSummary>): JobSummary => ({
  id: "job-1234567890",
  state: "running",
  project_id: "p1",
  project_root: "/path/to/project-alpha",
  workflow: "consult",
  profile: "default",
  target: "local",
  session: "ses-1",
  retry_of: null,
  failure_kind: null,
  created_at: "2026-11-08T11:00:00Z",
  updated_at: "2026-11-08T11:55:00Z",
  ...overrides,
});

it("shows loading and fetch errors without claiming the list is empty", () => {
  const { rerender } = render(<JobList jobs={[]} selectedId={null} onSelect={vi.fn()} loading />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading jobs");
  expect(screen.queryByText("No jobs found.")).not.toBeInTheDocument();
  rerender(<JobList jobs={[]} selectedId={null} onSelect={vi.fn()} error="offline" />);
  expect(screen.getByRole("alert")).toHaveTextContent("offline");
  expect(screen.queryByText("No jobs found.")).not.toBeInTheDocument();
});

it("renders project groups with details open, summary name, path, and count", () => {
  const jobs: JobSummary[] = [
    makeJob({ id: "job-1111111111", project_root: "/path/to/alpha", workflow: "consult", session: "s1" }),
    makeJob({ id: "job-2222222222", project_root: "/path/to/beta", workflow: "review", session: "s2" }),
    makeJob({ id: "job-3333333333", project_root: "/path/to/alpha", workflow: "plan", session: "s3" }),
    makeJob({ id: "job-4444444444", project_root: null, workflow: "code", session: "s4" }),
  ];

  const { container } = render(<JobList jobs={jobs} selectedId="job-1111111111" onSelect={vi.fn()} />);

  const details = container.querySelectorAll("details");
  expect(details).toHaveLength(3);
  for (const el of details) {
    expect(el).toHaveAttribute("open");
    expect(el).toHaveClass("group");
  }

  const summaries = container.querySelectorAll("summary");
  expect(summaries).toHaveLength(3);
  expect(summaries[0]).toHaveTextContent("alpha");
  expect(summaries[0]).toHaveTextContent("/path/to/alpha");
  expect(summaries[0]).toHaveTextContent(/2 jobs$/);
  expect(summaries[0].querySelector("span[title]")).toHaveAttribute("title", "/path/to/alpha");

  expect(summaries[1]).toHaveTextContent("beta");
  expect(summaries[1]).toHaveTextContent("/path/to/beta");
  expect(summaries[1]).toHaveTextContent(/1 job$/);
  expect(summaries[1].querySelector("span[title]")).toHaveAttribute("title", "/path/to/beta");

  expect(summaries[2]).toHaveTextContent("No project");
  expect(summaries[2]).toHaveTextContent(/1 job$/);

  // Rows sit inside the right groups
  const group0Buttons = within(details[0]).getAllByRole("button");
  expect(group0Buttons).toHaveLength(2);
  expect(group0Buttons[0]).toHaveTextContent("consult · s1");
  expect(group0Buttons[0]).toHaveAttribute("aria-current", "page");
  expect(group0Buttons[1]).toHaveTextContent("plan · s3");
  expect(group0Buttons[1]).not.toHaveAttribute("aria-current");

  const group1Buttons = within(details[1]).getAllByRole("button");
  expect(group1Buttons).toHaveLength(1);
  expect(group1Buttons[0]).toHaveTextContent("review · s2");
  expect(group1Buttons[0]).not.toHaveAttribute("aria-current");

  const group2Buttons = within(details[2]).getAllByRole("button");
  expect(group2Buttons).toHaveLength(1);
  expect(group2Buttons[0]).toHaveTextContent("code · s4");
  expect(group2Buttons[0]).not.toHaveAttribute("aria-current");
});

it("renders job rows with title and meta, omitting full job ID and exposing state", () => {
  const onSelect = vi.fn();
  const job = makeJob({
    id: "abcdef1234567890",
    workflow: "consult",
    session: "ses-42",
    target: "backend-1",
    state: "running",
  });

  const { container } = render(<JobList jobs={[job]} selectedId={job.id} onSelect={onSelect} />);

  const button = screen.getByRole("button", { name: /^consult · ses-42.*running/i });
  expect(button).toBeInTheDocument();
  expect(button).toHaveAttribute("aria-current", "page");
  expect(button).toHaveTextContent("consult · ses-42");
  expect(button).toHaveTextContent("backend-1");
  expect(button).toHaveTextContent("abcdef12");
  expect(button).toHaveTextContent("abcdef12 · running");
  expect(button).toHaveAccessibleName(/running/);

  // Must not display the full UUID / job id
  expect(container).not.toHaveTextContent("abcdef1234567890");

  fireEvent.click(button);
  expect(onSelect).toHaveBeenCalledWith("abcdef1234567890");
});

it("renders workflow only when session is null", () => {
  const job = makeJob({
    id: "j-null-session",
    workflow: "consult",
    session: null,
    state: "succeeded",
  });
  render(<JobList jobs={[job]} selectedId={null} onSelect={vi.fn()} />);
  const button = screen.getByRole("button", { name: /^consult.*succeeded/ });
  expect(button).toBeInTheDocument();
  expect(button).toHaveTextContent("consult");
  expect(button).not.toHaveTextContent("consult ·");
  expect(button).not.toHaveAttribute("aria-current");
});
