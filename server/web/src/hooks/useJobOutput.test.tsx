import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { OutputPage } from "../api";
import { useJobOutput } from "./useJobOutput";
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
afterEach(() => {
  vi.useRealTimers();
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
});
it("polls nonterminal output at about one second and pauses while hidden", async () => {
  vi.useFakeTimers();
  const load = vi.fn().mockResolvedValue(page([], 0, false));
  const hook = renderHook(() => useJobOutput("job", load));
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
  Object.defineProperty(document, "hidden", { configurable: true, value: true });
  await act(async () => {
    vi.advanceTimersByTime(3000);
  });
  expect(load).toHaveBeenCalledTimes(2);
  hook.unmount();
});
it("does not schedule another poll when an in-flight request rejects after unmount", async () => {
  vi.useFakeTimers();
  let reject!: (reason: Error) => void;
  const load = vi.fn(
    () =>
      new Promise<OutputPage>((_, r) => {
        reject = r;
      }),
  );
  const { unmount } = renderHook(() => useJobOutput("job", load));
  unmount();
  await act(async () => reject(Error("offline")));
  await act(async () => {
    vi.advanceTimersByTime(10000);
  });
  expect(load).toHaveBeenCalledTimes(1);
});
it("does not schedule another poll when selection changes before rejection", async () => {
  vi.useFakeTimers();
  let reject!: (reason: Error) => void;
  const load = vi.fn((id: string) =>
    id === "old"
      ? new Promise<OutputPage>((_, r) => {
          reject = r;
        })
      : Promise.resolve(page([], 0, false, true)),
  );
  const hook = renderHook(({ id }) => useJobOutput(id, load), { initialProps: { id: "old" } });
  hook.rerender({ id: "new" });
  await flush();
  await act(async () => reject(Error("offline")));
  await act(async () => {
    vi.advanceTimersByTime(10000);
  });
  expect(load.mock.calls.map(([id]) => id)).toEqual(["old", "new"]);
  hook.unmount();
});
it("drains terminal output pages and stops polling after the final page", async () => {
  vi.useFakeTimers();
  const load = vi
    .fn()
    .mockResolvedValueOnce(page([{ seq: 1 }], 1, true, true))
    .mockResolvedValueOnce(page([{ seq: 2 }], 2, false, true));
  const { result, unmount } = renderHook(() => useJobOutput("job", load));
  await flush();
  expect(result.current.events.map((e) => e.seq)).toEqual([1, 2]);
  await act(async () => {
    vi.advanceTimersByTime(20000);
  });
  expect(load).toHaveBeenCalledTimes(2);
  unmount();
});
it("exposes output availability", async () => {
  vi.useFakeTimers();
  const load = vi.fn().mockResolvedValueOnce({ ...page([], 0, false), available: false, terminal: true });
  const { result } = renderHook(() => useJobOutput("job", load));
  await flush();
  expect(result.current.status?.available).toBe(false);
});
it("exposes output errors and backs off five seconds", async () => {
  vi.useFakeTimers();
  const load = vi
    .fn()
    .mockRejectedValueOnce(Error("output unavailable"))
    .mockResolvedValue(page([], 0, false, true));
  const { result, unmount } = renderHook(() => useJobOutput("job", load));
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
it("keeps every fetched event instead of silently dropping early history", async () => {
  vi.useFakeTimers();
  const batch = (from: number, count: number) => Array.from({ length: count }, (_, i) => ({ seq: from + i }));
  const load = vi
    .fn()
    .mockResolvedValueOnce(page(batch(0, 3000), 3000, true, true))
    .mockResolvedValueOnce(page(batch(3000, 3000), 6000, false, true));
  const { result, unmount } = renderHook(() => useJobOutput("job", load));
  await flush();
  await flush();
  expect(result.current.events).toHaveLength(6000);
  expect(result.current.events[0]).toEqual({ seq: 0 });
  expect(result.current.events[5999]).toEqual({ seq: 5999 });
  unmount();
});
