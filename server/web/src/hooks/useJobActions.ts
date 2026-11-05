import { useCallback, useState } from "react";
import { DashboardApiError, postJobAction } from "../api";

export type JobActionName = "cancel" | "retry" | "answer";

const SUCCESS_MESSAGES: Record<JobActionName, string> = {
  cancel: "Cancellation requested",
  retry: "Retry started",
  answer: "Answer sent",
};

type Options = {
  jobId: string | null;
  announce: (message: string) => void;
  /** Called with the new job id after a successful retry, before the success announcement. */
  onRetried: (newJobId: string) => void;
  /** Called when an answer was rejected because the question is no longer pending. */
  onStaleQuestion: () => void;
  post?: typeof postJobAction;
};

const isStaleQuestion = (error: unknown) =>
  error instanceof DashboardApiError && error.status === 409 && error.code === "invalid_state";

/**
 * Runs cancel, retry and answer requests for one job. Results are announced;
 * a failed answer is rethrown so the dialog can keep the draft and show the error.
 */
export function useJobActions({ jobId, announce, onRetried, onStaleQuestion, post = postJobAction }: Options) {
  const [busy, setBusy] = useState(false);

  const perform = useCallback(
    async (name: JobActionName, body: Record<string, string> = {}) => {
      if (!jobId) return;
      setBusy(true);
      try {
        const result = await post(jobId, name, body);
        if (name === "retry" && typeof result.job_id === "string") onRetried(result.job_id);
        announce(SUCCESS_MESSAGES[name]);
      } catch (error) {
        announce(error instanceof Error ? error.message : "Action failed");
        if (name === "answer") {
          if (isStaleQuestion(error)) onStaleQuestion();
          throw error;
        }
      } finally {
        setBusy(false);
      }
    },
    [jobId, post, announce, onRetried, onStaleQuestion],
  );

  return {
    busy,
    cancel: () => perform("cancel"),
    retry: () => perform("retry"),
    answer: (question_id: string, answer: string) => perform("answer", { question_id, answer }),
  };
}
