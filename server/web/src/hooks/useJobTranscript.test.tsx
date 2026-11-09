import { focusManager } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OutputPage } from "../api";
import { deferred } from "../test/async";
import { useJobTranscript } from "./useJobTranscript";

const page = (events: Record<string, unknown>[], next: number, has_more: boolean, terminal = false): OutputPage => ({
  events,
  next,
  has_more,
  available: true,
  state: terminal ? "succeeded" : "running",
  terminal,
});

const flush = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
};

describe("useJobTranscript", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    focusManager.setFocused(true);
  });

  afterEach(() => {
    vi.useRealTimers();
    focusManager.setFocused(undefined);
  });

  it("polls nonterminal output at 1 s intervals", async () => {
    const load = vi.fn().mockResolvedValue(page([], 0, false));
    const hook = renderHook(() => useJobTranscript("job", load));
    await flush();
    expect(load).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(999);
    });
    expect(load).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    await flush();
    expect(load).toHaveBeenCalledTimes(2);

    hook.unmount();
  });

  it("backs off to 5 s polling after an error", async () => {
    const load = vi
      .fn()
      .mockRejectedValueOnce(new Error("output stream unavailable"))
      .mockResolvedValue(page([], 0, false, true));

    const { result, unmount } = renderHook(() => useJobTranscript("job", load));
    await flush();
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.loading).toBe(false);

    await act(async () => {
      vi.advanceTimersByTime(4999);
    });
    expect(load).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    await flush();
    expect(load).toHaveBeenCalledTimes(2);
    unmount();
  });

  it("stops polling once the job is terminal and has_more is false", async () => {
    const load = vi
      .fn()
      .mockResolvedValueOnce(page([{ kind: "future.kind", data: { text: "first" } }], 1, true, true))
      .mockResolvedValueOnce(page([{ kind: "future.kind", data: { text: "second" } }], 2, false, true));

    const { result, unmount } = renderHook(() => useJobTranscript("job", load));
    await flush();
    expect(result.current.rows.map((r) => r.text)).toEqual(["first", "second"]);

    await act(async () => {
      vi.advanceTimersByTime(20000);
    });
    expect(load).toHaveBeenCalledTimes(2);
    unmount();
  });

  it("pauses while hidden through focusManager and triggers an immediate refresh on return", async () => {
    const load = vi.fn().mockResolvedValue(page([], 0, false));
    const hook = renderHook(() => useJobTranscript("job", load));
    await flush();
    expect(load).toHaveBeenCalledTimes(1);

    // Tab is hidden
    act(() => {
      focusManager.setFocused(false);
    });

    await act(async () => {
      vi.advanceTimersByTime(10000);
    });
    // No requests should be made while hidden
    expect(load).toHaveBeenCalledTimes(1);

    // Tab becomes visible / focused again
    await act(async () => {
      focusManager.setFocused(true);
    });
    await flush();
    // Immediate refresh on return
    expect(load).toHaveBeenCalledTimes(2);

    hook.unmount();
  });

  it("does not allow overlapping output fetches", async () => {
    let resolveFirst!: (value: OutputPage) => void;
    const firstPromise = new Promise<OutputPage>((resolve) => {
      resolveFirst = resolve;
    });

    const load = vi
      .fn()
      .mockImplementationOnce(() => firstPromise)
      .mockResolvedValue(page([], 1, false));

    const hook = renderHook(() => useJobTranscript("job", load));
    await flush();
    expect(load).toHaveBeenCalledTimes(1);

    // Advance time while first request is still pending
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    // Should NOT have issued a second concurrent fetch
    expect(load).toHaveBeenCalledTimes(1);

    // Resolve first request
    await act(async () => {
      resolveFirst(page([], 0, false));
    });
    await flush();

    // After 1s, next scheduled poll happens
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await flush();
    expect(load).toHaveBeenCalledTimes(2);

    hook.unmount();
  });

  it("ignores state updates from a late response for a previous job", async () => {
    let resolveOld!: (value: OutputPage) => void;
    const oldPromise = new Promise<OutputPage>((resolve) => {
      resolveOld = resolve;
    });

    const load = vi.fn((id: string) => {
      if (id === "old") return oldPromise;
      return Promise.resolve(page([{ kind: "future.kind", data: { text: "new event" } }], 1, false, true));
    });

    const hook = renderHook(({ id }) => useJobTranscript(id, load), { initialProps: { id: "old" } });
    await flush();
    expect(load).toHaveBeenCalledWith("old", 0, expect.any(AbortSignal));

    // Switch selection to "new"
    hook.rerender({ id: "new" });
    await flush();
    expect(hook.result.current.rows).toEqual([expect.objectContaining({ text: "new event" })]);

    // Late response from "old" arrives
    await act(async () => {
      resolveOld(page([{ kind: "future.kind", data: { text: "stale old event" } }], 1, false, true));
    });
    await flush();

    // The rows must still only be for "new", not contaminated by "old"
    expect(hook.result.current.rows).toEqual([expect.objectContaining({ text: "new event" })]);
    hook.unmount();
  });

  it("keeps a 6000-row transcript across pages and holds no raw event array in state", async () => {
    const batch = (from: number, count: number) =>
      Array.from({ length: count }, (_, i) => ({
        kind: "future.kind",
        data: { text: `event-${from + i}` },
      }));

    const load = vi
      .fn()
      .mockResolvedValueOnce(page(batch(0, 3000), 3000, true, true))
      .mockResolvedValueOnce(page(batch(3000, 3000), 6000, false, true));

    const { result, unmount } = renderHook(() => useJobTranscript("job", load));
    await flush();
    await flush();

    expect(result.current.rows).toHaveLength(6000);
    expect(result.current.rows[0]?.text).toBe("event-0");
    expect(result.current.rows[5999]?.text).toBe("event-5999");

    // Holds no raw event array in status
    expect(result.current.status?.events).toHaveLength(0);
    unmount();
  });

  it("aborts in-flight load request when the job switches", async () => {
    let capturedSignal: AbortSignal | undefined;
    const pending = deferred<OutputPage>();
    const load = vi.fn((id: string, _cursor = 0, signal?: AbortSignal) => {
      if (id === "job1") {
        capturedSignal = signal;
        return pending.promise;
      }
      return Promise.resolve(page([], 0, false, true));
    });

    const { rerender, unmount } = renderHook(({ id }) => useJobTranscript(id, load), {
      initialProps: { id: "job1" },
    });

    await flush();
    expect(load).toHaveBeenCalledWith("job1", 0, expect.any(AbortSignal));
    expect(capturedSignal?.aborted).toBe(false);

    rerender({ id: "job2" });
    await flush();

    expect(capturedSignal?.aborted).toBe(true);
    unmount();
  });

  it("exposes output availability and status", async () => {
    const load = vi.fn().mockResolvedValueOnce({ ...page([], 0, false), available: false, terminal: true });
    const { result, unmount } = renderHook(() => useJobTranscript("job", load));
    await flush();
    expect(result.current.status?.available).toBe(false);
    unmount();
  });
});
