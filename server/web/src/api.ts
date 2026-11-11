import { z } from "zod";

export const JobSummarySchema = z.object({
  id: z.string(),
  state: z.string(),
  project_id: z.string().nullable(),
  project_root: z.string().nullable(),
  workflow: z.string().nullable(),
  profile: z.string().nullable(),
  target: z.string().nullable(),
  session: z.string().nullable(),
  retry_of: z.string().nullable(),
  failure_kind: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type JobSummary = z.infer<typeof JobSummarySchema>;

export const JobOptionsSchema = z.object({
  states: z.array(z.string()),
  projects: z.array(z.object({ id: z.string(), root: z.string() })),
  workflows: z.array(z.string()),
  targets: z.array(z.string()),
});
export type JobOptions = z.infer<typeof JobOptionsSchema>;

export const JobPageSchema = z.object({
  jobs: z.array(JobSummarySchema),
  next_cursor: z.string().nullable(),
  options: JobOptionsSchema,
});
export type JobPage = z.infer<typeof JobPageSchema>;

export const JobResultSchema = z.object({
  text: z.string().nullable(),
  error: z.string().nullable(),
  failure_kind: z.string().nullable(),
  model: z.string().nullable(),
  duration_ms: z.number().nullable(),
  tokens: z.record(z.string(), z.number().nullable()),
});
export type JobResult = z.infer<typeof JobResultSchema>;

export const PendingQuestionSchema = z.object({
  question_id: z.string(),
  text: z.string(),
});
export type PendingQuestion = z.infer<typeof PendingQuestionSchema>;

export const JobDetailSchema = JobSummarySchema.extend({
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  prompt: z.string(),
  result: JobResultSchema,
  pending_question: PendingQuestionSchema.nullable(),
});
export type JobDetail = z.infer<typeof JobDetailSchema>;

export const OutputPageSchema = z.object({
  events: z.array(z.record(z.string(), z.unknown())),
  next: z.number(),
  has_more: z.boolean(),
  available: z.boolean(),
  state: z.string(),
  terminal: z.boolean(),
});
export type OutputPage = z.infer<typeof OutputPageSchema>;

export const TargetViewSchema = z.object({
  id: z.string(),
  model: z.string(),
  backend: z.string(),
  isolated: z.boolean(),
  read_only: z.boolean(),
  max_concurrency: z.number(),
  active: z.number(),
  healthy: z.boolean(),
  circuit_open_until: z.string(),
  breaker_state: z.string(),
  cooldown_s: z.number(),
  probing: z.boolean(),
});
export type TargetView = z.infer<typeof TargetViewSchema>;

export const ConfigHealthSchema = z.object({
  attempted_at: z.string(),
  successful_at: z.string(),
  source_path: z.string(),
  modification_time: z.string(),
  revision: z.string(),
  valid: z.boolean(),
  latest_error: z.string(),
  last_known_good_revision: z.string(),
});
export type ConfigHealth = z.infer<typeof ConfigHealthSchema>;

export const TargetsResponseSchema = z.object({
  targets: z.array(TargetViewSchema),
  config: ConfigHealthSchema,
});
export type TargetsResponse = z.infer<typeof TargetsResponseSchema>;

export const JobActionResponseSchema = z.object({
  job_id: z.string(),
  state: z.string(),
  success: z.boolean().optional(),
  retry_of: z.string().optional(),
});
export type JobActionResponse = z.infer<typeof JobActionResponseSchema>;

export const CARD_STATES = ["todo", "in_progress", "in_review", "done", "cancelled"] as const;
export const CardStateSchema = z.enum(CARD_STATES);
export type CardState = z.infer<typeof CardStateSchema>;

export const CardSummarySchema = z.object({
  id: z.string(),
  project_id: z.string(),
  project_root: z.string(),
  title: z.string(),
  state: CardStateSchema,
  job_ids: z.array(z.string()),
  created_at: z.string(),
  updated_at: z.string(),
});
export type CardSummary = z.infer<typeof CardSummarySchema>;

export const CardOptionsSchema = z.object({
  projects: z.array(z.object({ id: z.string(), root: z.string() })),
});
export type CardOptions = z.infer<typeof CardOptionsSchema>;

export const CardsResponseSchema = z.object({
  cards: z.array(CardSummarySchema),
  truncated: z.boolean(),
  options: CardOptionsSchema,
});
export type CardsResponse = z.infer<typeof CardsResponseSchema>;

export const CardMoveSchema = z.object({
  from_state: CardStateSchema.nullable(),
  to_state: CardStateSchema,
  note: z.string(),
  at: z.string(),
});
export type CardMove = z.infer<typeof CardMoveSchema>;

export const CardJobSchema = z.object({
  id: z.string(),
  workflow: z.string().nullable(),
  state: z.string().nullable(),
  target: z.string().nullable(),
  available: z.boolean(),
});
export type CardJob = z.infer<typeof CardJobSchema>;

export const CardDetailCardSchema = CardSummarySchema.extend({
  body: z.string(),
});
export type CardDetailCard = z.infer<typeof CardDetailCardSchema>;

export const CardDetailResponseSchema = z.object({
  card: CardDetailCardSchema,
  moves: z.array(CardMoveSchema),
  jobs: z.array(CardJobSchema),
});
export type CardDetailResponse = z.infer<typeof CardDetailResponseSchema>;

const TokenTotalsSchema = z.object({
  input: z.number(),
  uncached_input: z.number(),
  output: z.number(),
  cache_read: z.number(),
  cache_write: z.number(),
  jobs: z.number(),
  cache_hit_ratio: z.number(),
});
export type TokenTotals = z.infer<typeof TokenTotalsSchema>;

export const StatsResponseSchema = z.object({
  days: z.number(),
  currency: z.string(),
  work_delegated: z.object({
    by_workflow: z.record(z.string(), z.record(z.string(), z.number())),
    by_state: z.record(z.string(), z.number()),
    breakdown: z.array(
      z.object({
        profile: z.string(),
        workflow: z.string(),
        target: z.string(),
        state: z.string(),
        jobs: z.number(),
      }),
    ),
    worker_hours: z.number(),
    success_rate: z.number(),
    daily: z.record(z.string(), z.object({ succeeded: z.number(), failed: z.number() })),
  }),
  failover_saves: z.object({
    skipped_targets: z.number(),
    retries: z.number(),
    retries_after_failure: z.number(),
    unknown_skipped_targets: z.number(),
    unknown_attempts: z.number(),
  }),
  tokens: z.object({
    by_backend: z.record(z.string(), TokenTotalsSchema),
    by_model: z.record(z.string(), TokenTotalsSchema),
    by_target: z.record(z.string(), TokenTotalsSchema),
  }),
  estimated_cost: z.object({
    total: z.number(),
    by_model: z.record(z.string(), z.number()),
    unpriced_models: z.array(z.string()),
  }),
});
export const STATS_DAYS = [1, 7, 30, 365] as const;
export type StatsDays = (typeof STATS_DAYS)[number];

export type StatsResponse = z.infer<typeof StatsResponseSchema>;

/** Job states after which a job never changes again (mirrors TERMINAL_STATES on the server). */
export const TERMINAL_JOB_STATES: ReadonlySet<string> = new Set(["succeeded", "failed", "cancelled", "interrupted"]);

export const isTerminalJobState = (state: string | null | undefined): boolean => state != null && TERMINAL_JOB_STATES.has(state);

export class DashboardApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
  ) {
    super(message);
    this.name = "DashboardApiError";
  }
}

