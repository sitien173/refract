import { useEffect, useRef, useState } from "react";

const ERROR_BACKOFF_MS = 5000;

/**
 * Polls `load(key)` while `key` is non-null. An empty string is a valid key.
 * `shouldContinue` lets the caller stop polling once a value is final (for
 * example a terminal job); changing the key starts polling again.
 */
export function usePolling<T>(
  key: string | null,
  load: (key: string) => Promise<T>,
  interval = 1000,
  shouldContinue: (value: T) => boolean = () => true,
) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(key !== null);
  const generation = useRef(0);
  const continueRef = useRef(shouldContinue);
  continueRef.current = shouldContinue;

  useEffect(() => {
    const token = ++generation.current;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let active = true;
    let busy = false;
    setError(null);
    setLoading(key !== null);
    if (key === null) {
      return () => {
        active = false;
        clearTimeout(timer);
      };
    }
    const poll = async () => {
      if (!active) return;
      if (document.hidden || busy) {
        timer = setTimeout(poll, interval);
        return;
      }
      busy = true;
      let nextDelay: number | null = interval;
      try {
        const next = await load(key);
        if (active && generation.current === token) {
          setValue(next);
          setError(null);
          setLoading(false);
          if (!continueRef.current(next)) nextDelay = null;
        }
      } catch (err) {
        nextDelay = ERROR_BACKOFF_MS;
        if (active && generation.current === token) {
          setError(err);
          setLoading(false);
        }
      } finally {
        busy = false;
        if (active && nextDelay !== null) timer = setTimeout(poll, nextDelay);
      }
    };
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [key, load, interval]);

  return { value, error, loading };
}
