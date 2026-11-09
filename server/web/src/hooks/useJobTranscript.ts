import { focusManager } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getJobOutput, type OutputPage } from "../api";
import { apply, initialTranscriptState, type TranscriptRow, type TranscriptState } from "../transcript/reduce";

const POLL_MS = 1000;
const ERROR_BACKOFF_MS = 5000;
const NO_EVENTS: OutputPage["events"] = [];

export type UseJobTranscriptResult = {
  rows: TranscriptRow[];
  status: OutputPage | null;
  error: unknown;
  loading: boolean;
};

type LoadOutput = (id: string, after?: number, signal?: AbortSignal) => Promise<OutputPage>;

/**
 * Runs one serialized fetch loop per job to stream output events.
 * Responses are reduced incrementally into display rows without storing raw events.
 * The loop pauses while the tab is hidden (via focusManager) and drops responses
 * if the selected job changes.
 */
export function useJobTranscript(jobId: string | null, load: LoadOutput = getJobOutput): UseJobTranscriptResult {
  const [transcript, setTranscript] = useState<TranscriptState>(initialTranscriptState);
  const [status, setStatus] = useState<OutputPage | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    let cursor = 0;
    let inFlight = false;
    let isTerminal = false;
    let scheduledTimer: ReturnType<typeof setTimeout> | null = null;
    let state = initialTranscriptState();
    const controller = new AbortController();

    setTranscript(state);
    setStatus(null);
    setError(null);
    setLoading(Boolean(jobId));

    const clearSchedule = () => {
      if (scheduledTimer !== null) {
        clearTimeout(scheduledTimer);
        scheduledTimer = null;
      }
    };

    const schedule = (delay: number) => {
      clearSchedule();
      if (!active || isTerminal) return;
      scheduledTimer = setTimeout(() => {
        scheduledTimer = null;
        void step();
      }, delay);
    };

    const step = async () => {
      if (!active || inFlight || isTerminal) return;
      if (!focusManager.isFocused()) return;

      inFlight = true;
      clearSchedule();

      try {
        let hasMore = true;
        while (hasMore && active && focusManager.isFocused()) {
          const page = await load(jobId as string, cursor, controller.signal);
          if (!active) return;

          cursor = page.next;
          state = apply(state, page.events);
          setTranscript(state);
          const { events: _events, ...meta } = page;
          setStatus({ ...meta, events: NO_EVENTS });
          setError(null);
          setLoading(false);

          if (page.terminal && !page.has_more) {
            isTerminal = true;
            return;
          }

          hasMore = page.has_more;
        }

        if (active && !isTerminal && focusManager.isFocused()) {
          schedule(POLL_MS);
        }
      } catch (err) {
        if ((err as { name?: string })?.name === "AbortError" || controller.signal.aborted) {
          return;
        }
        if (active) {
          setError(err);
          setLoading(false);
          if (focusManager.isFocused()) {
            schedule(ERROR_BACKOFF_MS);
          }
        }
      } finally {
        inFlight = false;
      }
    };

    if (!jobId) {
      return () => {
        active = false;
        clearSchedule();
      };
    }

    const unsubscribeFocus = focusManager.subscribe((focused) => {
      if (!active || isTerminal) return;
      if (focused) {
        if (!inFlight) {
          clearSchedule();
          void step();
        }
      } else {
        clearSchedule();
      }
    });

    void step();

    return () => {
      active = false;
      clearSchedule();
      controller.abort();
      unsubscribeFocus();
    };
  }, [jobId, load]);

  return {
    rows: transcript.rows as TranscriptRow[],
    status,
    error,
    loading,
  };
}
