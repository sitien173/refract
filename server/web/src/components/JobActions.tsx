import { useEffect, useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { isTerminalJobState } from "../api";

type JobActionsProps = {
  jobId?: string;
  pendingQuestion: { question_id: string; text: string } | null;
  busy: boolean;
  state?: string | null;
  onCancel: () => void | Promise<void>;
  onRetry: () => void | Promise<void>;
  onAnswer: (questionId: string, answer: string) => void | Promise<void>;
};

export function JobActions({ jobId, pendingQuestion, busy, state, onCancel, onRetry, onAnswer }: JobActionsProps) {
  const [answerOpen, setAnswerOpen] = useState(false);
  const [answer, setAnswer] = useState("");
  const [answerError, setAnswerError] = useState("");

  // Drafts belong to one job; switching jobs starts clean.
  useEffect(() => {
    setAnswer("");
    setAnswerError("");
    setAnswerOpen(false);
  }, [jobId]);

  const canCancel = state === "queued" || state === "running";
  const canRetry = isTerminalJobState(state);

  const openAnswer = () => {
    setAnswerError("");
    setAnswerOpen(true);
  };

  // A rejected answer keeps the dialog open and the draft intact.
  const submitAnswer = async (questionId: string) => {
    setAnswerError("");
    try {
      await onAnswer(questionId, answer);
      setAnswer("");
      setAnswerOpen(false);
    } catch (error) {
      setAnswerError(error instanceof Error ? error.message : "Unable to send answer");
    }
  };

  return (
    <div className="flex flex-wrap gap-(--gap-sm)">
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="destructive" disabled={busy || !canCancel}>
            Cancel job
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel this job?</AlertDialogTitle>
            <AlertDialogDescription>A running job may take time to stop.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel asChild>
              <Button variant="secondary" disabled={busy}>
                Keep job
              </Button>
            </AlertDialogCancel>
            <AlertDialogAction asChild>
              <Button disabled={busy} onClick={onCancel}>
                Confirm cancellation
              </Button>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Button variant="secondary" disabled={busy || !canRetry} onClick={onRetry}>
        Retry job
      </Button>

      {pendingQuestion && (
        <>
          <Button disabled={busy} onClick={openAnswer}>
            Answer question
          </Button>
          <Dialog open={answerOpen} onOpenChange={setAnswerOpen}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Answer question</DialogTitle>
              </DialogHeader>
              <p>{pendingQuestion.text}</p>
              <label className="tds-field-label" htmlFor="job-answer">
                Your answer
              </label>
              <Input id="job-answer" aria-label="Your answer" value={answer} onChange={(e) => setAnswer(e.target.value)} />
              {answerError && (
                <div role="alert" className="tds-announcement tds-announcement--error">
                  {answerError}
                </div>
              )}
              <DialogFooter>
                <Button variant="secondary" disabled={busy} onClick={() => setAnswerOpen(false)}>
                  Close
                </Button>
                <Button disabled={busy || !answer.trim()} onClick={() => submitAnswer(pendingQuestion.question_id)}>
                  Send answer
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </>
      )}
    </div>
  );
}
