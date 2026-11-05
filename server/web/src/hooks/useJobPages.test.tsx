import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { JobPage, JobSummary } from "../api";
import { useJobPages } from "./useJobPages";

const options = { states: [], projects: [], workflows: [], targets: [] };
const job = (id: string) => ({ id, state: "queued" }) as JobSummary;
const page = (ids: string[], next_cursor: string | null = null): JobPage => ({ jobs: ids.map(job), next_cursor, options });
const ids = (jobs: JobSummary[]) => jobs.map((j) => j.id);
const flush = async () => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
};
const tick = async (ms: number) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
};
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

afterEach(() => {
  vi.useRealTimers();
});

it("appends a cursor page after a nonempty first page", async () => {
  vi.useFakeTimers();
  const load = vi.fn(async (f: Record<string, string | undefined>) => (f.cursor ? page(["c", "d"]) : page(["a", "b"], "c1")));
  const hook = renderHook(() => useJobPages({}, load));
  await flush();
  expect(ids(hook.result.current.jobs)).toEqual(["a", "b"]);
  expect(hook.result.current.nextCursor).toBe("c1");
  await act(async () => {
    await hook.result.current.loadMore();
  });
  expect(load).toHaveBeenLastCalledWith({ cursor: "c1" });
  expect(ids(hook.result.current.jobs)).toEqual(["a", "b", "c", "d"]);
  expect(hook.result.current.nextCursor).toBeNull();
  hook.unmount();
});

it("discards a stale load-more response after the filters change", async () => {
  vi.useFakeTimers();
  const more = deferred<JobPage>();
  const load = vi.fn((f: Record<string, string | undefined>) => {
    if (f.cursor) return more.promise;
    return Promise.resolve(f.state === "failed" ? page(["f1"], "f-cursor") : page(["a"], "c1"));
  });
  const hook = renderHook(({ filters }) => useJobPages(filters, load), { initialProps: { filters: {} as Record<string, string> } });
  await flush();
  let pending!: Promise<void>;
  act(() => {
    pending = hook.result.current.loadMore();
  });
  expect(hook.result.current.loadingMore).toBe(true);
  hook.rerender({ filters: { state: "failed" } });
  await flush();
  expect(ids(hook.result.current.jobs)).toEqual(["f1"]);
  expect(hook.result.current.loadingMore).toBe(false);
  await act(async () => {
    more.resolve(page(["stale"], "stale-cursor"));
    await pending;
  });
  expect(ids(hook.result.current.jobs)).toEqual(["f1"]);
  expect(hook.result.current.nextCursor).toBe("f-cursor");
  expect(hook.result.current.loadingMore).toBe(false);
  hook.unmount();
});

it("discards a stale load-more failure and its finalizer after the filters change", async () => {
  vi.useFakeTimers();
  const more = deferred<JobPage>();
  const second = deferred<JobPage>();
  const load = vi.fn((f: Record<string, string | undefined>) => {
    if (f.cursor === "c1") return more.promise;
    if (f.cursor === "f-cursor") return second.promise;
    return Promise.resolve(f.state === "failed" ? page(["f1"], "f-cursor") : page(["a"], "c1"));
  });
  const hook = renderHook(({ filters }) => useJobPages(filters, load), { initialProps: { filters: {} as Record<string, string> } });
  await flush();
  let stale!: Promise<void>;
  act(() => {
    stale = hook.result.current.loadMore();
  });
  hook.rerender({ filters: { state: "failed" } });
  await flush();
  let current!: Promise<void>;
  act(() => {
    current = hook.result.current.loadMore();
  });
  expect(hook.result.current.loadingMore).toBe(true);
  await act(async () => {
    more.reject(Error("stale failure"));
    await stale;
  });
  expect(hook.result.current.loadMoreError).toBeNull();
  expect(hook.result.current.loadingMore).toBe(true);
  await act(async () => {
    second.resolve(page(["f2"]));
    await current;
  });
  expect(ids(hook.result.current.jobs)).toEqual(["f1", "f2"]);
  expect(hook.result.current.loadingMore).toBe(false);
  hook.unmount();
});

it("reports a load-more failure for the current filters", async () => {
  vi.useFakeTimers();
  const load = vi.fn((f: Record<string, string | undefined>) => (f.cursor ? Promise.reject(Error("page offline")) : Promise.resolve(page(["a"], "c1"))));
  const hook = renderHook(() => useJobPages({}, load));
  await flush();
  await act(async () => {
    await hook.result.current.loadMore();
  });
  expect(hook.result.current.loadMoreError).toBe("page offline");
  expect(hook.result.current.loadingMore).toBe(false);
  expect(ids(hook.result.current.jobs)).toEqual(["a"]);
  hook.unmount();
});

