export type JobSummary = {
  id: string;
  state: string;
  project_id: string | null;
  project_root: string | null;
  workflow: string | null;
  profile: string | null;
  target: string | null;
  session: string | null;
  retry_of: string | null;
  failure_kind: string | null;
  created_at: string;
  updated_at: string;
};

export type JobPage = {
  jobs: JobSummary[];
  next_cursor: string | null;
  options: { states: string[]; projects: { id: string; root: string }[]; workflows: string[]; targets: string[] };
};

export type JobDetail = JobSummary & {
  started_at: string | null;
  finished_at: string | null;
  prompt: string;
  result: {
    text: string | null;
    error: string | null;
    failure_kind: string | null;
    model: string | null;
    duration_ms: number | null;
    tokens: Record<string, number | null>;
  };
  pending_question: { question_id: string; text: string } | null;
};

export type OutputPage = {
  events: Record<string, unknown>[];
  next: number;
  has_more: boolean;
  available: boolean;
  state: string;
  terminal: boolean;
};

export type TargetView = {
  id: string;
  model: string;
  backend: string;
  isolated: boolean;
  read_only: boolean;
  max_concurrency: number;
  active: number;
  healthy: boolean;
  circuit_open_until: string;
  breaker_state: "closed" | "open" | "half_open";
  cooldown_s: number;
  probing: boolean;
};

export type ConfigHealth = {
  attempted_at: string;
  successful_at: string;
  source_path: string;
  modification_time: string;
  revision: string;
  valid: boolean;
  latest_error: string;
  last_known_good_revision: string;
};

/** Job states after which a job never changes again (mirrors TERMINAL_STATES on the server). */
export const TERMINAL_JOB_STATES: ReadonlySet<string> = new Set(["succeeded", "failed", "cancelled", "interrupted"]);

export const isTerminalJobState = (state: string | null | undefined): boolean =>
  state != null && TERMINAL_JOB_STATES.has(state);

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

async function request<T>(url: string, init: RequestInit = {}, fetcher: typeof fetch = fetch): Promise<T> {
  const response = await fetcher(url, { ...init, cache: "no-store" });
  let data: ({ error?: string; code?: string } & T) | null = null;
  try {
    data = (await response.json()) as { error?: string; code?: string } & T;
  } catch {
    /* non-JSON error body */
  }
  if (!response.ok) {
    throw new DashboardApiError(data?.error || `Dashboard request failed (${response.status})`, response.status, data?.code || "http_error");
  }
  if (data === null) {
    throw new DashboardApiError("Dashboard returned an invalid response", response.status, "invalid_response");
  }
  return data;
}

export function getJobs(filters: Record<string, string | undefined> = {}, fetcher: typeof fetch = fetch): Promise<JobPage> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) query.set(key, value);
  }
  return request(`${base}/jobs${query.size ? `?${query}` : ""}`, {}, fetcher);
}

export function getJob(id: string, fetcher: typeof fetch = fetch): Promise<JobDetail> {
  return request(`${base}/jobs/${encodeURIComponent(id)}`, {}, fetcher);
}

export function getJobOutput(id: string, after = 0, fetcher: typeof fetch = fetch): Promise<OutputPage> {
  return request(`${base}/jobs/${encodeURIComponent(id)}/output?after=${after}`, {}, fetcher);
}

export function getTargets(fetcher: typeof fetch = fetch): Promise<{ targets: TargetView[]; config: ConfigHealth }> {
  return request(`${base}/targets`, {}, fetcher);
}

export function postJobAction(
  id: string,
  action: "cancel" | "retry" | "answer",
  body: unknown = {},
  fetcher: typeof fetch = fetch,
): Promise<Record<string, unknown>> {
  return request(
    `${base}/jobs/${encodeURIComponent(id)}/${action}`,
    {
      method: "POST",
      headers: { "X-Refract-Dashboard": "1", "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    fetcher,
  );
}
