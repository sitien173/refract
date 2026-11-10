import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { DashboardApiError, type JobPage } from "./api";
import { deferred, settle } from "./test/async";
import { mockMotion } from "./test/motion";
import { createQueryWrapper, createTestQueryClient } from "./test/query";

const api = vi.hoisted(() => ({
  getJobs: vi.fn(),
  getJob: vi.fn(),
  getJobOutput: vi.fn(),
  getTargets: vi.fn(),
  getCards: vi.fn(),
  getCard: vi.fn(),
  getStats: vi.fn(),
  postJobAction: vi.fn(),
}));
vi.mock("./api", async (importOriginal) => ({ ...(await importOriginal<typeof import("./api")>()), ...api }));

const options = { states: [], projects: [], workflows: [], targets: [] };
const jobsPage = (ids: string[], next_cursor: string | null = null) => ({ jobs: ids.map((id) => ({ id, state: "queued" })), next_cursor, options }) as unknown as JobPage;
const detailOf = (id: string, state = "failed", pending_question: unknown = null) => ({
  id,
  state,
  prompt: "p",
  result: { text: "r" },
  pending_question,
});
const emptyStats = {
  days: 7,
  currency: "USD",
  work_delegated: { by_workflow: {}, by_state: {}, worker_hours: 0, success_rate: 0, daily: {} },
  failover_saves: { skipped_targets: 0, retries: 0, retries_after_failure: 0, unknown_skipped_targets: 0, unknown_attempts: 0 },
  tokens: { by_backend: {}, by_model: {}, by_target: {} },
  estimated_cost: { total: 0, by_model: {}, unpriced_models: [] },
};
const announcements = () => screen.getByRole("status", { name: "Announcements" });

let queryClient = createTestQueryClient();
const renderApp = () => render(<App />, { wrapper: createQueryWrapper(queryClient) });

beforeEach(() => {
  vi.useFakeTimers();
  queryClient = createTestQueryClient();
  history.replaceState({}, "", "/dashboard/jobs/old?state=running&q=needle");
  api.getJobs.mockResolvedValue(jobsPage([]));
  api.getJob.mockImplementation((id: string) => Promise.resolve(detailOf(id)));
  api.getJobOutput.mockResolvedValue({ events: [], next: 0, has_more: false, available: true, state: "failed", terminal: true });
  api.getCards.mockResolvedValue({ cards: [], truncated: false, options: { projects: [] } });
  api.getCard.mockResolvedValue({ card: {}, moves: [], jobs: [] });
  api.getStats.mockResolvedValue(emptyStats);
  api.postJobAction.mockResolvedValue({ job_id: "new-job", state: "queued" });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(document, "startViewTransition");
  vi.useRealTimers();
  vi.clearAllMocks();
});

