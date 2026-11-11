import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { StatsResponse } from "../api";
import { DailyChart, fillDays, fixed, getXLabels, InsightsView, niceTicks } from "./InsightsView";

const empty: StatsResponse = {
  days: 7,
  currency: "USD",
  work_delegated: { by_workflow: {}, by_state: {}, breakdown: [], worker_hours: 0, success_rate: 0, daily: {} },
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
    breakdown: [
      { profile: "default", workflow: "consult", target: "t1", state: "succeeded", jobs: 1 },
      { profile: "default", workflow: "consult", target: "t1", state: "failed", jobs: 1 },
      { profile: "default", workflow: "implement", target: "t2", state: "failed", jobs: 1 },
      { profile: "default", workflow: "implement", target: "t2", state: "succeeded", jobs: 1 },
    ],
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

it("shows zeros and empty messages for empty data without an unpriced notice", () => {
  renderView({ stats: empty });
  expect(screen.getByRole("heading", { name: "Insights" })).toBeInTheDocument();
  expect(kpi("Jobs finished")).toHaveTextContent("0");
  expect(kpi("Success rate")).toHaveTextContent("0.0%");
  expect(screen.getByRole("group", { name: /Daily jobs finished/ })).toBeInTheDocument();
  expect(screen.getByText("No token usage in this window.")).toBeInTheDocument();
  expect(screen.getByText("0.00 USD")).toBeInTheDocument();
  expect(screen.queryByText(/Unpriced models/)).not.toBeInTheDocument();
  expect(screen.queryByRole("table", { name: "Jobs by profile, workflow, target, and state" })).not.toBeInTheDocument();
});

it("shows loading and error states without stats", () => {
  const { unmount } = render(<InsightsView stats={null} days={7} loading error={null} onDaysChange={vi.fn()} onNavigate={vi.fn()} />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading insights");
  unmount();
  renderView({ stats: null, error: "daemon offline" });
  expect(screen.getByRole("alert")).toHaveTextContent("daemon offline");
});

it("shows the work delegated cards, a named daily chart, and its table fallback", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-10T12:00:00Z"));
  try {
    renderView();
    expect(kpi("Jobs finished")).toHaveTextContent("4");
    expect(kpi("Succeeded")).toHaveTextContent("2");
    expect(kpi("Failed")).toHaveTextContent("2");
    expect(kpi("Success rate")).toHaveTextContent("50.0%");
    expect(kpi("Worker hours")).toHaveTextContent("0.07");
    expect(screen.getByRole("group", { name: /Daily jobs finished/ })).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Daily jobs finished" });
    const rows = within(table).getAllByRole("row");
    // 7-day window with fake system time produces exactly 8 day rows + 1 header row = 9 rows total
    expect(rows).toHaveLength(9);
    // Missing day filled with zeros
    const zeroCells = within(rows[1])
      .getAllByRole("cell")
      .map((c) => c.textContent);
    expect(zeroCells[1]).toBe("0");
    expect(zeroCells[2]).toBe("0");
    expect(within(table).getByText("2026-11-09")).toBeInTheDocument();
    expect(within(table).getByText("2026-11-10")).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
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
    breakdown: [
      { profile: "default", workflow: "consult", target: "t1", state: "succeeded", jobs: 1 },
      { profile: "default", workflow: "consult", target: "t1", state: "cancelled", jobs: 2 },
      { profile: "default", workflow: "implement", target: "t2", state: "failed", jobs: 1 },
      { profile: "default", workflow: "implement", target: "t2", state: "interrupted", jobs: 1 },
    ],
  },
};

it("renders jobs by profile, workflow, target, and state, and omits the removed jobs by state table", () => {
  renderView({ stats: withCancelled });
  expect(kpi("Jobs finished")).toHaveTextContent("5");
  expect(screen.queryByRole("table", { name: "Jobs by state" })).not.toBeInTheDocument();
  const table = screen.getByRole("table", { name: "Jobs by profile, workflow, target, and state" });
  const rows = within(table).getAllByRole("row");
  expect(
    within(rows[0])
      .getAllByRole("columnheader")
      .map((th) => th.textContent),
  ).toEqual(["Profile", "Workflow", "Target", "State", "Jobs"]);
  expect(
    rows.slice(1).map((row) =>
      within(row)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ),
  ).toEqual([
    ["default", "consult", "t1", "succeeded", "1"],
    ["default", "consult", "t1", "cancelled", "2"],
    ["default", "implement", "t2", "failed", "1"],
    ["default", "implement", "t2", "interrupted", "1"],
  ]);
});

it("says no succeeded or failed jobs exist when only cancelled jobs finished", () => {
  const cancelledOnly: StatsResponse = {
    ...empty,
    work_delegated: {
      ...empty.work_delegated,
      by_workflow: { consult: { cancelled: 3 } },
      by_state: { cancelled: 3 },
      breakdown: [{ profile: "default", workflow: "consult", target: "t1", state: "cancelled", jobs: 3 }],
    },
  };
  renderView({ stats: cancelledOnly });
  expect(kpi("Jobs finished")).toHaveTextContent("3");
  expect(screen.getByRole("group", { name: /Daily jobs finished/ })).toBeInTheDocument();
  expect(screen.queryByRole("table", { name: "Jobs by state" })).not.toBeInTheDocument();
  expect(within(screen.getByRole("table", { name: "Jobs by profile, workflow, target, and state" })).getByText("cancelled")).toBeInTheDocument();
});

it("shows the empty state for a 1-day window with the 1 day button pressed", () => {
  renderView({ stats: { ...empty, days: 1 }, days: 1 });
  expect(screen.getByRole("button", { name: "1 day" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("group", { name: /Daily jobs finished/ })).toBeInTheDocument();
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

describe("fillDays", () => {
  it("fills missing days with zeros across the local date window and unions outside keys", () => {
    // 2026-11-10T12:00:00Z with tzOffset = 0 (UTC).
    // Window = 1 day: local range is 2026-11-09 to 2026-11-10.
    const now = Date.UTC(2026, 10, 10, 12, 0, 0); // Month is 0-indexed (10 = November)
    const daily = {
      "2026-11-10": { succeeded: 3, failed: 1 },
      "2026-11-05": { succeeded: 1, failed: 0 }, // outside range
    };
    const days = fillDays(daily, 1, now, 0);
    expect(days).toEqual([
      { day: "2026-11-05", succeeded: 1, failed: 0 },
      { day: "2026-11-09", succeeded: 0, failed: 0 },
      { day: "2026-11-10", succeeded: 3, failed: 1 },
    ]);
  });

  it("handles 7-day window with timezone offset", () => {
    // 2026-11-10T20:00:00Z with tzOffset = +300 minutes (+5h) -> local time 2026-11-11 01:00.
    // 7 days earlier is 2026-11-04 01:00.
    const now = Date.UTC(2026, 10, 10, 20, 0, 0);
    const days = fillDays({}, 7, now, 300);
    expect(days).toHaveLength(8);
    expect(days[0].day).toBe("2026-11-04");
    expect(days[7].day).toBe("2026-11-11");
    expect(days.every((d) => d.succeeded === 0 && d.failed === 0)).toBe(true);
  });

  it("handles negative timezone offset and exact local midnight", () => {
    // 2026-11-10T02:00:00Z with tzOffset = -480 minutes (-8h, Pacific) -> local time 2026-11-09 18:00.
    const nowNegative = Date.UTC(2026, 10, 10, 2, 0, 0);
    const daysNeg = fillDays({}, 1, nowNegative, -480);
    expect(daysNeg).toHaveLength(2);
    expect(daysNeg[0].day).toBe("2026-11-08");
    expect(daysNeg[1].day).toBe("2026-11-09");

    // Exactly at local midnight
    const nowMidnight = Date.UTC(2026, 10, 10, 0, 0, 0);
    const daysMidnight = fillDays({}, 1, nowMidnight, 0);
    expect(daysMidnight).toHaveLength(2);
    expect(daysMidnight[0].day).toBe("2026-11-09");
    expect(daysMidnight[1].day).toBe("2026-11-10");
  });

  it("produces exactly 31 keys for 30-day window and 366 keys for 365-day window", () => {
    const now = Date.UTC(2026, 10, 10, 12, 0, 0);
    const days30 = fillDays({}, 30, now, 0);
    expect(days30).toHaveLength(31);

    const days365 = fillDays({}, 365, now, 0);
    expect(days365).toHaveLength(366);
  });
});

describe("niceTicks", () => {
  it("falls back to 1 when max is zero or negative and returns 3 to 5 ticks from 0", () => {
    const ticks0 = niceTicks(0);
    expect(ticks0[0]).toBe(0);
    expect(ticks0.length).toBeGreaterThanOrEqual(3);
    expect(ticks0.length).toBeLessThanOrEqual(5);
    expect(ticks0[ticks0.length - 1]).toBeGreaterThanOrEqual(1);
  });

  it("picks 1, 2, 5 * 10^n steps and covers various max values", () => {
    for (const max of [1, 2, 3, 4, 5, 8, 10, 15, 20, 50, 100, 250, 1000]) {
      const ticks = niceTicks(max);
      expect(ticks[0]).toBe(0);
      expect(ticks.length).toBeGreaterThanOrEqual(3);
      expect(ticks.length).toBeLessThanOrEqual(5);
      expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(max);
      const step = ticks[1] - ticks[0];
      for (let i = 1; i < ticks.length; i++) {
        expect(ticks[i] - ticks[i - 1]).toBe(step);
      }
      const exp = Math.floor(Math.log10(step));
      const factor = Math.round(step / 10 ** exp);
      expect([1, 2, 5]).toContain(factor);
    }
  });
});

describe("getXLabels", () => {
  it("labels each day for 1-day window", () => {
    const days = [
      { day: "2026-11-09", succeeded: 0, failed: 0 },
      { day: "2026-11-10", succeeded: 0, failed: 0 },
    ];
    const labels = getXLabels(days, 1);
    expect(labels.map((l) => l.text)).toEqual(["Nov 9", "Nov 10"]);
  });

  it("labels every day when range has at most 8 days", () => {
    const days = Array.from({ length: 8 }, (_, i) => ({
      day: `2026-11-0${i + 1}`,
      succeeded: 0,
      failed: 0,
    }));
    const labels = getXLabels(days, 7);
    expect(labels).toHaveLength(8);
    expect(labels[0].text).toBe("Nov 1");
    expect(labels[7].text).toBe("Nov 8");
  });

  it("thins labels about weekly for 30 days", () => {
    const days = Array.from({ length: 31 }, (_, i) => ({
      day: `2026-10-${String(i + 1).padStart(2, "0")}`,
      succeeded: 0,
      failed: 0,
    }));
    const labels = getXLabels(days, 30);
    expect(labels.length).toBe(5); // indices 0, 7, 14, 21, 28
    expect(labels[0].text).toBe("Oct 1");
    expect(labels[1].text).toBe("Oct 8");
  });

  it("thins labels monthly for 365 days (first day of each month)", () => {
    const days: { day: string; succeeded: number; failed: number }[] = [];
    // Nov 11, 2025 to Nov 11, 2026
    const start = new Date(Date.UTC(2025, 10, 11));
    for (let i = 0; i < 366; i++) {
      const d = new Date(start.getTime() + i * 86400000);
      const str = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
      days.push({ day: str, succeeded: 0, failed: 0 });
    }
    const labels = getXLabels(days, 365);
    expect(labels.length).toBe(12); // Dec 1, Jan 1, ..., Nov 1
    expect(labels.every((l) => days[l.index].day.endsWith("-01"))).toBe(true);
  });
});

describe("DailyChart component", () => {
  it("renders axes and gridlines even when all days are zero", () => {
    const zeroDays = [
      { day: "2026-11-09", succeeded: 0, failed: 0 },
      { day: "2026-11-10", succeeded: 0, failed: 0 },
    ];
    render(<DailyChart days={zeroDays} windowDays={1} />);
    const svg = screen.getByRole("group", { name: /Daily jobs finished/ });
    expect(svg).toBeInTheDocument();
    // Ticks should render count labels inside the SVG
    expect(within(svg).getByText("0")).toBeInTheDocument();
    expect(within(svg).getByText("1")).toBeInTheDocument();
    expect(within(svg).getByText("2")).toBeInTheDocument();
    expect(within(svg).getByText("Nov 9")).toBeInTheDocument();
    expect(within(svg).getByText("Nov 10")).toBeInTheDocument();
  });

  it("formats large tick numbers compactly", () => {
    const bigDays = [
      { day: "2026-11-09", succeeded: 1_000_000, failed: 0 },
      { day: "2026-11-10", succeeded: 500_000, failed: 0 },
    ];
    render(<DailyChart days={bigDays} windowDays={1} />);
    const svg = screen.getByRole("group", { name: /Daily jobs finished/ });
    expect(within(svg).getByText("1M")).toBeInTheDocument();
  });

  it("shows tooltip on focus with date, succeeded, and failed counts, and hides on blur", () => {
    const days = [
      { day: "2026-11-09", succeeded: 5, failed: 2 },
      { day: "2026-11-10", succeeded: 8, failed: 0 },
    ];
    render(<DailyChart days={days} windowDays={1} />);
    const bar0 = screen.getByRole("img", { name: "2026-11-09: 5 succeeded, 2 failed" });
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    fireEvent.focus(bar0);
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toBeInTheDocument();
    expect(tooltip).toHaveTextContent("2026-11-09: 5 succeeded, 2 failed");

    fireEvent.blur(bar0);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("shows tooltip on mouse hover and hides on mouse leave", () => {
    const days = [{ day: "2026-11-09", succeeded: 3, failed: 1 }];
    render(<DailyChart days={days} windowDays={1} />);
    const bar = screen.getByRole("img", { name: "2026-11-09: 3 succeeded, 1 failed" });

    fireEvent.mouseEnter(bar);
    expect(screen.getByRole("tooltip")).toHaveTextContent("2026-11-09");
    fireEvent.mouseLeave(bar);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("uses roving tabindex with one tab stop, arrows, Home, End, and bounds clamping for 365 days", () => {
    const days = Array.from({ length: 366 }, (_, i) => ({
      day: `day-${i}`,
      succeeded: i,
      failed: 0,
    }));
    const { container } = render(<DailyChart days={days} windowDays={365} />);
    const tabStops = container.querySelectorAll('g[tabindex="0"]');
    expect(tabStops).toHaveLength(1);

    const first = screen.getByRole("img", { name: "day-0: 0 succeeded, 0 failed" });
    const second = screen.getByRole("img", { name: "day-1: 1 succeeded, 0 failed" });
    const last = screen.getByRole("img", { name: "day-365: 365 succeeded, 0 failed" });

    fireEvent.focus(first);
    expect(screen.getByRole("tooltip")).toHaveTextContent("day-0");

    // Arrow keys
    fireEvent.keyDown(first, { key: "ArrowRight" });
    expect(screen.getByRole("tooltip")).toHaveTextContent("day-1");

    fireEvent.keyDown(second, { key: "ArrowLeft" });
    expect(screen.getByRole("tooltip")).toHaveTextContent("day-0");

    // Left arrow at start clamps to 0
    fireEvent.keyDown(first, { key: "ArrowLeft" });
    expect(screen.getByRole("tooltip")).toHaveTextContent("day-0");

    // End key moves to last day
    fireEvent.keyDown(first, { key: "End" });
    expect(screen.getByRole("tooltip")).toHaveTextContent("day-365");

    // Right arrow at end clamps to last
    fireEvent.keyDown(last, { key: "ArrowRight" });
    expect(screen.getByRole("tooltip")).toHaveTextContent("day-365");

    // Home key moves back to first day
    fireEvent.keyDown(last, { key: "Home" });
    expect(screen.getByRole("tooltip")).toHaveTextContent("day-0");
  });
});
