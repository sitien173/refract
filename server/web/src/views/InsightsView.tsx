import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { STATS_DAYS, type StatsDays, type StatsResponse, type TokenTotals } from "../api";
import { ViewNav } from "../components/ViewNav";

type InsightsViewProps = {
  stats: StatsResponse | null;
  days: StatsDays;
  loading: boolean;
  error: string | null;
  onDaysChange: (days: StatsDays) => void;
  onNavigate: (path: string) => void;
};

export type Day = { day: string; succeeded: number; failed: number };

const CHART_WIDTH = 600;
const CHART_HEIGHT = 160;
const CHART_LABEL_HEIGHT = 20;
const Y_AXIS_WIDTH = 40;
const PLOT_TOP = 10;
const PLOT_BOTTOM = CHART_HEIGHT - CHART_LABEL_HEIGHT;
const PLOT_HEIGHT = PLOT_BOTTOM - PLOT_TOP;
const PLOT_WIDTH = CHART_WIDTH - Y_AXIS_WIDTH;
const MAX_BAR_WIDTH = 40;

/**
 * Formats like Python's `f"{value:.{digits}f}"`, which rounds exact ties to even where `toFixed` rounds them up.
 * Domain: finite, non-negative values below 1e21. `toFixed` switches to exponent notation from 1e21, and a
 * negative value would break the tie check.
 */
export function fixed(value: number, digits: number): string {
  const rounded = value.toFixed(digits);
  const exact = value.toFixed(100);
  const cut = exact.indexOf(".") + 1 + digits;
  const isTie = exact[cut] === "5" && /^0*$/.test(exact.slice(cut + 1));
  if (!isTie || Number(rounded[rounded.length - 1]) % 2 === 0) return rounded;
  return exact.slice(0, digits === 0 ? cut - 1 : cut);
}

const percent = (ratio: number) => `${fixed(ratio * 100, 1)}%`;
const count = (value: number) => value.toLocaleString();

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg bg-card p-4 shadow-card">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-2xl font-semibold tracking-tight">{value}</dd>
    </div>
  );
}

function KpiGrid({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <dl aria-label={label} className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {children}
    </dl>
  );
}

function localDateString(timeMs: number, tzOffsetMinutes: number): string {
  const localMs = timeMs + tzOffsetMinutes * 60_000;
  const d = new Date(localMs);
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function fillDays(daily: Record<string, { succeeded: number; failed: number }>, windowDays: number, now: number, tzOffsetMinutes: number): Day[] {
  const startMs = now - windowDays * 24 * 60 * 60 * 1000;
  const daySet = new Set<string>();

  for (let i = 0; i <= windowDays; i++) {
    daySet.add(localDateString(startMs + i * 86_400_000, tzOffsetMinutes));
  }

  for (const k of Object.keys(daily)) {
    daySet.add(k);
  }

  const sortedKeys = Array.from(daySet).sort();
  return sortedKeys.map((key) => ({
    day: key,
    succeeded: daily[key]?.succeeded ?? 0,
    failed: daily[key]?.failed ?? 0,
  }));
}

export function niceTicks(max: number): number[] {
  const effectiveMax = Math.max(max || 0, 1);
  const exponent = Math.floor(Math.log10(effectiveMax));
  const steps: number[] = [];
  for (let exp = Math.max(0, exponent - 1); exp <= exponent + 2; exp++) {
    for (const factor of [1, 2, 5]) {
      steps.push(factor * 10 ** exp);
    }
  }
  steps.sort((a, b) => a - b);

  let chosenStep = steps[steps.length - 1];
  for (const step of steps) {
    if (Math.ceil(effectiveMax / step) <= 4) {
      chosenStep = step;
      break;
    }
  }

  const k = Math.max(2, Math.ceil(effectiveMax / chosenStep));
  const ticks: number[] = [];
  for (let i = 0; i <= k; i++) {
    ticks.push(i * chosenStep);
  }
  return ticks;
}

function formatTick(val: number): string {
  if (val < 10_000) return val.toLocaleString();
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(val);
}

function formatShortDate(dateStr: string): string {
  const [y, m, d] = dateStr.split("-").map(Number);
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) {
    return dateStr;
  }
  const date = new Date(Date.UTC(y, m - 1, d));
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(date);
}

