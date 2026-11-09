import { type InfiniteData, keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getJobs, type JobPage, type JobSummary } from "../api";

type Filters = Record<string, string | undefined>;
type LoadJobs = (filters: Filters, signal?: AbortSignal) => Promise<JobPage>;

const EMPTY_OPTIONS: JobPage["options"] = { states: [], projects: [], workflows: [], targets: [] };

const messageOf = (error: unknown, fallback: string) => (error instanceof Error ? error.message : fallback);

export function useJobPages(filters: Record<string, string>, load: LoadJobs = getJobs, enabled = true) {
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);

  const filterKey = useMemo(() => new URLSearchParams(filters).toString(), [filters]);
  const prevFilterKeyRef = useRef(filterKey);
  const inFlightRef = useRef(false);

  useEffect(() => {
    if (prevFilterKeyRef.current !== filterKey) {
      prevFilterKeyRef.current = filterKey;
      inFlightRef.current = false;
      setLoadMoreError(null);
    }
  }, [filterKey]);

  const query = useInfiniteQuery({
    queryKey: ["jobs", filters],
    queryFn: async ({ pageParam, signal }) => {
      const activeFilters: Filters = { ...filters };
      if (pageParam) {
        activeFilters.cursor = pageParam;
      }
      return load(activeFilters, signal);
    },
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? null,
    refetchInterval: (q) => (q.state.error ? 5000 : 1000),
    placeholderData: keepPreviousData,
    enabled,
    select: (data: InfiniteData<JobPage, string | null>) => {
      const seen = new Set<string>();
      const jobs: JobSummary[] = [];
      for (const page of data.pages) {
        for (const job of page.jobs) {
          if (!seen.has(job.id)) {
            seen.add(job.id);
            jobs.push(job);
          }
        }
      }
      const firstPage = data.pages[0];
      const lastPage = data.pages[data.pages.length - 1];
      return {
        jobs,
        options: firstPage?.options ?? EMPTY_OPTIONS,
        nextCursor: lastPage?.next_cursor ?? null,
      };
    },
  });

  const isAnyFetchOrPlaceholderActive = query.isFetching || query.isPlaceholderData;
  const hasMore = Boolean(query.hasNextPage && query.data?.nextCursor);

  const loadMore = useCallback(async () => {
    if (inFlightRef.current || isAnyFetchOrPlaceholderActive || !hasMore) return;
    inFlightRef.current = true;
    setLoadMoreError(null);
    try {
      const result = await query.fetchNextPage();
      if (result.error) {
        setLoadMoreError(messageOf(result.error, "Unable to load more jobs."));
      }
    } finally {
      inFlightRef.current = false;
    }
  }, [isAnyFetchOrPlaceholderActive, hasMore, query.fetchNextPage]);

  const jobs = query.data?.jobs ?? [];
  const options = query.data?.options ?? EMPTY_OPTIONS;
  const nextCursor = query.isPending ? null : (query.data?.nextCursor ?? null);

  return {
    jobs,
    options,
    nextCursor,
    loading: query.isPending && !query.isPlaceholderData,
    error: query.error,
    loadingMore: query.isFetchingNextPage,
    loadMoreError,
    loadMore,
  };
}
