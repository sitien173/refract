import { describe, expect, it, vi } from "vitest";
import { CardDetailResponseSchema, CardStateSchema, CardsResponseSchema, DashboardApiError, getJob, getJobOutput, getJobs, getTargets, postJobAction } from "./api";

function response(status: number, body: unknown, json = vi.fn().mockResolvedValue(body)) {
  return { ok: status >= 200 && status < 300, status, json } as unknown as Response;
}

const sampleJobSummary = {
  id: "job-1",
  state: "running",
  project_id: null,
  project_root: null,
  workflow: null,
  profile: null,
  target: null,
  session: null,
  retry_of: null,
  failure_kind: null,
  created_at: "2026-11-07T00:00:00Z",
  updated_at: "2026-11-07T00:00:00Z",
};

const sampleJobDetail = {
  ...sampleJobSummary,
  started_at: null,
  finished_at: null,
  prompt: "test prompt",
  result: {
    text: null,
    error: null,
    failure_kind: null,
    model: null,
    duration_ms: null,
    tokens: {},
  },
  pending_question: null,
};

describe("dashboard API", () => {
  it("uses encoded identifiers and no-store cache", async () => {
    const fetcher = vi.fn().mockResolvedValue(response(200, { jobs: [sampleJobSummary], next_cursor: null, options: { states: [], projects: [], workflows: [], targets: [] } }));
    await getJobs({ state: "running" }, fetcher as typeof fetch);
    expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("state=running"), expect.objectContaining({ cache: "no-store" }));
    fetcher.mockClear();
    fetcher.mockResolvedValue(response(200, sampleJobDetail));
    await getJob("a/b?c", fetcher as typeof fetch);
    expect(fetcher.mock.calls[0][0]).toBe("/dashboard/api/jobs/a%2Fb%3Fc");
    expect(fetcher.mock.calls[0][1]).toMatchObject({ cache: "no-store" });
  });

  it("posts answer JSON with question_id and answer and CSRF headers", async () => {
    const fetcher = vi.fn().mockResolvedValue(response(200, { job_id: "j1", state: "running", success: true }));
    await postJobAction("j1", "answer", { question_id: "q1", answer: "yes" }, fetcher as typeof fetch);
    expect(fetcher.mock.calls[0][1]).toMatchObject({
      method: "POST",
      headers: { "X-Refract-Dashboard": "1", "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: "q1", answer: "yes" }),
      cache: "no-store",
    });
  });

  it("preserves status and error code for JSON errors including 409", async () => {
    for (const [status, code] of [
      [400, "bad_request"],
      [409, "invalid_state"],
    ] as const) {
      const fetcher = vi.fn().mockResolvedValue(response(status, { error: "Request failed", code }));
      try {
        await postJobAction("j1", "answer", {}, fetcher as typeof fetch);
        throw Error("expected rejection");
      } catch (error) {
        expect(error).toMatchObject({ status, code });
      }
    }
  });

  it("handles non-JSON error bodies without losing HTTP status", async () => {
    const fetcher = vi.fn().mockResolvedValue(response(502, null, vi.fn().mockRejectedValue(Error("Unexpected token"))));
    try {
      await getJobs({}, fetcher as typeof fetch);
      throw Error("expected rejection");
    } catch (error) {
      expect(error).toMatchObject({ status: 502 });
      expect(error).toBeInstanceOf(Error);
    }
  });

  it("throws DashboardApiError with invalid_response when payload fails schema validation", async () => {
    const fetcher = vi.fn().mockResolvedValue(response(200, { invalid_field: "unexpected" }));
    try {
      await getJob("job-1", fetcher as typeof fetch);
      throw new Error("expected rejection");
    } catch (error) {
      expect(error).toBeInstanceOf(DashboardApiError);
      expect(error).toMatchObject({ status: 200, code: "invalid_response" });
    }
  });

  it("passes AbortSignal to fetch across all API calls", async () => {
    const controller = new AbortController();
    const signal = controller.signal;

    const fetcher = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/output")) {
        return Promise.resolve(response(200, { events: [], next: 0, has_more: false, available: true, state: "running", terminal: false }));
      }
      if (url.includes("/targets")) {
        return Promise.resolve(
          response(200, {
            targets: [],
            config: {
              attempted_at: "",
              successful_at: "",
              source_path: "",
              modification_time: "",
              revision: "",
              valid: true,
              latest_error: "",
              last_known_good_revision: "",
            },
          }),
        );
      }
      if (url.includes("/jobs/") && url.includes("/cancel")) {
        return Promise.resolve(response(200, { job_id: "j1", state: "cancelled", success: true }));
      }
      if (url.includes("/jobs/")) {
        return Promise.resolve(response(200, sampleJobDetail));
      }
      return Promise.resolve(response(200, { jobs: [], next_cursor: null, options: { states: [], projects: [], workflows: [], targets: [] } }));
    });

    await getJobs({}, fetcher as typeof fetch, signal);
    expect(fetcher).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ signal }));

    await getJob("j1", fetcher as typeof fetch, signal);
    expect(fetcher).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ signal }));

    await getJobOutput("j1", 0, fetcher as typeof fetch, signal);
    expect(fetcher).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ signal }));

    await getTargets(fetcher as typeof fetch, signal);
    expect(fetcher).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ signal }));

    await postJobAction("j1", "cancel", {}, fetcher as typeof fetch, signal);
    expect(fetcher).toHaveBeenLastCalledWith(expect.any(String), expect.objectContaining({ signal }));
  });

  it("accepts lenient schemas: extra fields, unknown breaker_state, and record event payloads", async () => {
    const fetcher = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/output")) {
        return Promise.resolve(
          response(200, {
            events: [{ kind: "custom", seq: 1, extra_nested: { foo: "bar" } }],
            next: 1,
            has_more: false,
            available: true,
            state: "running",
            terminal: false,
            extra_output_field: "ignored",
          }),
        );
      }
      if (url.includes("/targets")) {
        return Promise.resolve(
          response(200, {
            targets: [
              {
                id: "t1",
                model: "m1",
                backend: "b1",
                isolated: false,
                read_only: false,
                max_concurrency: 1,
                active: 0,
                healthy: true,
                circuit_open_until: "",
                breaker_state: "custom_unknown_breaker_state",
                cooldown_s: 0,
                probing: false,
                extra_target_info: 42,
              },
            ],
            config: {
              attempted_at: "",
              successful_at: "",
              source_path: "",
              modification_time: "",
              revision: "",
              valid: true,
              latest_error: "",
              last_known_good_revision: "",
            },
          }),
        );
      }
      return Promise.resolve(response(200, {}));
    });

    const output = await getJobOutput("j1", 0, fetcher as typeof fetch);
    expect(output.events[0]).toMatchObject({ kind: "custom", seq: 1 });

    const targets = await getTargets(fetcher as typeof fetch);
    expect(targets.targets[0]?.breaker_state).toBe("custom_unknown_breaker_state");
  });

  it("validates card list and detail schemas", () => {
    const validCard = {
      id: "card-1",
      project_id: "p1",
      project_root: "/path/to/p1",
      title: "Card 1",
      state: "todo",
      job_ids: ["job-1"],
      created_at: "2026-11-08T00:00:00Z",
      updated_at: "2026-11-08T00:00:00Z",
    };
    const validList = {
      cards: [validCard, { ...validCard, id: "card-2", state: "in_review" }, { ...validCard, id: "card-3", state: "done" }, { ...validCard, id: "card-4", state: "cancelled" }],
      truncated: false,
      options: { projects: [{ id: "p1", root: "/path/to/p1" }] },
    };
    expect(CardsResponseSchema.safeParse(validList).success).toBe(true);

    const validDetail = {
      card: { ...validCard, body: "Detailed description" },
      moves: [
        { from_state: null, to_state: "todo", note: "Created", at: "2026-11-08T00:00:00Z" },
        { from_state: "todo", to_state: "in_progress", note: "Started", at: "2026-11-08T01:00:00Z" },
      ],
      jobs: [
        { id: "job-1", workflow: "build", state: "succeeded", target: "local", available: true },
        { id: "job-pruned", workflow: null, state: null, target: null, available: false },
      ],
    };
    expect(CardDetailResponseSchema.safeParse(validDetail).success).toBe(true);

    // Rejects a card without state
    const { state: _, ...withoutState } = validCard;
    expect(CardsResponseSchema.safeParse({ ...validList, cards: [withoutState] }).success).toBe(false);

    // Rejects a state outside the five values
    expect(CardStateSchema.safeParse("unknown_state").success).toBe(false);
    expect(CardsResponseSchema.safeParse({ ...validList, cards: [{ ...validCard, state: "unknown_state" }] }).success).toBe(false);
  });
});
