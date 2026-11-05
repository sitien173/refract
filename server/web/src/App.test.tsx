import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { DashboardApiError, type JobPage } from "./api";
import { deferred, settle } from "./test/async";
import { warmUpComponents } from "./test/warmup";

const api = vi.hoisted(() => ({
  getJobs: vi.fn(),
  getJob: vi.fn(),
  getJobOutput: vi.fn(),
  getTargets: vi.fn(),
  postJobAction: vi.fn(),
}));
vi.mock("./api", async (importOriginal) => ({ ...(await importOriginal<typeof import("./api")>()), ...api }));

const options = { states: [], projects: [], workflows: [], targets: [] };
const jobsPage = (ids: string[], next_cursor: string | null = null) =>
  ({ jobs: ids.map((id) => ({ id, state: "queued" })), next_cursor, options }) as unknown as JobPage;
const detailOf = (id: string, state = "failed", pending_question: unknown = null) => ({
  id,
  state,
  prompt: "p",
  result: { text: "r" },
  pending_question,
});
const announcements = () => screen.getByRole("status", { name: "Announcements" });

beforeAll(warmUpComponents);

beforeEach(() => {
  vi.useFakeTimers();
  history.replaceState({}, "", "/dashboard/jobs/old?state=running&q=needle");
  api.getJobs.mockResolvedValue(jobsPage([]));
  api.getJob.mockImplementation((id: string) => Promise.resolve(detailOf(id)));
  api.getJobOutput.mockResolvedValue({ events: [], next: 0, has_more: false, available: true, state: "failed", terminal: true });
  api.postJobAction.mockResolvedValue({ job_id: "new-job", state: "queued" });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

it("loads the next cursor page after a nonempty first page and keeps both", async () => {
  api.getJobs.mockImplementation((filters: Record<string, string>) =>
    Promise.resolve(filters.cursor ? jobsPage(["later"]) : jobsPage(["first"], "cursor-1")),
  );
  history.replaceState({}, "", "/dashboard/");
  render(<App />);
  await settle();
  expect(screen.getByRole("button", { name: /first.*queued/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Load more jobs" }));
  await settle();
  expect(screen.getByRole("button", { name: /first.*queued/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /later.*queued/ })).toBeInTheDocument();
  expect(api.getJobs).toHaveBeenCalledWith({ cursor: "cursor-1" });
  expect(screen.queryByRole("button", { name: "Load more jobs" })).not.toBeInTheDocument();
});

it("discards a late load-more response after the filter changes", async () => {
  const late = deferred<JobPage>();
  api.getJobs.mockImplementation((filters: Record<string, string>) => {
    if (filters.cursor) return late.promise;
    return Promise.resolve(filters.q === "fresh" ? jobsPage(["fresh-job"]) : jobsPage(["first"], "cursor-1"));
  });
  history.replaceState({}, "", "/dashboard/");
  render(<App />);
  await settle();
  fireEvent.click(screen.getByRole("button", { name: "Load more jobs" }));
  fireEvent.change(screen.getByLabelText("Search jobs"), { target: { value: "fresh" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await settle();
  expect(screen.getByRole("button", { name: /fresh-job.*queued/ })).toBeInTheDocument();
  await act(async () => late.resolve(jobsPage(["stale-job"], "stale-cursor")));
  await settle();
  expect(screen.queryByRole("button", { name: /stale-job/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Load more jobs" })).not.toBeInTheDocument();
  expect(location.search).toBe("?q=fresh");
});

it("navigates to targets in-app and reports fetch failures", async () => {
  api.getTargets.mockRejectedValue(Error("targets offline"));
  history.replaceState({}, "", "/dashboard/");
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Targets" }));
  await settle();
  expect(screen.getByRole("alert")).toHaveTextContent("targets offline");
  expect(screen.queryByText("No targets configured.")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Back to console" }));
  expect(location.pathname).toBe("/dashboard/");
});

it("keeps a failed answer draft and refetches a stale pending question", async () => {
  const pending = { question_id: "q1", text: "Proceed?" };
  api.getJob.mockImplementation((id: string) => Promise.resolve(detailOf(id, "running", pending)));
  api.postJobAction.mockRejectedValue(new DashboardApiError("Question expired", 409, "invalid_state"));
  history.replaceState({}, "", "/dashboard/jobs/old");
  render(<App />);
  await settle();
  fireEvent.click(screen.getByRole("button", { name: "Answer question" }));
  fireEvent.change(screen.getByLabelText("Your answer"), { target: { value: "Keep this" } });
  const callsBefore = api.getJob.mock.calls.length;
  fireEvent.click(screen.getByRole("button", { name: "Send answer" }));
  await settle();
  expect(screen.getByRole("alert")).toHaveTextContent("Question expired");
  expect(screen.getByLabelText("Your answer")).toHaveValue("Keep this");
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(api.getJob.mock.calls.length).toBeGreaterThan(callsBefore);
});

it("restores deep-link filters, selects the retry job, and keeps the retry announcement", async () => {
  render(<App />);
  await settle();
  expect(screen.getByRole("heading", { name: "Job old" })).toBeInTheDocument();
  expect(screen.getByLabelText("Search jobs")).toHaveValue("needle");
  fireEvent.click(screen.getByRole("button", { name: "Retry job" }));
  await settle();
  expect(location.pathname).toBe("/dashboard/jobs/new-job");
  expect(location.search).toBe("?state=running&q=needle");
  expect(api.postJobAction).toHaveBeenCalledWith("old", "retry", {});
  expect(screen.getByRole("heading", { name: "Job new-job" })).toBeInTheDocument();
  expect(announcements()).toHaveTextContent("Retry started");
});

it("clears the previous announcement when the user selects another job", async () => {
  api.getJob.mockImplementation((id: string) => Promise.resolve(detailOf(id, "running")));
  api.getJobs.mockResolvedValue(jobsPage(["old", "other"]));
  render(<App />);
  await settle();
  fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm cancellation" }));
  await settle();
  expect(announcements()).toHaveTextContent("Cancellation requested");
  fireEvent.click(screen.getByRole("button", { name: /other.*queued/ }));
  await settle();
  expect(announcements()).toBeEmptyDOMElement();
});

it("stops polling the detail of a terminal job but keeps polling the list", async () => {
  render(<App />);
  await settle();
  await settle(5000);
  expect(api.getJob).toHaveBeenCalledTimes(1);
  expect(api.getJobs.mock.calls.length).toBeGreaterThanOrEqual(5);
});

it("keeps polling the detail of a running job", async () => {
  api.getJob.mockImplementation((id: string) => Promise.resolve(detailOf(id, "running")));
  render(<App />);
  await settle();
  await settle(3000);
  expect(api.getJob.mock.calls.length).toBeGreaterThanOrEqual(3);
});

it("keeps the last good detail and an open answer draft when a later refresh fails", async () => {
  const pending = { question_id: "q1", text: "Proceed?" };
  api.getJob
    .mockResolvedValueOnce(detailOf("old", "running", pending))
    .mockRejectedValue(new DashboardApiError("server down", 500, "http_error"));
  render(<App />);
  await settle();
  fireEvent.click(screen.getByRole("button", { name: "Answer question" }));
  fireEvent.change(screen.getByLabelText("Your answer"), { target: { value: "Keep this" } });
  await settle(1000);
  expect(api.getJob.mock.calls.length).toBeGreaterThanOrEqual(2);
  // The open modal dialog hides the page from the accessibility tree, so query by text.
  expect(screen.getByText("Job old")).toBeInTheDocument();
  expect(screen.getByLabelText("Your answer")).toHaveValue("Keep this");
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.getByText(/Refreshing failed: server down/)).toBeInTheDocument();
});

it("shows a replacement error when the first detail load fails", async () => {
  api.getJob.mockRejectedValue(new DashboardApiError("Job not found", 404, "unknown_job"));
  render(<App />);
  await settle();
  expect(screen.getByRole("alert")).toHaveTextContent("Job not found.");
  expect(screen.queryByRole("heading", { name: /Job old/ })).not.toBeInTheDocument();
});
