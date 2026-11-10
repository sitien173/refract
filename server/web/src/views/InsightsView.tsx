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

type Day = { day: string; succeeded: number; failed: number };

const CHART_WIDTH = 600;
const CHART_HEIGHT = 160;
const CHART_LABEL_HEIGHT = 18;
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

function DailyChart({ days }: { days: Day[] }) {
  const max = Math.max(...days.map((d) => d.succeeded + d.failed), 1);
  const plotHeight = CHART_HEIGHT - CHART_LABEL_HEIGHT;
  const slot = CHART_WIDTH / days.length;
  const barWidth = Math.min(MAX_BAR_WIDTH, slot * 0.7);
  const label = `Daily jobs finished, ${days[0].day} to ${days[days.length - 1].day}: succeeded and failed`;

  return (
    <>
      <svg role="img" aria-label={label} viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="w-full max-w-2xl">
        <title>{label}</title>
        {days.map((d, index) => {
          const x = index * slot + (slot - barWidth) / 2;
          const succeededHeight = (d.succeeded / max) * plotHeight;
          const failedHeight = (d.failed / max) * plotHeight;
          return (
            <g key={d.day}>
              <rect x={x} y={plotHeight - succeededHeight} width={barWidth} height={succeededHeight} className="fill-primary" />
              <rect x={x} y={plotHeight - succeededHeight - failedHeight} width={barWidth} height={failedHeight} className="fill-destructive" />
            </g>
          );
        })}
        <line x1={0} x2={CHART_WIDTH} y1={plotHeight} y2={plotHeight} className="stroke-border" />
        <text x={0} y={CHART_HEIGHT - 4} className="fill-muted-foreground text-[11px]">
          {days[0].day}
        </text>
        <text x={CHART_WIDTH} y={CHART_HEIGHT - 4} textAnchor="end" className="fill-muted-foreground text-[11px]">
          {days[days.length - 1].day}
        </text>
      </svg>
      <p className="flex gap-4 text-sm text-muted-foreground" aria-hidden="true">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-primary" /> Succeeded
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-destructive" /> Failed
        </span>
      </p>
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
    </>
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
  const byWorkflow = Object.entries(work.by_workflow).flatMap(([workflow, states]) => Object.entries(states).map(([state, jobs]) => [workflow, state, count(jobs)]));
  return (
    <div className="flex flex-col gap-3">
      <SimpleTable label="Jobs by state" headings={["State", "Jobs"]} rows={Object.entries(work.by_state).map(([state, jobs]) => [state, count(jobs)])} />
      <SimpleTable label="Jobs by workflow and state" headings={["Workflow", "State", "Jobs"]} rows={byWorkflow} />
    </div>
  );
}

function WorkDelegated({ work }: { work: StatsResponse["work_delegated"] }) {
  const days = Object.entries(work.daily).map(([day, counts]) => ({ day, ...counts }));
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
      {days.length > 0 ? (
        <DailyChart days={days} />
      ) : (
        <p className="text-sm text-muted-foreground">{total === 0 ? "No jobs finished in this window." : "No succeeded or failed jobs finished in this window."}</p>
      )}
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
          <WorkDelegated work={stats.work_delegated} />
          <FailoverSaves saves={stats.failover_saves} />
          <Tokens tokens={stats.tokens} />
          <Cost cost={stats.estimated_cost} currency={stats.currency} />
        </>
      )}
    </main>
  );
}