it("ignores a second load-more while one is in flight", async () => {
  vi.useFakeTimers();
  const more = deferred<JobPage>();
  const load = vi.fn((f: Record<string, string | undefined>) => (f.cursor ? more.promise : Promise.resolve(page(["a"], "c1"))));
  const hook = renderHook(() => useJobPages({}, load));
  await flush();
  act(() => {
    void hook.result.current.loadMore();
    void hook.result.current.loadMore();
  });
  expect(load.mock.calls.filter(([f]) => f.cursor)).toHaveLength(1);
  await act(async () => more.resolve(page(["b"])));
  hook.unmount();
});

it("deduplicates jobs that move from a later page into the refreshed first page", async () => {
  vi.useFakeTimers();
  let firstPage = page(["a", "b"], "c1");
  const load = vi.fn(async (f: Record<string, string | undefined>) => (f.cursor === "c1" ? page(["c", "d"]) : firstPage));
  const hook = renderHook(() => useJobPages({}, load));
  await flush();
  await act(async () => {
    await hook.result.current.loadMore();
  });
  firstPage = page(["c", "a"], "c1");
  await tick(1000);
  expect(ids(hook.result.current.jobs)).toEqual(["c", "a", "d"]);
  hook.unmount();
});

it("revalidates loaded pages when the live first page shifts so no job is lost or duplicated", async () => {
  vi.useFakeTimers();
  let firstPage = page(["a", "b"], "c1");
  const load = vi.fn(async (f: Record<string, string | undefined>) => {
    if (f.cursor === "c1") return page(["c", "d"]);
    if (f.cursor === "c2") return page(["b", "c", "d"]);
    return firstPage;
  });
  const hook = renderHook(() => useJobPages({}, load));
  await flush();
  await act(async () => {
    await hook.result.current.loadMore();
  });
  firstPage = page(["x", "a"], "c2");
  await tick(1000);
  await flush();
  expect(load).toHaveBeenCalledWith({ cursor: "c2" });
  expect(ids(hook.result.current.jobs)).toEqual(["x", "a", "b", "c", "d"]);
  expect(hook.result.current.loadingMore).toBe(false);
  hook.unmount();
});

const withState = (id: string, state: string) => ({ id, state }) as JobSummary;
const stateOf = (jobs: JobSummary[], id: string) => jobs.find((j) => j.id === id)?.state;

it("refreshes a later-page job when the first-page cursor has not moved", async () => {
  vi.useFakeTimers();
  let second = [withState("c", "running"), withState("d", "queued")];
  const load = vi.fn(async (f: Record<string, string | undefined>) =>
    f.cursor === "c1" ? { jobs: second, next_cursor: null, options } : page(["a", "b"], "c1"),
  );
  const hook = renderHook(() => useJobPages({}, load));
  await flush();
  await act(async () => {
    await hook.result.current.loadMore();
  });
  expect(stateOf(hook.result.current.jobs, "c")).toBe("running");
  second = [withState("c", "succeeded"), withState("d", "queued")];
  await tick(1000);
  expect(stateOf(hook.result.current.jobs, "c")).toBe("succeeded");
  expect(hook.result.current.nextCursor).toBeNull();
  hook.unmount();
});

it("drops a later-page job that no longer matches the state filter", async () => {
  vi.useFakeTimers();
  let second = [withState("c", "running"), withState("d", "running")];
  const load = vi.fn(async (f: Record<string, string | undefined>) => {
    expect(f.state).toBe("running");
    return f.cursor === "c1"
      ? { jobs: second, next_cursor: null, options }
      : { jobs: [withState("a", "running")], next_cursor: "c1", options };
  });
  const hook = renderHook(() => useJobPages({ state: "running" }, load));
  await flush();
  await act(async () => {
    await hook.result.current.loadMore();
  });
  expect(ids(hook.result.current.jobs)).toEqual(["a", "c", "d"]);
  second = [withState("d", "running")];
  await tick(1000);
  expect(ids(hook.result.current.jobs)).toEqual(["a", "d"]);
  hook.unmount();
});

it("keeps loaded pages on a revalidation failure, backs off, and recovers on a later poll", async () => {
  vi.useFakeTimers();
  let fail = false;
  let second = [withState("c", "running")];
  const load = vi.fn(async (f: Record<string, string | undefined>) => {
    if (f.cursor === "c1") {
      if (fail) throw Error("page 2 offline");
      return { jobs: second, next_cursor: null, options };
    }
    return page(["a"], "c1");
  });
  const hook = renderHook(() => useJobPages({}, load));
  await flush();
  await act(async () => {
    await hook.result.current.loadMore();
  });
  fail = true;
  second = [withState("c", "succeeded")];
  await tick(1000);
  expect(hook.result.current.loadMoreError).toBe("page 2 offline");
  expect(stateOf(hook.result.current.jobs, "c")).toBe("running");
  const failedCalls = load.mock.calls.filter(([f]) => f.cursor).length;
  await tick(1000);
  expect(load.mock.calls.filter(([f]) => f.cursor)).toHaveLength(failedCalls);
  fail = false;
  await tick(5000);
  expect(stateOf(hook.result.current.jobs, "c")).toBe("succeeded");
  expect(hook.result.current.loadMoreError).toBeNull();
  expect(hook.result.current.loadingMore).toBe(false);
  hook.unmount();
});
