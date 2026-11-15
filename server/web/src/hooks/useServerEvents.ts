import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { z } from "zod";

const EVENTS_URL = "/dashboard/api/events";
const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 30_000;
const CLOSED = 2;

const ServerEventSchema = z.object({ job_id: z.string(), kind: z.string() });

export type EventSourceLike = {
  onopen: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onerror: (() => void) | null;
  readonly readyState: number;
  close: () => void;
};

// The handlers only read `event.data`, so the narrower event type is safe.
const createEventSource = (url: string): EventSourceLike | null => (typeof EventSource === "undefined" ? null : (new EventSource(url) as unknown as EventSourceLike));

/**
 * Subscribes to the server's job signals and invalidates the matching queries. The signal only says
 * that something changed; the queries refetch the state. A `resync` frame means the server dropped
 * signals for this client, so every job query is refetched. The 30-second `refetchInterval` on each
 * query stays as the fallback while the stream is down.
 */
export function useServerEvents(create: (url: string) => EventSourceLike | null = createEventSource): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    let source: EventSourceLike | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let delay = RECONNECT_MIN_MS;
    let dropped = false;
    let stopped = false;

    const invalidateAll = () => {
      for (const queryKey of [["job"], ["jobs"], ["cards"], ["card"], ["stats"], ["targets"]]) {
        void queryClient.invalidateQueries({ queryKey });
      }
    };

    const onEvent = (raw: string) => {
      let json: unknown;
      try {
        json = JSON.parse(raw);
      } catch {
        return;
      }
      const parsed = ServerEventSchema.safeParse(json);
      if (!parsed.success) return;
      const { job_id, kind } = parsed.data;
      if (kind === "resync") {
        invalidateAll();
        return;
      }
      void queryClient.invalidateQueries({ queryKey: ["job", job_id] });
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["cards"] });
      void queryClient.invalidateQueries({ queryKey: ["card"] });
      if (kind === "terminal") {
        void queryClient.invalidateQueries({ queryKey: ["stats"] });
        void queryClient.invalidateQueries({ queryKey: ["targets"] });
      }
    };

    const connect = () => {
      timer = null;
      const next = create(EVENTS_URL);
      if (!next) return;
      source = next;
      next.onopen = () => {
        delay = RECONNECT_MIN_MS;
        // Signals sent while the stream was down are lost, so refetch once it is back.
        if (dropped) {
          dropped = false;
          invalidateAll();
        }
      };
      next.onmessage = (event) => onEvent(event.data);
      next.onerror = () => {
        dropped = true;
        // A connecting source reconnects on its own. A closed one gave up, so reopen it with backoff.
        if (next.readyState !== CLOSED || stopped) return;
        next.close();
        source = null;
        timer = setTimeout(connect, delay);
        delay = Math.min(delay * 2, RECONNECT_MAX_MS);
      };
    };

    connect();

    return () => {
      stopped = true;
      if (timer !== null) clearTimeout(timer);
      source?.close();
    };
  }, [queryClient, create]);
}