const base = "/dashboard/api";

function resolveRequestOptions(
  fetcherOrSignal?: typeof fetch | AbortSignal | { signal?: AbortSignal; fetcher?: typeof fetch },
  maybeSignal?: AbortSignal,
): { fetcher: typeof fetch; signal?: AbortSignal } {
  if (typeof fetcherOrSignal === "function") {
    return { fetcher: fetcherOrSignal, signal: maybeSignal };
  }
  if (fetcherOrSignal && typeof fetcherOrSignal === "object") {
    if ("aborted" in fetcherOrSignal) {
      return { fetcher: fetch, signal: fetcherOrSignal as AbortSignal };
    }
    return {
      fetcher: fetcherOrSignal.fetcher ?? fetch,
      signal: fetcherOrSignal.signal ?? maybeSignal,
    };
  }
  return { fetcher: fetch, signal: maybeSignal };
}

async function request<T>(schema: z.ZodType<T>, url: string, init: RequestInit = {}, fetcher: typeof fetch = fetch): Promise<T> {
  const response = await fetcher(url, { ...init, cache: "no-store" });
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    /* non-JSON error body */
  }
  if (!response.ok) {
    const errorData = data && typeof data === "object" ? (data as { error?: string; code?: string }) : null;
    throw new DashboardApiError(errorData?.error || `Dashboard request failed (${response.status})`, response.status, errorData?.code || "http_error");
  }
  if (data === null || typeof data !== "object") {
    throw new DashboardApiError("Dashboard returned an invalid response", response.status, "invalid_response");
  }
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    throw new DashboardApiError("Dashboard returned an invalid response", response.status, "invalid_response");
  }
  return parsed.data;
}

