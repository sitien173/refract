import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { DashboardApiError, postJobAction } from "../api";

export type JobActionName = "cancel" | "retry" | "answer";

type Options = {
  jobId: string | null;
  announce: (message: string) => void;
  /** Called with the new job id after a successful retry, before the success announcement. */
  onRetried: (newJobId: string) => void;
  /** Called when an answer was rejected because the question is no longer pending. */
  onStaleQuestion?: () => void;
  post?: typeof postJobAction;
};

const isStaleQuestion = (error: unknown) => error instanceof DashboardApiError && error.status === 409 && error.code === "invalid_state";

export function useJobActions({ jobId, announce, onRetried, onStaleQuestion, post = postJobAction }: Options) {
  const queryClient = useQueryClient();

  const cancelMutation = useMutation({
    mutationFn: async () => {
      if (!jobId) return;
      return post(jobId, "cancel", {});
    },
    retry: false,
    onSuccess: () => {
      if (!jobId) return;
      queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      announce("Cancellation requested");
    },
    onError: (error) => {
      announce(error instanceof Error ? error.message : "Action failed");
    },
  });

  const retryMutation = useMutation({
    mutationFn: async () => {
      if (!jobId) return;
      return post(jobId, "retry", {});
    },
    retry: false,
    onSuccess: (result) => {
      if (!jobId) return;
      queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      if (result && typeof result.job_id === "string") {
        onRetried(result.job_id);
      }
      announce("Retry started");
    },
    onError: (error) => {
      announce(error instanceof Error ? error.message : "Action failed");
    },
  });

  const answerMutation = useMutation({
    mutationFn: async ({ question_id, answer }: { question_id: string; answer: string }) => {
      if (!jobId) return;
      return post(jobId, "answer", { question_id, answer });
    },
    retry: false,
    onSuccess: () => {
      if (!jobId) return;
      queryClient.invalidateQueries({ queryKey: ["job", jobId] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      announce("Answer sent");
    },
    onError: (error) => {
      announce(error instanceof Error ? error.message : "Action failed");
      if (isStaleQuestion(error)) {
        if (jobId) {
          queryClient.invalidateQueries({ queryKey: ["job", jobId] });
        }
        onStaleQuestion?.();
      }
    },
  });

  const cancel = useCallback(async () => {
    if (!jobId) return;
    try {
      await cancelMutation.mutateAsync();
    } catch {
      // Handled in onError
    }
  }, [jobId, cancelMutation]);

  const retry = useCallback(async () => {
    if (!jobId) return;
    try {
      await retryMutation.mutateAsync();
    } catch {
      // Handled in onError
    }
  }, [jobId, retryMutation]);

  const answer = useCallback(
    async (question_id: string, answerText: string) => {
      if (!jobId) return;
      await answerMutation.mutateAsync({ question_id, answer: answerText });
    },
    [jobId, answerMutation],
  );

  return {
    busy: cancelMutation.isPending || retryMutation.isPending || answerMutation.isPending,
    cancel,
    retry,
    answer,
  };
}