it("loads the next cursor page after a nonempty first page and keeps both", async () => {
  api.getJobs.mockImplementation((filters: Record<string, string>) => Promise.resolve(filters.cursor ? jobsPage(["later"]) : jobsPage(["first"], "cursor-1")));
  history.replaceState({}, "", "/dashboard/");
  renderApp();
  await settle();
  expect(screen.getByRole("button", { name: /first.*queued/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Load more jobs" }));
  await settle();
  expect(screen.getByRole("button", { name: /first.*queued/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /later.*queued/ })).toBeInTheDocument();
  expect(api.getJobs).toHaveBeenCalledWith({ cursor: "cursor-1" }, expect.any(AbortSignal));
  expect(screen.queryByRole("button", { name: "Load more jobs" })).not.toBeInTheDocument();
});

it("discards a late load-more response after the filter changes", async () => {
  const late = deferred<JobPage>();
  api.getJobs.mockImplementation((filters: Record<string, string>) => {
    if (filters.cursor) return late.promise;
    return Promise.resolve(filters.q === "fresh" ? jobsPage(["fresh-job"]) : jobsPage(["first"], "cursor-1"));
  });
  history.replaceState({}, "", "/dashboard/");
  renderApp();
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
  renderApp();
  fireEvent.click(screen.getByRole("link", { name: "Targets" }));
  await settle();
  expect(screen.getByRole("alert")).toHaveTextContent("targets offline");
  expect(screen.queryByText("No targets configured.")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Back to console" }));
  expect(location.pathname).toBe("/dashboard/");
});

it("shows navigation links in the header with aria-current on the active view", async () => {
  history.replaceState({}, "", "/dashboard/");
  renderApp();
  await settle();
  expect(screen.getByRole("link", { name: "Console" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Board" })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("link", { name: "Targets" })).not.toHaveAttribute("aria-current");

  cleanup();
  history.replaceState({}, "", "/dashboard/jobs/old");
  renderApp();
  await settle();
  expect(screen.getByRole("link", { name: "Console" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Board" })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("link", { name: "Targets" })).not.toHaveAttribute("aria-current");

  cleanup();
  api.getTargets.mockResolvedValue({ targets: [], config: null });
  history.replaceState({}, "", "/dashboard/targets");
  renderApp();
  await settle();
  expect(screen.getByRole("link", { name: "Console" })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("link", { name: "Board" })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("link", { name: "Targets" })).toHaveAttribute("aria-current", "page");

  cleanup();
  history.replaceState({}, "", "/dashboard/board");
  renderApp();
  await settle();
  expect(screen.getByRole("link", { name: "Console" })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("link", { name: "Board" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Targets" })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("link", { name: "Insights" })).not.toHaveAttribute("aria-current");

  cleanup();
  history.replaceState({}, "", "/dashboard/insights");
  renderApp();
  await settle();
  expect(screen.getByRole("link", { name: "Console" })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("link", { name: "Board" })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("link", { name: "Targets" })).not.toHaveAttribute("aria-current");
  expect(screen.getByRole("link", { name: "Insights" })).toHaveAttribute("aria-current", "page");
});

it("makes no job-list request and sends the UTC offset when visiting the insights view", async () => {
  vi.spyOn(Date.prototype, "getTimezoneOffset").mockReturnValue(-330);
  history.replaceState({}, "", "/dashboard/insights");
  renderApp();
  await settle();
  expect(api.getJobs).not.toHaveBeenCalled();
  expect(api.getStats).toHaveBeenCalledWith(7, 330, expect.anything());
});

it("navigates to insights in-app from the console nav", async () => {
  history.replaceState({}, "", "/dashboard/");
  renderApp();
  await settle();
  fireEvent.click(screen.getByRole("link", { name: "Insights" }));
  await settle();
  expect(location.pathname).toBe("/dashboard/insights");
  expect(screen.getByRole("heading", { name: "Insights" })).toBeInTheDocument();
});

it("makes no job-list request when visiting the board view", async () => {
  history.replaceState({}, "", "/dashboard/board");
  renderApp();
  await settle();
  expect(api.getJobs).not.toHaveBeenCalled();
});

it("shows correct column counts for cards returned by getCards in multiple states", async () => {
  api.getCards.mockResolvedValue({
    cards: [
      {
        id: "c1",
        project_id: "p1",
        project_root: "/repo",
        title: "Card 1",
        state: "todo",
        job_ids: [],
        created_at: "2026-11-08T01:00:00Z",
        updated_at: "2026-11-08T01:00:00Z",
      },
      {
        id: "c2",
        project_id: "p1",
        project_root: "/repo",
        title: "Card 2",
        state: "in_progress",
        job_ids: [],
        created_at: "2026-11-08T02:00:00Z",
        updated_at: "2026-11-08T02:00:00Z",
      },
      {
        id: "c3",
        project_id: "p1",
        project_root: "/repo",
        title: "Card 3",
        state: "in_progress",
        job_ids: [],
        created_at: "2026-11-08T03:00:00Z",
        updated_at: "2026-11-08T03:00:00Z",
      },
    ],
    truncated: false,
    options: { projects: [{ id: "p1", root: "/repo" }] },
  });
  history.replaceState({}, "", "/dashboard/board");
  renderApp();
  await settle();

  expect(screen.getByRole("heading", { level: 2, name: /TODO\s*1/ })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 2, name: /IN PROGRESS\s*2/ })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 2, name: /IN REVIEW\s*0/ })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 2, name: /DONE\s*0/ })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 2, name: /CANCELLED\s*0/ })).toBeInTheDocument();
});

it("keeps a failed answer draft and refetches a stale pending question", async () => {
  const pending = { question_id: "q1", text: "Proceed?" };
  api.getJob.mockImplementation((id: string) => Promise.resolve(detailOf(id, "running", pending)));
  api.postJobAction.mockRejectedValue(new DashboardApiError("Question expired", 409, "invalid_state"));
  history.replaceState({}, "", "/dashboard/jobs/old");
  renderApp();
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
  renderApp();
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
  renderApp();
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
  renderApp();
  await settle();
  await settle(5000);
  expect(api.getJob).toHaveBeenCalledTimes(1);
  expect(api.getJobs.mock.calls.length).toBeGreaterThanOrEqual(5);
});

it("keeps polling the detail of a running job", async () => {
  api.getJob.mockImplementation((id: string) => Promise.resolve(detailOf(id, "running")));
  renderApp();
  await settle();
  await settle(3000);
  expect(api.getJob.mock.calls.length).toBeGreaterThanOrEqual(3);
});

it("keeps the last good detail and an open answer draft when a later refresh fails", async () => {
  const pending = { question_id: "q1", text: "Proceed?" };
  api.getJob.mockResolvedValueOnce(detailOf("old", "running", pending)).mockRejectedValue(new DashboardApiError("server down", 500, "http_error"));
  renderApp();
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
  api.getJob.mockRejectedValue(new DashboardApiError("server down", 500, "server_error"));
  renderApp();
  await settle();
  expect(screen.getByRole("alert")).toHaveTextContent("server down");
  expect(screen.queryByRole("heading", { name: /Job old/ })).not.toBeInTheDocument();
});

it("clears the selection, keeps filters, announces not found, and stops output polling when detail 404s", async () => {
  api.getJob.mockRejectedValue(new DashboardApiError("Job not found", 404, "unknown_job"));
  history.replaceState({}, "", "/dashboard/jobs/old?state=running&q=needle");
  const pushSpy = vi.spyOn(history, "pushState");
  const replaceSpy = vi.spyOn(history, "replaceState");
  renderApp();
  await settle();

  expect(location.pathname).toBe("/dashboard/");
  expect(location.search).toBe("?state=running&q=needle");
  expect(pushSpy).not.toHaveBeenCalled();
  expect(replaceSpy).toHaveBeenCalledWith(expect.anything(), "", "/dashboard/?state=running&q=needle");
  expect(announcements()).toHaveTextContent("Job not found");
  expect(screen.getByText("Select a job to view its details.")).toBeInTheDocument();

  const outputCalls = api.getJobOutput.mock.calls.length;
  await settle(5000);
  expect(api.getJobOutput.mock.calls.length).toBe(outputCalls);
});

it("announces list warning only when error becomes non-null and does not overwrite subsequent action announcements on repeated failed polls", async () => {
  api.getJobs.mockResolvedValueOnce(jobsPage(["old"])).mockImplementation(() => Promise.reject(new DashboardApiError("list offline", 500, "error")));
  renderApp();
  await settle();

  expect(announcements()).toHaveTextContent("");

  // First failed poll at 1s
  await settle(1000);
  expect(announcements()).toHaveTextContent("list offline");

  // User action announces something
  fireEvent.click(screen.getByRole("button", { name: "Retry job" }));
  await settle();
  expect(announcements()).toHaveTextContent("Retry started");

  // Next failed poll after 5s backoff keeps the action announcement
  await settle(6000);
  expect(api.getJobs.mock.calls.length).toBeGreaterThanOrEqual(3);
  expect(announcements()).toHaveTextContent("Retry started");
});

it("opens the deep-linked tab and falls back to transcript for an invalid one", async () => {
  history.replaceState({}, "", "/dashboard/jobs/old?tab=result");
  renderApp();
  await settle();
  expect(screen.getByRole("tab", { name: "Result" })).toHaveAttribute("aria-selected", "true");
  cleanup();
  history.replaceState({}, "", "/dashboard/jobs/old?tab=nope");
  renderApp();
  await settle();
  expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
});

it("changes tabs with replaceState, keeps filters, does not refetch output, and follows popstate", async () => {
  mockMotion({ transitions: false });
  renderApp();
  await settle();
  const outputCalls = api.getJobOutput.mock.calls.length;
  const length = history.length;
  fireEvent.click(screen.getByRole("tab", { name: "Prompt" }));
  expect(location.search).toBe("?state=running&q=needle&tab=prompt");
  expect(history.length).toBe(length);
  expect(screen.getByRole("tab", { name: "Prompt" })).toHaveAttribute("aria-selected", "true");
  expect(api.getJobOutput.mock.calls.length).toBe(outputCalls);
  history.replaceState({}, "", "/dashboard/jobs/old?tab=metadata");
  act(() => window.dispatchEvent(new PopStateEvent("popstate")));
  expect(screen.getByRole("tab", { name: "Metadata" })).toHaveAttribute("aria-selected", "true");
  vi.unstubAllGlobals();
});

it("starts a view transition on job and tab changes but not on polls", async () => {
  const start = mockMotion();
  api.getJob.mockImplementation((id: string) => Promise.resolve(detailOf(id, "running")));
  api.getJobs.mockResolvedValue(jobsPage(["old", "other"]));
  renderApp();
  await settle();
  await settle(3000);
  expect(start).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("tab", { name: "Result" }));
  expect(start).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: /other.*queued/ }));
  expect(start).toHaveBeenCalledTimes(2);
  await settle(3000);
  expect(start).toHaveBeenCalledTimes(2);
  vi.unstubAllGlobals();
});

it("starts no view transition under reduced motion or without startViewTransition", async () => {
  const start = mockMotion({ reduced: true });
  renderApp();
  await settle();
  fireEvent.click(screen.getByRole("tab", { name: "Result" }));
  expect(start).not.toHaveBeenCalled();
  expect(screen.getByRole("tab", { name: "Result" })).toHaveAttribute("aria-selected", "true");
  cleanup();
  mockMotion({ transitions: false });
  history.replaceState({}, "", "/dashboard/jobs/old");
  renderApp();
  await settle();
  fireEvent.click(screen.getByRole("tab", { name: "Result" }));
  expect(screen.getByRole("tab", { name: "Result" })).toHaveAttribute("aria-selected", "true");
  vi.unstubAllGlobals();
});

it("renders card detail on /dashboard/board?card=<id>", async () => {
  api.getCards.mockResolvedValue({
    cards: [
      {
        id: "card-1",
        project_id: "p1",
        project_root: "/repo",
        title: "Test Card 1",
        state: "todo",
        job_ids: [],
        created_at: "2026-11-08T00:00:00Z",
        updated_at: "2026-11-08T00:00:00Z",
      },
    ],
    truncated: false,
    options: { projects: [] },
  });
  api.getCard.mockResolvedValue({
    card: {
      id: "card-1",
      project_id: "p1",
      project_root: "/repo",
      title: "Test Card 1",
      state: "todo",
      body: "Card body description",
      job_ids: [],
      created_at: "2026-11-08T00:00:00Z",
      updated_at: "2026-11-08T00:00:00Z",
    },
    moves: [],
    jobs: [],
  });
  history.replaceState({}, "", "/dashboard/board?card=card-1");
  renderApp();
  await settle();
  expect(screen.getByRole("complementary", { name: "Card detail" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { level: 2, name: "Test Card 1" })).toBeInTheDocument();
});

it("clears card selection and announces Card not found on 404", async () => {
  api.getCard.mockRejectedValue(new DashboardApiError("Card not found", 404, "unknown_card"));
  history.replaceState({}, "", "/dashboard/board?project=p1&card=missing-card");
  renderApp();
  await settle();
  expect(location.pathname).toBe("/dashboard/board");
  expect(location.search).toBe("?project=p1");
  expect(announcements()).toHaveTextContent("Card not found");
  expect(screen.queryByRole("complementary", { name: "Card detail" })).not.toBeInTheDocument();
});
