import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { StatsResponse } from "../api";
import { fixed, InsightsView } from "./InsightsView";

const empty: StatsResponse = {
  days: 7,
  currency: "USD",
  work_delegated: { by_workflow: {}, by_state: {}, worker_hours: 0, success_rate: 0, daily: {} },
  failover_saves: { skipped_targets: 0, retries: 0, retries_after_failure: 0, unknown_skipped_targets: 0, unknown_attempts: 0 },
  tokens: { by_backend: {}, by_model: {}, by_target: {} },
  estimated_cost: { total: 0, by_model: {}, unpriced_models: [] },
};

const totals = (values: Partial<StatsResponse["tokens"]["by_model"][string]>) => ({
  input: 0,
  uncached_input: 0,
  output: 0,
  cache_read: 0,
  cache_write: 0,
  jobs: 0,
  cache_hit_ratio: 0,
  ...values,
});
const gpt = totals({ input: 1000, uncached_input: 600, output: 200, cache_read: 400, jobs: 1, cache_hit_ratio: 0.4 });
const claude = totals({ input: 1300, uncached_input: 1030, output: 400, cache_read: 150, cache_write: 120, jobs: 2, cache_hit_ratio: 0.1271186440677966 });
const none = totals({ jobs: 1 });

const full: StatsResponse = {
  days: 7,
  currency: "USD",
  work_delegated: {
    by_workflow: { consult: { succeeded: 1, failed: 1 }, implement: { failed: 1, succeeded: 1 } },
    by_state: { succeeded: 2, failed: 2 },
    worker_hours: 0.075,
    success_rate: 0.5,
    daily: { "2026-11-09": { succeeded: 1, failed: 1 }, "2026-11-10": { succeeded: 3, failed: 0 } },
  },
  failover_saves: { skipped_targets: 4, retries: 2, retries_after_failure: 1, unknown_skipped_targets: 1, unknown_attempts: 3 },
  tokens: {
    by_backend: { codex: gpt, claude, unassigned: none },
    by_model: { "gpt-x": gpt, "claude-y": claude, unassigned: none },
    by_target: { t1: gpt, t2: claude, unassigned: none },
  },
  estimated_cost: { total: 0.010624999999999999, by_model: { "claude-y": 0.009585, "gpt-x": 0.00104 }, unpriced_models: ["unassigned"] },
};

const renderView = (props: Partial<Parameters<typeof InsightsView>[0]> = {}) => {
  const onDaysChange = vi.fn();
  const onNavigate = vi.fn();
  render(<InsightsView stats={full} days={7} loading={false} error={null} onDaysChange={onDaysChange} onNavigate={onNavigate} {...props} />);
  return { onDaysChange, onNavigate };
};

const kpi = (name: string) => screen.getByText(name, { selector: "dt" }).nextElementSibling;

