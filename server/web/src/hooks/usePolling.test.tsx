import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "./usePolling";

const flush = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
};
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
});

describe("usePolling", () => {
  it("treats an empty serialized filter key as a valid polling key", async () => {
    const load = vi.fn().mockResolvedValue("page");
    const hook = renderHook(() => usePolling("", load));
    await flush();
    expect(load).toHaveBeenCalledWith("");
    expect(hook.result.current.value).toBe("page");
    hook.unmount();
  });
  it("reports loading for an empty-string key until the first response", async () => {
    vi.useFakeTimers();
    let resolve!: (v: string) => void;
    const load = vi.fn(
      () =>
        new Promise<string>((r) => {
          resolve = r;
        }),
    );
    const hook = renderHook(() => usePolling("", load));
    expect(hook.result.current.loading).toBe(true);
    await act(async () => resolve("page"));
    expect(hook.result.current.loading).toBe(false);
    hook.unmount();
  });
  it("is not loading for a null key", () => {
    const hook = renderHook(() => usePolling(null, vi.fn()));
    expect(hook.result.current.loading).toBe(false);
  });
  it("stops polling once the value says it is finished and resumes on a key change", async () => {
    vi.useFakeTimers();
    const load = vi.fn(async (key: string) => ({ key, done: key === "b" }));
    const hook = renderHook(({ id }) => usePolling(id, load, 1000, (v) => !v.done), { initialProps: { id: "a" } });
    await flush();
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await flush();
    expect(load).toHaveBeenCalledTimes(2);
    hook.rerender({ id: "b" });
    await flush();
    expect(load).toHaveBeenCalledTimes(3);
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });
    expect(load).toHaveBeenCalledTimes(3);
    expect(hook.result.current.value).toEqual({ key: "b", done: true });
    hook.unmount();
  });
  it("polls every second without overlapping requests and cleans up", async () => {
    vi.useFakeTimers();
    let resolve!: (v: number) => void;
    const load = vi.fn(
      () =>
        new Promise<number>((r) => {
          resolve = r;
        }),
    );
    const { result, unmount } = renderHook(() => usePolling("job", load));
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => resolve(1));
    expect(result.current.value).toBe(1);
    await act(async () => {
      vi.advanceTimersByTime(999);
    });
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(load).toHaveBeenCalledTimes(2);
    unmount();
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    expect(load).toHaveBeenCalledTimes(2);
  });
  it("discards stale selection responses and pauses while hidden", async () => {
    vi.useFakeTimers();
    let resolve!: (v: string) => void;
    const load = vi.fn((key: string) =>
      key === "old"
        ? new Promise<string>((r) => {
            resolve = r;
          })
        : Promise.resolve(key),
    );
    const hook = renderHook(({ id }) => usePolling(id, load), { initialProps: { id: "old" } });
    hook.rerender({ id: "new" });
    await flush();
    expect(hook.result.current.value).toBe("new");
    await act(async () => resolve("old"));
    expect(hook.result.current.value).toBe("new");
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    expect(load.mock.calls.filter((call) => call[0] === "new")).toHaveLength(1);
    hook.unmount();
  });
  it("does not reschedule after an in-flight request rejects after cleanup", async () => {
    vi.useFakeTimers();
    let reject!: (reason: Error) => void;
    const load = vi.fn(
      () =>
        new Promise<string>((_, r) => {
          reject = r;
        }),
    );
    const hook = renderHook(() => usePolling("job", load));
    hook.unmount();
    await act(async () => reject(Error("offline")));
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });
    expect(load).toHaveBeenCalledTimes(1);
  });
  it("keeps prior data visible during a key change while refreshing", async () => {
    vi.useFakeTimers();
    let resolve!: (value: string) => void;
    const load = vi.fn((key: string) =>
      key === "old"
        ? Promise.resolve("old value")
        : new Promise<string>((r) => {
            resolve = r;
          }),
    );
    const hook = renderHook(({ id }) => usePolling(id, load), { initialProps: { id: "old" } });
    await flush();
    expect(hook.result.current.value).toBe("old value");
    hook.rerender({ id: "new" });
    expect(hook.result.current.value).toBe("old value");
    expect(hook.result.current.loading).toBe(true);
    await act(async () => resolve("new value"));
    expect(hook.result.current.value).toBe("new value");
    hook.unmount();
  });
  it("backs off five seconds after an error", async () => {
    vi.useFakeTimers();
    const load = vi.fn().mockRejectedValueOnce(Error("offline")).mockResolvedValue("ok");
    const { result, unmount } = renderHook(() => usePolling("job", load));
    await flush();
    expect(result.current.error).toBeTruthy();
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
});
