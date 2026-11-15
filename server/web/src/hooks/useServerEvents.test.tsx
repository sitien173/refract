import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createQueryWrapper, createTestQueryClient } from "../test/query";
import { type EventSourceLike, useServerEvents } from "./useServerEvents";

class FakeSource implements EventSourceLike {
  static instances: FakeSource[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;
  closed = false;
  constructor(public url: string) {
    FakeSource.instances.push(this);
  }
  close() {
    this.closed = true;
    this.readyState = 2;
  }
  emit(payload: unknown) {
    this.onmessage?.({ data: typeof payload === "string" ? payload : JSON.stringify(payload) });
  }
}

const create = (url: string) => new FakeSource(url);

function setup() {
  const queryClient = createTestQueryClient();
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const hook = renderHook(() => useServerEvents(create), { wrapper: createQueryWrapper(queryClient) });
  return { invalidate, hook, source: () => FakeSource.instances[FakeSource.instances.length - 1] };
}

const keys = (spy: { mock: { calls: unknown[][] } }) => spy.mock.calls.map((call) => (call[0] as { queryKey: unknown[] }).queryKey);

describe("useServerEvents", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeSource.instances = [];
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("subscribes to the dashboard event stream", () => {
    setup();
    expect(FakeSource.instances.map((s) => s.url)).toEqual(["/dashboard/api/events"]);
  });

  it("invalidates the job, job list, and card queries for a job event", () => {
    const { invalidate, source } = setup();
    act(() => source().emit({ job_id: "job-1", kind: "terminal" }));
    expect(keys(invalidate)).toEqual(expect.arrayContaining([["job", "job-1"], ["jobs"], ["cards"], ["card"]]));
    expect(keys(invalidate)).not.toContainEqual(["job", "job-2"]);
  });

  it("refreshes stats and targets when a job reaches a terminal state", () => {
    const { invalidate, source } = setup();
    act(() => source().emit({ job_id: "job-1", kind: "queued" }));
    expect(keys(invalidate)).not.toContainEqual(["stats"]);
    act(() => source().emit({ job_id: "job-1", kind: "terminal" }));
    expect(keys(invalidate)).toEqual(expect.arrayContaining([["stats"], ["targets"]]));
  });

  it("invalidates every job query on a resync frame", () => {
    const { invalidate, source } = setup();
    act(() => source().emit({ job_id: "", kind: "resync" }));
    expect(keys(invalidate)).toEqual(expect.arrayContaining([["job"], ["jobs"], ["cards"], ["card"], ["stats"], ["targets"]]));
  });

  it("ignores frames that are not valid events", () => {
    const { invalidate, source } = setup();
    act(() => source().emit("not json"));
    act(() => source().emit({ job_id: 3 }));
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("reopens a closed stream with backoff and resyncs once it is back", async () => {
    const { invalidate, source } = setup();
    const first = source();
    act(() => {
      first.readyState = 2;
      first.onerror?.();
    });
    expect(first.closed).toBe(true);
    expect(FakeSource.instances).toHaveLength(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(FakeSource.instances).toHaveLength(2);

    invalidate.mockClear();
    act(() => source().onopen?.());
    expect(keys(invalidate)).toContainEqual(["jobs"]);
  });

  it("leaves a connecting stream to the browser's own reconnect", async () => {
    const { source } = setup();
    const first = source();
    act(() => {
      first.readyState = 0;
      first.onerror?.();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(first.closed).toBe(false);
    expect(FakeSource.instances).toHaveLength(1);
  });

  it("does not resync on the first open", () => {
    const { invalidate, source } = setup();
    act(() => source().onopen?.());
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("closes the stream and cancels a pending reconnect on unmount", async () => {
    const { hook, source } = setup();
    const first = source();
    act(() => {
      first.readyState = 2;
      first.onerror?.();
    });
    hook.unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(FakeSource.instances).toHaveLength(1);

    const other = setup();
    const live = other.source();
    other.hook.unmount();
    expect(live.closed).toBe(true);
  });

  it("does nothing where EventSource is unavailable", () => {
    const queryClient = createTestQueryClient();
    renderHook(() => useServerEvents(), { wrapper: createQueryWrapper(queryClient) });
    expect(FakeSource.instances).toHaveLength(0);
  });
});