export function getXLabels(days: Day[], windowDays: number): { index: number; text: string }[] {
  if (days.length === 0) return [];
  const labels: { index: number; text: string }[] = [];

  if (windowDays === 1 || days.length <= 8) {
    for (let i = 0; i < days.length; i++) {
      labels.push({ index: i, text: formatShortDate(days[i].day) });
    }
  } else if (windowDays === 365 || days.length > 35) {
    for (let i = 0; i < days.length; i++) {
      if (days[i].day.endsWith("-01")) {
        labels.push({ index: i, text: formatShortDate(days[i].day) });
      }
    }
  } else {
    for (let i = 0; i < days.length; i++) {
      if (i % 7 === 0) {
        labels.push({ index: i, text: formatShortDate(days[i].day) });
      }
    }
  }
  return labels;
}

export function DailyChart({ days, windowDays = 7 }: { days: Day[]; windowDays?: number }) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const [rovingIndex, setRovingIndex] = useState<number>(0);
  const groupRefs = useRef<(SVGGElement | null)[]>([]);

  if (days.length === 0) return null;

  const maxCount = Math.max(...days.map((d) => d.succeeded + d.failed), 0);
  const ticks = niceTicks(maxCount);
  const maxTick = ticks[ticks.length - 1];

  const slot = PLOT_WIDTH / days.length;
  const barWidth = Math.max(1, Math.min(MAX_BAR_WIDTH, slot * 0.7));

  const xLabels = getXLabels(days, windowDays);
  const isRoving = windowDays === 365 || days.length > 31;
  const effectiveRovingIndex = Math.max(0, Math.min(rovingIndex, days.length - 1));

  const activeIndex = hoveredIndex ?? focusedIndex;
  const activeDay = activeIndex !== null ? days[activeIndex] : null;

  const label = `Daily jobs finished, ${days[0].day} to ${days[days.length - 1].day}: succeeded and failed`;

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    let targetIndex: number | null = null;
    if (e.key === "ArrowRight") {
      targetIndex = Math.min(days.length - 1, index + 1);
    } else if (e.key === "ArrowLeft") {
      targetIndex = Math.max(0, index - 1);
    } else if (e.key === "Home") {
      targetIndex = 0;
    } else if (e.key === "End") {
      targetIndex = days.length - 1;
    }

    if (targetIndex !== null) {
      e.preventDefault();
      if (isRoving) setRovingIndex(targetIndex);
      setFocusedIndex(targetIndex);
      groupRefs.current[targetIndex]?.focus();
    }
  };

  const activeCenterX = activeIndex !== null ? Y_AXIS_WIDTH + activeIndex * slot + slot / 2 : 0;
  const tooltipLeftPercent = Math.max(12, Math.min(88, (activeCenterX / CHART_WIDTH) * 100));

  return (
    <div className="relative flex flex-col gap-2 w-full">
      <div className="flex items-center gap-4 text-sm text-muted-foreground w-full" aria-hidden="true">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-primary" /> Succeeded
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-destructive" /> Failed
        </span>
      </div>

      {activeDay && (
        <div
          role="tooltip"
          className="pointer-events-none absolute top-0 z-10 rounded-md bg-popover px-3 py-1.5 text-xs text-popover-foreground shadow-md border border-border"
          style={{
            left: `${tooltipLeftPercent}%`,
            transform: "translateX(-50%)",
          }}
        >
          <span className="font-medium">{activeDay.day}: </span>
          <span className="text-primary font-medium">{activeDay.succeeded} succeeded</span>
          <span>, </span>
          <span className="text-destructive font-medium">{activeDay.failed} failed</span>
        </div>
      )}

      {/* biome-ignore lint/a11y/useSemanticElements: SVG chart container represents a named group */}
      <svg role="group" aria-label={label} viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="w-full overflow-visible">
        <title>{label}</title>

        {/* Y-axis gridlines and labels */}
        {ticks.map((val) => {
          const y = PLOT_BOTTOM - (val / maxTick) * PLOT_HEIGHT;
          return (
            <g key={val} className="text-muted-foreground">
              <line x1={Y_AXIS_WIDTH} x2={CHART_WIDTH} y1={y} y2={y} className="stroke-border/50" strokeDasharray={val === 0 ? undefined : "3 3"} />
              <text x={Y_AXIS_WIDTH - 6} y={y + 3.5} textAnchor="end" className="fill-muted-foreground text-[10px]">
                {formatTick(val)}
              </text>
            </g>
          );
        })}

        {/* X-axis baseline */}
        <line x1={Y_AXIS_WIDTH} x2={CHART_WIDTH} y1={PLOT_BOTTOM} y2={PLOT_BOTTOM} className="stroke-border" />

        {/* Day bar groups */}
        {days.map((d, index) => {
          const x = Y_AXIS_WIDTH + index * slot + (slot - barWidth) / 2;
          const succeededHeight = (d.succeeded / maxTick) * PLOT_HEIGHT;
          const failedHeight = (d.failed / maxTick) * PLOT_HEIGHT;
          const tabIndex = isRoving ? (index === effectiveRovingIndex ? 0 : -1) : 0;
          const isSelected = index === activeIndex;

          return (
            // biome-ignore lint/a11y/noInteractiveElementToNoninteractiveRole: bar group is focusable for chart tooltip inspection
            <g
              key={d.day}
              ref={(el) => {
                groupRefs.current[index] = el;
              }}
              role="img"
              tabIndex={tabIndex}
              aria-label={`${d.day}: ${d.succeeded} succeeded, ${d.failed} failed`}
              className="outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring cursor-pointer"
              onMouseEnter={() => setHoveredIndex(index)}
              onMouseLeave={() => setHoveredIndex(null)}
              onFocus={() => {
                setFocusedIndex(index);
                if (isRoving) setRovingIndex(index);
              }}
              onBlur={() => setFocusedIndex(null)}
              onKeyDown={(e) => handleKeyDown(e, index)}
            >
              {/* Invisible full-height hit area */}
              <rect x={Y_AXIS_WIDTH + index * slot} y={PLOT_TOP} width={slot} height={PLOT_HEIGHT} fill="transparent" />
              {isSelected && <rect x={Y_AXIS_WIDTH + index * slot} y={PLOT_TOP} width={slot} height={PLOT_HEIGHT} className="fill-muted/20" />}
              {succeededHeight > 0 && <rect x={x} y={PLOT_BOTTOM - succeededHeight} width={barWidth} height={succeededHeight} className="fill-primary" />}
              {failedHeight > 0 && <rect x={x} y={PLOT_BOTTOM - succeededHeight - failedHeight} width={barWidth} height={failedHeight} className="fill-destructive" />}
            </g>
          );
        })}

        {/* X-axis labels */}
        {xLabels.map(({ index, text }) => {
          const centerX = Y_AXIS_WIDTH + index * slot + slot / 2;
          return (
            <text key={days[index].day} x={centerX} y={CHART_HEIGHT - 3} textAnchor="middle" className="fill-muted-foreground text-[10px]">
              {text}
            </text>
          );
        })}
      </svg>

      <table aria-label="Daily jobs finished" className="sr-only">
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col">Succeeded</th>
            <th scope="col">Failed</th>
          </tr>
        </thead>
        <tbody>
          {days.map((d) => (
            <tr key={d.day}>
              <td>{d.day}</td>
              <td>{d.succeeded}</td>
              <td>{d.failed}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SimpleTable({ label, headings, rows }: { label: string; headings: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto rounded-lg bg-card shadow-card">
      <table aria-label={label} className="w-full text-left text-sm">
        <thead className="text-muted-foreground">
          <tr>
            {headings.map((heading) => (
              <th key={heading} scope="col" className="p-3 font-medium">
                {heading}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((cells) => (
            <tr key={cells.slice(0, -1).join("/")} className="border-t border-border">
              {cells.map((cell, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: cells are positional and never reordered
                <td key={index} className="p-3">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JobBreakdown({ work }: { work: StatsResponse["work_delegated"] }) {
  const rows = work.breakdown.map((row) => [row.profile, row.workflow, row.target, row.state, count(row.jobs)]);
  return (
    <div className="flex flex-col gap-3">
      <SimpleTable label="Jobs by profile, workflow, target, and state" headings={["Profile", "Workflow", "Target", "State", "Jobs"]} rows={rows} />
    </div>
  );
}

function WorkDelegated({ work, windowDays }: { work: StatsResponse["work_delegated"]; windowDays: number }) {
  const days = fillDays(work.daily, windowDays, Date.now(), -new Date().getTimezoneOffset() || 0);
  const total = Object.values(work.by_state).reduce((sum, value) => sum + value, 0);
  return (
    <section aria-label="Work delegated" className="flex flex-col gap-3">
      <h2 className="text-xl font-semibold tracking-tight">Work delegated</h2>
      <KpiGrid label="Work delegated totals">
        <Kpi label="Jobs finished" value={count(total)} />
        <Kpi label="Succeeded" value={count(work.by_state.succeeded ?? 0)} />
        <Kpi label="Failed" value={count(work.by_state.failed ?? 0)} />
        <Kpi label="Success rate" value={percent(work.success_rate)} />
        <Kpi label="Worker hours" value={fixed(work.worker_hours, 2)} />
      </KpiGrid>
      <DailyChart key={windowDays} days={days} windowDays={windowDays} />
      {total > 0 && <JobBreakdown work={work} />}
    </section>
  );
}

function FailoverSaves({ saves }: { saves: StatsResponse["failover_saves"] }) {
  const unknown = [
    saves.unknown_skipped_targets > 0 && `${saves.unknown_skipped_targets} ${saves.unknown_skipped_targets === 1 ? "job" : "jobs"} (skipped targets)`,
    saves.unknown_attempts > 0 && `${saves.unknown_attempts} ${saves.unknown_attempts === 1 ? "job" : "jobs"} (attempts)`,
  ].filter(Boolean);
  const total = saves.skipped_targets + saves.retries + saves.retries_after_failure;
  return (
    <section aria-label="Failover saves" className="flex flex-col gap-3">
      <h2 className="text-xl font-semibold tracking-tight">Failover saves</h2>
      <KpiGrid label="Failover saves totals">
        <Kpi label="Failover saves" value={count(total)} />
        <Kpi label="Jobs saved by skipping a target" value={count(saves.skipped_targets)} />
        <Kpi label="Jobs saved by a same-target retry" value={count(saves.retries)} />
        <Kpi label="Jobs saved by retrying a failed job" value={count(saves.retries_after_failure)} />
      </KpiGrid>
      {unknown.length > 0 && <p className="text-sm text-muted-foreground">Unknown for {unknown.join(" and ")}.</p>}
    </section>
  );
}

function TokenTable({ title, rows }: { title: string; rows: Record<string, TokenTotals> }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-lg font-semibold tracking-tight">{title}</h3>
      <div className="overflow-x-auto rounded-lg bg-card shadow-card">
        <table aria-label={`Tokens ${title.toLowerCase()}`} className="w-full text-left text-sm">
          <thead className="text-muted-foreground">
            <tr>
              <th scope="col" className="p-3 font-medium">
                Name
              </th>
              <th scope="col" className="p-3 font-medium">
                Jobs
              </th>
              <th scope="col" className="p-3 font-medium">
                Uncached input
              </th>
              <th scope="col" className="p-3 font-medium">
                Output
              </th>
              <th scope="col" className="p-3 font-medium">
                Cache read
              </th>
              <th scope="col" className="p-3 font-medium">
                Cache write
              </th>
              <th scope="col" className="p-3 font-medium">
                Cache hit ratio
              </th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(rows).map(([name, row]) => (
              <tr key={name} className="border-t border-border">
                <td className="p-3">{name}</td>
                <td className="p-3">{count(row.jobs)}</td>
                <td className="p-3">{count(row.uncached_input)}</td>
                <td className="p-3">{count(row.output)}</td>
                <td className="p-3">{count(row.cache_read)}</td>
                <td className="p-3">{count(row.cache_write)}</td>
                <td className="p-3">
                  <div className="flex items-center gap-2">
                    {/* biome-ignore lint/a11y/useSemanticElements: a native <meter> cannot be styled as a plain CSS bar across browsers */}
                    <div
                      role="meter"
                      aria-label={`Cache hit ratio for ${name}`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(row.cache_hit_ratio * 100)}
                      className="h-2 w-24 overflow-hidden rounded-full bg-muted"
                    >
                      <div className="h-full bg-primary" style={{ width: `${row.cache_hit_ratio * 100}%` }} />
                    </div>
                    <span>{percent(row.cache_hit_ratio)}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Tokens({ tokens }: { tokens: StatsResponse["tokens"] }) {
  const empty = Object.keys(tokens.by_model).length === 0;
  return (
    <section aria-label="Tokens" className="flex flex-col gap-3">
      <h2 className="text-xl font-semibold tracking-tight">Tokens</h2>
      {empty ? (
        <p className="text-sm text-muted-foreground">No token usage in this window.</p>
      ) : (
        <>
          <TokenTable title="By model" rows={tokens.by_model} />
          <TokenTable title="By backend" rows={tokens.by_backend} />
          <TokenTable title="By target" rows={tokens.by_target} />
        </>
      )}
    </section>
  );
}

function Cost({ cost, currency }: { cost: StatsResponse["estimated_cost"]; currency: string }) {
  const models = Object.entries(cost.by_model);
  return (
    <section aria-label="Estimated cost" className="flex flex-col gap-3">
      <h2 className="text-xl font-semibold tracking-tight">Estimated cost</h2>
      <KpiGrid label="Estimated cost total">
        <Kpi label="Total" value={`${fixed(cost.total, 2)} ${currency}`} />
      </KpiGrid>
      {models.length > 0 && (
        <div className="overflow-x-auto rounded-lg bg-card shadow-card">
          <table aria-label="Estimated cost by model" className="w-full text-left text-sm">
            <thead className="text-muted-foreground">
              <tr>
                <th scope="col" className="p-3 font-medium">
                  Model
                </th>
                <th scope="col" className="p-3 font-medium">
                  Cost
                </th>
              </tr>
            </thead>
            <tbody>
              {models.map(([model, amount]) => (
                <tr key={model} className="border-t border-border">
                  <td className="p-3">{model}</td>
                  <td className="p-3">{`${fixed(amount, 4)} ${currency}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {cost.unpriced_models.length > 0 && (
        <p className="callout callout-warning">{`Unpriced models: ${cost.unpriced_models.join(", ")}. Their usage is left out of the estimate.`}</p>
      )}
    </section>
  );
}

export function InsightsView({ stats, days, loading, error, onDaysChange, onNavigate }: InsightsViewProps) {
  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Insights</h1>
        <div className="flex items-center gap-3">
          <ViewNav current="insights" onNavigate={onNavigate} />
          <Button variant="secondary" onClick={() => onNavigate("/dashboard/")}>
            Back to console
          </Button>
        </div>
      </header>
      <fieldset className="flex items-center gap-2">
        <legend className="sr-only">Window</legend>
        {STATS_DAYS.map((value) => (
          <Button key={value} variant={value === days ? "default" : "secondary"} aria-pressed={value === days} onClick={() => onDaysChange(value)}>
            {value === 1 ? "1 day" : `${value} days`}
          </Button>
        ))}
      </fieldset>
      {error && (
        <div className="callout callout-error" role="alert">
          {error}
        </div>
      )}
      {loading && (
        <p role="status" className="text-sm text-muted-foreground">
          Loading insights…
        </p>
      )}
      {stats && (
        <>
          <WorkDelegated work={stats.work_delegated} windowDays={stats.days} />
          <FailoverSaves saves={stats.failover_saves} />
          <Tokens tokens={stats.tokens} />
          <Cost cost={stats.estimated_cost} currency={stats.currency} />
        </>
      )}
    </main>
  );
}
