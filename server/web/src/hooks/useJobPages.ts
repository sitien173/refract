import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getJobs, type JobPage, type JobSummary } from "../api";
import { usePolling } from "./usePolling";

type Filters = Record<string, string | undefined>;
type LoadJobs = (filters: Filters) => Promise<JobPage>;
type ExtraPage = { jobs: JobSummary[]; next_cursor: string | null };

const REVALIDATE_BACKOFF_MS = 5000;
const NO_PAGES: ExtraPage[] = [];
const EMPTY_OPTIONS: JobPage["options"] = { states: [], projects: [], workflows: [], targets: [] };

const parseFilters = (key: string): Filters => Object.fromEntries(new URLSearchParams(key).entries());
const messageOf = (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback);

function dedupeById(jobs: JobSummary[]): JobSummary[] {
  const seen = new Set<string>();
  return jobs.filter((job) => {
    if (seen.has(job.id)) return false;
    seen.add(job.id);
    return true;
  });
}

/**
 * The job list for one filter set: a live-polled first page plus cursor pages
 * the user asked for.
 *
 * - Every async result is tagged with a generation that changes with the
 *   filters; results (including errors and finalizers) from an older
 *   generation are discarded.
 * - The first page keeps refreshing, and each refresh also refetches the loaded
 *   cursor pages (sequentially, no overlap, 5 s backoff after a failure) from the
 *   first page's current `next_cursor`. This keeps the combined list gapless and
 *   current even when a later-page job changes state or leaves the filter.
 * - The combined list is deduplicated by job id; earlier pages win.
 */
export function useJobPages(filters: Record<string, string>, load: LoadJobs = getJobs) {
  const key = useMemo(() => new URLSearchParams(filters).toString(), [filters]);
  const loadFirstPage = useCallback((filterKey: string) => load(parseFilters(filterKey)), [load]);
  const first = usePolling(key, loadFirstPage);
  const firstPage = first.value;

  const [extra, setExtra] = useState<{ key: string; pages: ExtraPage[] }>({ key, pages: [] });
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);

  const generation = useRef(0);
  const inflight = useRef(false);
  const extraRef = useRef<ExtraPage[]>([]);
  const retryAt = useRef(0);
  const keyRef = useRef(key);
  const firstRef = useRef({ page: firstPage, loading: first.loading });
  keyRef.current = key;
  firstRef.current = { page: firstPage, loading: first.loading };

  useEffect(() => {
    generation.current += 1;
    inflight.current = false;
    extraRef.current = [];
    retryAt.current = 0;
    setExtra({ key, pages: [] });
    setLoadingMore(false);
    setLoadMoreError(null);
  }, [key]);

  const commit = (pages: ExtraPage[], filterKey: string) => {
    extraRef.current = pages;
    setExtra({ key: filterKey, pages });
  };

  const loadMore = useCallback(async () => {
    const { page: base, loading } = firstRef.current;
    const loaded = extraRef.current;
    const cursor = loaded.length ? loaded[loaded.length - 1]!.next_cursor : (base?.next_cursor ?? null);
    if (!cursor || loading || inflight.current) return;
    const mine = generation.current;
    const filterKey = keyRef.current;
    inflight.current = true;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const next = await load({ ...parseFilters(filterKey), cursor });
      if (mine !== generation.current) return;
      commit([...extraRef.current, { jobs: next.jobs, next_cursor: next.next_cursor }], filterKey);
    } catch (error) {
      if (mine === generation.current) setLoadMoreError(messageOf(error, "Unable to load more jobs."));
    } finally {
      if (mine === generation.current) {
        inflight.current = false;
        setLoadingMore(false);
      }
    }
  }, [load]);

  // Every first-page poll also refreshes the loaded pages, sequentially and never
  // overlapping, so state changes and filter exits on later pages show up even when
  // the first-page cursor has not moved. A failure keeps the previous pages and
  // pauses revalidation for the backoff period; the next poll after that retries.
  useEffect(() => {
    if (!firstPage || first.loading) return;
    const loaded = extraRef.current;
    if (!loaded.length || inflight.current || Date.now() < retryAt.current) return;
    const mine = generation.current;
    const filterKey = keyRef.current;
    inflight.current = true;
    void (async () => {
      try {
        const fresh: ExtraPage[] = [];
        let cursor = firstPage.next_cursor;
        for (let i = 0; i < loaded.length && cursor; i += 1) {
          const next = await load({ ...parseFilters(filterKey), cursor });
          if (mine !== generation.current) return;
          fresh.push({ jobs: next.jobs, next_cursor: next.next_cursor });
          cursor = next.next_cursor;
        }
        if (retryAt.current) setLoadMoreError(null);
        retryAt.current = 0;
        commit(fresh, filterKey);
      } catch (error) {
        if (mine !== generation.current) return;
        retryAt.current = Date.now() + REVALIDATE_BACKOFF_MS;
        setLoadMoreError(messageOf(error, "Unable to refresh loaded jobs."));
      } finally {
        if (mine === generation.current) inflight.current = false;
      }
    })();
  }, [firstPage, first.loading, load]);

  const pages = extra.key === key ? extra.pages : NO_PAGES;
  const jobs = useMemo(
    () => dedupeById([...(firstPage?.jobs ?? []), ...pages.flatMap((p) => p.jobs)]),
    [firstPage, pages],
  );
  const lastPage = pages[pages.length - 1];
  const nextCursor = first.loading ? null : lastPage ? lastPage.next_cursor : (firstPage?.next_cursor ?? null);

  return {
    jobs,
    options: firstPage?.options ?? EMPTY_OPTIONS,
    nextCursor,
    loading: first.loading,
    error: first.error,
    loadingMore,
    loadMoreError,
    loadMore,
  };
}
