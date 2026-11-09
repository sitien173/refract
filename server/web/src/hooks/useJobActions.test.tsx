import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DashboardApiError } from "../api";
import { createQueryWrapper, createTestQueryClient } from "../test/query";
import { useJobActions } from "./useJobActions";

describe("useJobActions", () => {
  it("announces Cancellation requested even if cancel response has state running", async () => {
    const queryClient = createTestQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const announce = vi.fn();
    const onRetried = vi.fn();
    const onStaleQuestion = vi.fn();
    const post = vi.fn().mockResolvedValue({ job_id: "job-1", state: "running", success: true });

    const hook = renderHook(
      () =>
        useJobActions({
          jobId: "job-1",
          announce,
          onRetried,
          onStaleQuestion,
          post,
        }),
      { wrapper: createQueryWrapper(queryClient) },
    );

    await act(async () => {
      await hook.result.current.cancel();
    });

    expect(post).toHaveBeenCalledWith("job-1", "cancel", {});
    expect(announce).toHaveBeenCalledWith("Cancellation requested");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["job", "job-1"] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["jobs"] });
  });

  it("navigates to retry job ID and invalidates queries on retry", async () => {
    const queryClient = createTestQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const announce = vi.fn();
    const onRetried = vi.fn();
    const onStaleQuestion = vi.fn();
    const post = vi.fn().mockResolvedValue({ job_id: "job-1-retry", state: "queued" });

    const hook = renderHook(
      () =>
        useJobActions({
          jobId: "job-1",
          announce,
          onRetried,
          onStaleQuestion,
          post,
        }),
      { wrapper: createQueryWrapper(queryClient) },
    );

    await act(async () => {
      await hook.result.current.retry();
    });

    expect(post).toHaveBeenCalledWith("job-1", "retry", {});
    expect(onRetried).toHaveBeenCalledWith("job-1-retry");
    expect(announce).toHaveBeenCalledWith("Retry started");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["job", "job-1"] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["jobs"] });
  });

  it("reloads detail on answer 409 and rethrows error so draft stays", async () => {
    const queryClient = createTestQueryClient();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const announce = vi.fn();
    const onRetried = vi.fn();
    const onStaleQuestion = vi.fn();
    const staleError = new DashboardApiError("Question expired", 409, "invalid_state");
    const post = vi.fn().mockRejectedValue(staleError);

    const hook = renderHook(
      () =>
        useJobActions({
          jobId: "job-1",
          announce,
          onRetried,
          onStaleQuestion,
          post,
        }),
      { wrapper: createQueryWrapper(queryClient) },
    );

    let caughtError: unknown;
    await act(async () => {
      try {
        await hook.result.current.answer("q-1", "Proceed");
      } catch (err) {
        caughtError = err;
      }
    });

    expect(caughtError).toBe(staleError);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["job", "job-1"] });
    expect(onStaleQuestion).toHaveBeenCalled();
  });
});
