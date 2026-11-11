import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import {
  type CardDetailResponse,
  type CardsResponse,
  DashboardApiError,
  getCard,
  getCards,
  getJob,
  getStats,
  getTargets,
  isTerminalJobState,
  type JobDetail,
  type StatsDays,
  type StatsResponse,
  type TargetsResponse,
} from "../api";

export function useJobDetail(
  id: string | null,
  options?: {
    load?: (id: string, signal?: AbortSignal) => Promise<JobDetail>;
    onNotFound?: () => void;
  },
) {
  const load = options?.load ?? getJob;
  const onNotFound = options?.onNotFound;

  const query = useQuery({
    queryKey: ["job", id],
    queryFn: ({ signal }) => {
      if (!id) throw new Error("Job ID required");
      return load(id, signal);
    },
    enabled: Boolean(id),
    refetchInterval: (q) => {
      const data = q.state.data;
      if (data && isTerminalJobState(data.state)) {
        return false;
      }
      return q.state.error ? 5000 : 1000;
    },
  });

  useEffect(() => {
    if (query.error instanceof DashboardApiError && query.error.status === 404) {
      onNotFound?.();
    }
  }, [query.error, onNotFound]);

  return query;
}

export function useTargets(options?: { load?: (signal?: AbortSignal) => Promise<TargetsResponse>; enabled?: boolean }) {
  const load = options?.load ?? getTargets;
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: ["targets"],
    queryFn: ({ signal }) => load(signal),
    enabled,
  });
}

export function useBoardCards(
  project?: string,
  options?: {
    load?: (project?: string, signal?: AbortSignal) => Promise<CardsResponse>;
    enabled?: boolean;
  },
) {
  const load = options?.load ?? getCards;
  const enabled = options?.enabled === true;

  return useQuery({
    queryKey: ["cards", project ?? ""],
    queryFn: ({ signal }) => load(project, signal),
    enabled,
    refetchInterval: (q) => (q.state.error ? 5000 : 1000),
  });
}

export function useCardDetail(
  cardId: string | null,
  options?: {
    load?: (id: string, signal?: AbortSignal) => Promise<CardDetailResponse>;
    onNotFound?: () => void;
  },
) {
  const load = options?.load ?? getCard;
  const onNotFound = options?.onNotFound;

  const query = useQuery({
    queryKey: ["card", cardId],
    queryFn: ({ signal }) => {
      if (!cardId) throw new Error("Card ID required");
      return load(cardId, signal);
    },
    enabled: Boolean(cardId),
    refetchInterval: (q) => (q.state.error ? 5000 : 1000),
  });

  useEffect(() => {
    if (query.error instanceof DashboardApiError && query.error.status === 404) {
      onNotFound?.();
    }
  }, [query.error, onNotFound]);

  return query;
}

/** `new Date().getTimezoneOffset()` is positive west of UTC; the stats API wants a UTC offset, east positive. */
const browserUtcOffsetMinutes = () => -new Date().getTimezoneOffset() || 0;

export function useStats(days: StatsDays, options?: { load?: (days: StatsDays, tzOffsetMinutes: number, signal?: AbortSignal) => Promise<StatsResponse>; enabled?: boolean }) {
  const load = options?.load ?? getStats;
  const enabled = options?.enabled ?? true;
  const tzOffsetMinutes = browserUtcOffsetMinutes();

  return useQuery({
    queryKey: ["stats", days, tzOffsetMinutes],
    queryFn: ({ signal }) => load(days, tzOffsetMinutes, signal),
    enabled,
  });
}
