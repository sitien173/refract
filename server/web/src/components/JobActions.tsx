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
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
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
  // biome-ignore lint/correctness/useExhaustiveDependencies: jobId is the reset trigger; the effect body deliberately does not read it.
  useEffect(() => {
    setAnswer("");
    setAnswerError("");
    setAnswerOpen(false);
  }, [jobId]);

  const canCancel = state === "queued" || state === "running";
  const canRetry = isTerminalJobState(state);

  const changeAnswerOpen = (open: boolean) => {
    if (open) setAnswerError("");
    setAnswerOpen(open);
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
    <div className="flex flex-wrap gap-2">
      <AlertDialog>
        <AlertDialogTrigger render={<Button variant="destructive" disabled={busy || !canCancel} />}>Cancel job</AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Cancel this job?</AlertDialogTitle>
            <AlertDialogDescription>A running job may take time to stop.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel render={<Button variant="secondary" disabled={busy} />}>Keep job</AlertDialogCancel>
            <AlertDialogAction render={<Button disabled={busy} onClick={onCancel} />}>Confirm cancellation</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Button variant="secondary" disabled={busy || !canRetry} onClick={onRetry}>
        Retry job
      </Button>

      {pendingQuestion && (
        <Dialog open={answerOpen} onOpenChange={changeAnswerOpen}>
          <DialogTrigger render={<Button disabled={busy} />}>Answer question</DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Answer question</DialogTitle>
            </DialogHeader>
            <p className="text-sm">{pendingQuestion.text}</p>
            <label className="text-[0.8125rem] font-medium text-muted-foreground" htmlFor="job-answer">
              Your answer
            </label>
            <Input id="job-answer" aria-label="Your answer" value={answer} onChange={(e) => setAnswer(e.target.value)} />
            {answerError && (
              <div role="alert" className="callout callout-error">
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
      )}
    </div>
  );
}