it("shows zeros and empty messages for empty data without a chart or unpriced notice", () => {
  renderView({ stats: empty });
  expect(screen.getByRole("heading", { name: "Insights" })).toBeInTheDocument();
  expect(kpi("Jobs finished")).toHaveTextContent("0");
  expect(kpi("Success rate")).toHaveTextContent("0.0%");
  expect(screen.getByText("No jobs finished in this window.")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.getByText("No token usage in this window.")).toBeInTheDocument();
  expect(screen.getByText("0.00 USD")).toBeInTheDocument();
  expect(screen.queryByText(/Unpriced models/)).not.toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

it("shows loading and error states without stats", () => {
  const { unmount } = render(<InsightsView stats={null} days={7} loading error={null} onDaysChange={vi.fn()} onNavigate={vi.fn()} />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading insights");
  unmount();
  renderView({ stats: null, error: "daemon offline" });
  expect(screen.getByRole("alert")).toHaveTextContent("daemon offline");
});

it("shows the work delegated cards, a named daily chart, and its table fallback", () => {
  renderView();
  expect(kpi("Jobs finished")).toHaveTextContent("4");
  expect(kpi("Succeeded")).toHaveTextContent("2");
  expect(kpi("Failed")).toHaveTextContent("2");
  expect(kpi("Success rate")).toHaveTextContent("50.0%");
  expect(kpi("Worker hours")).toHaveTextContent("0.07");
  expect(screen.getByRole("img", { name: /Daily jobs finished/ })).toBeInTheDocument();
  const table = screen.getByRole("table", { name: "Daily jobs finished" });
  const rows = within(table).getAllByRole("row");
  expect(rows).toHaveLength(3);
  expect(rows[1]).toHaveTextContent("2026-11-09");
  expect(rows[2]).toHaveTextContent("2026-11-10");
  expect(
    within(rows[2])
      .getAllByRole("cell")
      .map((cell) => cell.textContent),
  ).toEqual(["2026-11-10", "3", "0"]);
});

it("shows failover saves with a note for unknown counts", () => {
  renderView();
  expect(kpi("Failover saves")).toHaveTextContent("7");
  expect(kpi("Jobs saved by skipping a target")).toHaveTextContent("4");
  expect(kpi("Jobs saved by a same-target retry")).toHaveTextContent("2");
  expect(kpi("Jobs saved by retrying a failed job")).toHaveTextContent("1");
  expect(screen.getByText("Unknown for 1 job (skipped targets) and 3 jobs (attempts).")).toBeInTheDocument();
});

it("hides the unknown note when every job reports failover data", () => {
  renderView({ stats: { ...full, failover_saves: { ...full.failover_saves, unknown_skipped_targets: 0, unknown_attempts: 0 } } });
  expect(screen.queryByText(/Unknown for/)).not.toBeInTheDocument();
});

it("shows token tables per model, backend, and target with cache ratio bars", () => {
  renderView();
  const table = screen.getByRole("table", { name: "Tokens by model" });
  const rows = within(table).getAllByRole("row");
  expect(rows).toHaveLength(4);
  expect(
    within(rows[1])
      .getAllByRole("cell")
      .map((cell) => cell.textContent),
  ).toEqual(["gpt-x", "1", "600", "200", "400", "0", "40.0%"]);
  expect(within(rows[2]).getAllByRole("cell")[0]).toHaveTextContent("claude-y");
  expect(within(rows[2]).getAllByRole("cell")[6]).toHaveTextContent("12.7%");
  expect(within(rows[3]).getAllByRole("cell")[0]).toHaveTextContent("unassigned");
  expect(within(rows[1]).getByRole("meter", { name: "Cache hit ratio for gpt-x" })).toHaveAttribute("aria-valuenow", "40");
  expect(screen.getByRole("table", { name: "Tokens by backend" })).toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Tokens by target" })).toBeInTheDocument();
});

it("shows the cost total, the per-model table, and the unpriced notice", () => {
  renderView();
  expect(screen.getByText("0.01 USD")).toBeInTheDocument();
  const rows = within(screen.getByRole("table", { name: "Estimated cost by model" })).getAllByRole("row");
  expect(
    within(rows[1])
      .getAllByRole("cell")
      .map((cell) => cell.textContent),
  ).toEqual(["claude-y", "0.0096 USD"]);
  expect(
    within(rows[2])
      .getAllByRole("cell")
      .map((cell) => cell.textContent),
  ).toEqual(["gpt-x", "0.0010 USD"]);
  expect(screen.getByText("Unpriced models: unassigned. Their usage is left out of the estimate.")).toBeInTheDocument();
});

it("marks the current window and reports a window change", () => {
  const { onDaysChange } = renderView({ days: 30 });
  expect(screen.getByRole("button", { name: "30 days" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: "7 days" })).toHaveAttribute("aria-pressed", "false");
  fireEvent.click(screen.getByRole("button", { name: "365 days" }));
  expect(onDaysChange).toHaveBeenCalledWith(365);
  expect(screen.getByRole("button", { name: "1 day" })).toBeInTheDocument();
});

it("navigates back to the console", () => {
  const { onNavigate } = renderView();
  fireEvent.click(screen.getByRole("button", { name: "Back to console" }));
  expect(onNavigate).toHaveBeenCalledWith("/dashboard/");
});

it("counts a job that skipped several targets once and totals the three counters", () => {
  renderView({ stats: { ...full, failover_saves: { skipped_targets: 1, retries: 0, retries_after_failure: 2, unknown_skipped_targets: 0, unknown_attempts: 0 } } });
  expect(kpi("Jobs saved by skipping a target")).toHaveTextContent(/^1$/);
  expect(kpi("Jobs saved by a same-target retry")).toHaveTextContent(/^0$/);
  expect(kpi("Failover saves")).toHaveTextContent(/^3$/);
  expect(screen.queryByText("Targets skipped")).not.toBeInTheDocument();
});

const withCancelled: StatsResponse = {
  ...full,
  work_delegated: {
    ...full.work_delegated,
    by_workflow: { consult: { succeeded: 1, cancelled: 2 }, implement: { failed: 1, interrupted: 1 } },
    by_state: { succeeded: 1, failed: 1, cancelled: 2, interrupted: 1 },
  },
};

it("renders jobs by state and by workflow and state, including cancelled and interrupted", () => {
  renderView({ stats: withCancelled });
  expect(kpi("Jobs finished")).toHaveTextContent("5");
  const states = within(screen.getByRole("table", { name: "Jobs by state" })).getAllByRole("row");
  expect(
    states.slice(1).map((row) =>
      within(row)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ),
  ).toEqual([
    ["succeeded", "1"],
    ["failed", "1"],
    ["cancelled", "2"],
    ["interrupted", "1"],
  ]);
  const workflows = within(screen.getByRole("table", { name: "Jobs by workflow and state" })).getAllByRole("row");
  expect(
    workflows.slice(1).map((row) =>
      within(row)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ),
  ).toEqual([
    ["consult", "succeeded", "1"],
    ["consult", "cancelled", "2"],
    ["implement", "failed", "1"],
    ["implement", "interrupted", "1"],
  ]);
});

it("says no succeeded or failed jobs exist when only cancelled jobs finished", () => {
  const cancelledOnly: StatsResponse = {
    ...empty,
    work_delegated: { ...empty.work_delegated, by_workflow: { consult: { cancelled: 3 } }, by_state: { cancelled: 3 } },
  };
  renderView({ stats: cancelledOnly });
  expect(kpi("Jobs finished")).toHaveTextContent("3");
  expect(screen.getByText("No succeeded or failed jobs finished in this window.")).toBeInTheDocument();
  expect(screen.queryByText("No jobs finished in this window.")).not.toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Jobs by state" })).getByText("cancelled")).toBeInTheDocument();
});

it("shows the empty state for a 1-day window with the 1 day button pressed", () => {
  renderView({ stats: { ...empty, days: 1 }, days: 1 });
  expect(screen.getByRole("button", { name: "1 day" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("No jobs finished in this window.")).toBeInTheDocument();
  expect(kpi("Jobs finished")).toHaveTextContent("0");
  expect(screen.getByText("No token usage in this window.")).toBeInTheDocument();
});

it("formats large token counts with thousands separators", () => {
  const big = totals({ input: 1_500_000, uncached_input: 1_234_567, output: 2_000_000, cache_read: 265_433, cache_write: 12_345, jobs: 1234, cache_hit_ratio: 0.18 });
  renderView({ stats: { ...full, tokens: { by_backend: { claude: big }, by_model: { "claude-y": big }, by_target: { t2: big } } } });
  const row = within(screen.getByRole("table", { name: "Tokens by model" })).getAllByRole("row")[1];
  expect(
    within(row)
      .getAllByRole("cell")
      .map((cell) => cell.textContent),
  ).toEqual(["claude-y", "1,234", "1,234,567", "2,000,000", "265,433", "12,345", "18.0%"]);
});

it("formats fixed-point numbers like Python, rounding exact ties to even", () => {
  // Expected strings checked with python3: f"{x:.Nf}".
  expect(fixed(0.125, 2)).toBe("0.12");
  expect(fixed(0.375, 2)).toBe("0.38");
  expect(fixed(2.675, 2)).toBe("2.67");
  expect(fixed(0.5, 0)).toBe("0");
  expect(fixed(1.5, 0)).toBe("2");
  expect(fixed(9.5, 0)).toBe("10");
  expect(fixed(0.25, 1)).toBe("0.2");
  expect(fixed(0, 2)).toBe("0.00");
});

it("shows worker hours and the cost total with Python tie rounding", () => {
  renderView({
    stats: { ...full, work_delegated: { ...full.work_delegated, worker_hours: 0.125 }, estimated_cost: { total: 0.125, by_model: {}, unpriced_models: [] } },
  });
  expect(kpi("Worker hours")).toHaveTextContent(/^0\.12$/);
  expect(screen.getByText("0.12 USD")).toBeInTheDocument();
});

it("shows the success rate percent with Python tie rounding", () => {
  renderView({ stats: { ...full, work_delegated: { ...full.work_delegated, success_rate: 0.0625 } } });
  expect(kpi("Success rate")).toHaveTextContent(/^6.2%$/);
});
