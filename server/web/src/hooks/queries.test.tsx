import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardApiError, type JobDetail, type TargetsResponse } from "../api";
import { createQueryWrapper, createTestQueryClient } from "../test/query";
import { useBoardCards, useCardDetail, useJobDetail, useTargets } from "./queries";

const sampleDetail = (id: string, state = "running"): JobDetail => ({
  id,
  state,
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
  started_at: "2026-11-07T00:00:00Z",
  finished_at: null,
  prompt: "run job",
  result: {
    text: null,
    error: null,
    failure_kind: null,
    model: null,
    duration_ms: null,
    tokens: {},
  },
  pending_question: null,
});

describe("queries hook", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("polls job detail at 1 s intervals while running", async () => {
    const queryClient = createTestQueryClient();
    const load = vi.fn().mockImplementation((id: string) => Promise.resolve(sampleDetail(id, "running")));

    renderHook(() => useJobDetail("job-1", { load }), {
      wrapper: createQueryWrapper(queryClient),
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(load).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(load).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("backs off to 5 s after an error", async () => {
    const queryClient = createTestQueryClient();
    let fail = true;
    const load = vi.fn().mockImplementation((id: string) => {
      if (fail) return Promise.reject(new DashboardApiError("Network failure", 500, "network_error"));
      return Promise.resolve(sampleDetail(id, "running"));
    });

    renderHook(() => useJobDetail("job-1", { load }), {
      wrapper: createQueryWrapper(queryClient),
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(load).toHaveBeenCalledTimes(1);

    // After 1 s, it should not have retried yet due to 5 s backoff
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(load).toHaveBeenCalledTimes(1);

    // At 5 s, it should refetch
    fail = false;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("stops polling once the job is terminal", async () => {
    const queryClient = createTestQueryClient();
    const load = vi.fn().mockImplementation((id: string) => Promise.resolve(sampleDetail(id, "succeeded")));

    renderHook(() => useJobDetail("job-1", { load }), {
      wrapper: createQueryWrapper(queryClient),
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(load).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("clears selection on 404", async () => {
    const queryClient = createTestQueryClient();
    const onNotFound = vi.fn();
    const load = vi.fn().mockRejectedValue(new DashboardApiError("Job not found", 404, "unknown_job"));

    renderHook(() => useJobDetail("missing-job", { load, onNotFound }), {
      wrapper: createQueryWrapper(queryClient),
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(onNotFound).toHaveBeenCalledTimes(1);
  });

  it("fetches targets via useTargets", async () => {
    const queryClient = createTestQueryClient();
    const targetsData: TargetsResponse = {
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
    };
    const load = vi.fn().mockResolvedValue(targetsData);

    const hook = renderHook(() => useTargets({ load }), {
      wrapper: createQueryWrapper(queryClient),
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(hook.result.current.data).toEqual(targetsData);
  });

  it("polls board cards at 1 s intervals and switches to 5 s after an error", async () => {
    const queryClient = createTestQueryClient();
    let fail = false;
    const cardsData = { cards: [], truncated: false, options: { projects: [] } };
    const load = vi.fn().mockImplementation(() => {
      if (fail) return Promise.reject(new DashboardApiError("Network failure", 500, "network_error"));
      return Promise.resolve(cardsData);
    });

    renderHook(() => useBoardCards("p1", { load, enabled: true }), {
      wrapper: createQueryWrapper(queryClient),
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(load).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(load).toHaveBeenCalledTimes(2);

    // Error on next poll
    fail = true;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(load).toHaveBeenCalledTimes(3);

    // 1 s after error, should not poll because interval is 5 s
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(load).toHaveBeenCalledTimes(3);

    // 5 s total after error, should refetch
    fail = false;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(load).toHaveBeenCalledTimes(4);
  });

  it("makes no request for useCardDetail with null id", async () => {
    const queryClient = createTestQueryClient();
    const load = vi.fn().mockResolvedValue({ card: {}, moves: [], jobs: [] });

    renderHook(() => useCardDetail(null, { load }), {
      wrapper: createQueryWrapper(queryClient),
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(load).not.toHaveBeenCalled();
  });

  it("clears card selection on 404 for useCardDetail", async () => {
    const queryClient = createTestQueryClient();
    const onNotFound = vi.fn();
    const load = vi.fn().mockRejectedValue(new DashboardApiError("Card not found", 404, "unknown_card"));

    renderHook(() => useCardDetail("missing-card", { load, onNotFound }), {
      wrapper: createQueryWrapper(queryClient),
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(onNotFound).toHaveBeenCalledTimes(1);
  });
});
