import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import type { CardDetailResponse } from "../api";
import { COLUMN_LABELS, formatRelativeTime, getProjectName, shortCardId } from "../lib/board";

export type CardPanelProps = {
  detail?: CardDetailResponse | null;
  loading?: boolean;
  error?: { status?: number; message?: string } | string | null;
  onClose?: () => void;
};

export function CardPanel({ detail, loading = false, error = null, onClose }: CardPanelProps) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose?.();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const errorMessage = typeof error === "string" ? error : error?.message;

  return (
    <aside aria-label="Card detail" className="flex w-96 shrink-0 flex-col gap-4 border-l border-border bg-card p-6 overflow-y-auto">
      <div className="flex items-start justify-between gap-2">
        {detail ? <h2 className="text-xl font-semibold tracking-tight break-all">{detail.card.title}</h2> : <h2 className="text-xl font-semibold tracking-tight">Card</h2>}
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
          Close
        </Button>
      </div>

      {error && (
        <div role="alert" className="callout callout-error">
          {errorMessage ?? "Unable to load card."}
        </div>
      )}

      {loading && !detail && (
        <p role="status" className="text-sm text-muted-foreground">
          Loading card…
        </p>
      )}

      {detail && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{COLUMN_LABELS[detail.card.state]}</span>
            <span>•</span>
            <span>{getProjectName(detail.card.project_root)}</span>
          </div>

          <div className="whitespace-pre-wrap text-sm text-foreground">{detail.card.body}</div>

          {detail.jobs.length > 0 && (
            <section aria-label="Linked jobs" className="flex flex-col gap-2">
              <h3 className="text-sm font-semibold">Linked jobs</h3>
              <ul className="flex flex-col gap-2">
                {detail.jobs.map((job) => (
                  <li key={job.id}>
                    {job.available ? (
                      <a href={`/dashboard/jobs/${encodeURIComponent(job.id)}`} className="flex flex-col gap-1 rounded-md border border-border p-2.5 text-xs hover:bg-muted/50">
                        <div className="flex items-center justify-between font-medium">
                          <span>{shortCardId(job.id)}</span>
                          <span>{job.state ?? "unknown"}</span>
                        </div>
                        <div className="flex items-center justify-between text-muted-foreground">
                          <span>{job.workflow ?? "workflow"}</span>
                          <span>{job.target ?? "target"}</span>
                        </div>
                      </a>
                    ) : (
                      <div className="flex items-center justify-between rounded-md border border-border p-2.5 text-xs text-muted-foreground">
                        <span>{shortCardId(job.id)}</span>
                        <span>unavailable</span>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section aria-label="Timeline" className="flex flex-col gap-2">
            <h3 className="text-sm font-semibold">Timeline</h3>
            <ol className="flex flex-col gap-3">
              <li className="flex flex-col gap-0.5 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium">Created</span>
                  <span className="text-muted-foreground">{formatRelativeTime(detail.card.created_at)}</span>
                </div>
              </li>
              {detail.moves.map((move) => (
                <li key={`${move.at}-${move.to_state}`} className="flex flex-col gap-0.5 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">Moved to {COLUMN_LABELS[move.to_state]}</span>
                    <span className="text-muted-foreground">{formatRelativeTime(move.at)}</span>
                  </div>
                  {move.note ? <p className="text-muted-foreground whitespace-pre-wrap">{move.note}</p> : null}
                </li>
              ))}
            </ol>
          </section>
        </>
      )}
    </aside>
  );
}
