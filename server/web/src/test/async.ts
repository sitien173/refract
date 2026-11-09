import { act } from "@testing-library/react";
import { vi } from "vitest";

/**
 * Advance fake timers inside an async `act` so pending promises and the React
 * updates they cause are flushed deterministically. Testing Library's
 * `waitFor` cannot advance Vitest fake timers, so tests use this instead.
 */
export async function settle(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}