export function getJobs(
  filters: Record<string, string | undefined> = {},
  fetcherOrSignal?: typeof fetch | AbortSignal | { signal?: AbortSignal; fetcher?: typeof fetch },
  maybeSignal?: AbortSignal,
): Promise<JobPage> {
  const { fetcher, signal } = resolveRequestOptions(fetcherOrSignal, maybeSignal);
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) query.set(key, value);
  }
  return request(JobPageSchema, `${base}/jobs${query.size ? `?${query}` : ""}`, { signal }, fetcher);
}

export function getJob(id: string, fetcherOrSignal?: typeof fetch | AbortSignal | { signal?: AbortSignal; fetcher?: typeof fetch }, maybeSignal?: AbortSignal): Promise<JobDetail> {
  const { fetcher, signal } = resolveRequestOptions(fetcherOrSignal, maybeSignal);
  return request(JobDetailSchema, `${base}/jobs/${encodeURIComponent(id)}`, { signal }, fetcher);
}

export function getJobOutput(
  id: string,
  after = 0,
  fetcherOrSignal?: typeof fetch | AbortSignal | { signal?: AbortSignal; fetcher?: typeof fetch },
  maybeSignal?: AbortSignal,
): Promise<OutputPage> {
  const { fetcher, signal } = resolveRequestOptions(fetcherOrSignal, maybeSignal);
  return request(OutputPageSchema, `${base}/jobs/${encodeURIComponent(id)}/output?after=${after}`, { signal }, fetcher);
}

export function getTargets(fetcherOrSignal?: typeof fetch | AbortSignal | { signal?: AbortSignal; fetcher?: typeof fetch }, maybeSignal?: AbortSignal): Promise<TargetsResponse> {
  const { fetcher, signal } = resolveRequestOptions(fetcherOrSignal, maybeSignal);
  return request(TargetsResponseSchema, `${base}/targets`, { signal }, fetcher);
}

/** `tzOffsetMinutes` is the UTC offset in minutes, east positive; `-new Date().getTimezoneOffset()` in a browser. */
export function getStats(
  days: StatsDays,
  tzOffsetMinutes: number,
  fetcherOrSignal?: typeof fetch | AbortSignal | { signal?: AbortSignal; fetcher?: typeof fetch },
  maybeSignal?: AbortSignal,
): Promise<StatsResponse> {
  const { fetcher, signal } = resolveRequestOptions(fetcherOrSignal, maybeSignal);
  return request(StatsResponseSchema, `${base}/stats?days=${days}&tz_offset_minutes=${tzOffsetMinutes}`, { signal }, fetcher);
}

export function postJobAction(
  id: string,
  action: "cancel" | "retry" | "answer",
  body: unknown = {},
  fetcherOrSignal?: typeof fetch | AbortSignal | { signal?: AbortSignal; fetcher?: typeof fetch },
  maybeSignal?: AbortSignal,
): Promise<JobActionResponse> {
  const { fetcher, signal } = resolveRequestOptions(fetcherOrSignal, maybeSignal);
  return request(
    JobActionResponseSchema,
    `${base}/jobs/${encodeURIComponent(id)}/${action}`,
    {
      method: "POST",
      headers: { "X-Refract-Dashboard": "1", "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
      signal,
    },
    fetcher,
  );
}

export function getCards(
  project?: string,
  fetcherOrSignal?: typeof fetch | AbortSignal | { signal?: AbortSignal; fetcher?: typeof fetch },
  maybeSignal?: AbortSignal,
): Promise<CardsResponse> {
  const { fetcher, signal } = resolveRequestOptions(fetcherOrSignal, maybeSignal);
  const query = project ? `?project=${encodeURIComponent(project)}` : "";
  return request(CardsResponseSchema, `${base}/cards${query}`, { signal }, fetcher);
}

export function getCard(
  id: string,
  fetcherOrSignal?: typeof fetch | AbortSignal | { signal?: AbortSignal; fetcher?: typeof fetch },
  maybeSignal?: AbortSignal,
): Promise<CardDetailResponse> {
  const { fetcher, signal } = resolveRequestOptions(fetcherOrSignal, maybeSignal);
  return request(CardDetailResponseSchema, `${base}/cards/${encodeURIComponent(id)}`, { signal }, fetcher);
}
