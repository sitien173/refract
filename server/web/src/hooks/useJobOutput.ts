import { useEffect, useState } from "react";
import { getJobOutput, type OutputPage } from "../api";

const POLL_MS = 1000;
const TERMINAL_POLL_MS = 5000;
const ERROR_BACKOFF_MS = 5000;

/**
 * Streams a job's output events. Every fetched event is kept so the transcript
 * can always be reconstructed; the transcript view bounds what it renders.
 */
export function useJobOutput(jobId: string | null, load = getJobOutput) {
  const [events, setEvents] = useState<Record<string, unknown>[]>([]);
  const [status, setStatus] = useState<OutputPage | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    let cursor = 0;
    let busy = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setEvents([]);
    setStatus(null);
    setError(null);
    setLoading(Boolean(jobId));
    const stop = () => {
      live = false;
      clearTimeout(timer);
    };
    if (!jobId) return stop;

    const append = (items: Record<string, unknown>[]) => {
      if (items.length) setEvents((old) => [...old, ...items]);
    };
    const poll = async () => {
      if (!live) return;
      if (document.hidden || busy) {
        timer = setTimeout(poll, POLL_MS);
        return;
      }
      busy = true;
      try {
        let page = await load(jobId, cursor);
        if (!live) return;
        cursor = page.next;
        append(page.events);
        setStatus(page);
        setError(null);
        setLoading(false);
        while (page.has_more && live && !document.hidden) {
          page = await load(jobId, cursor);
          if (!live) return;
          cursor = page.next;
          append(page.events);
          setStatus(page);
        }
        const finished = page.terminal && !page.has_more;
        if (live && !finished) timer = setTimeout(poll, page.terminal ? TERMINAL_POLL_MS : POLL_MS);
      } catch (err) {
        if (live) {
          setError(err);
          setLoading(false);
          timer = setTimeout(poll, ERROR_BACKOFF_MS);
        }
      } finally {
        busy = false;
      }
    };
    void poll();
    return stop;
  }, [jobId, load]);

  return { events, status, error, loading };
}
