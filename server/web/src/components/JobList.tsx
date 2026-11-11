import { ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { JobSummary } from "../api";
import { groupByProject, jobLabel } from "../lib/jobs";

type JobListProps = {
  jobs: JobSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading?: boolean;
  error?: string | null;
};

function stateDotClass(state: string): string {
  switch (state) {
    case "running":
      return "bg-primary";
    case "succeeded":
      return "bg-[#34c759]";
    case "failed":
      return "bg-destructive";
    default:
      return "bg-muted-foreground";
  }
}

export function JobList({ jobs, selectedId, onSelect, loading = false, error = null }: JobListProps) {
  const groups = groupByProject(jobs, (job) => job.project_root);

  return (
    <nav aria-label="Jobs" className="flex flex-col gap-2">
      {error && (
        <div role="alert" className="callout callout-error">
          {error}
        </div>
      )}
      {loading && (
        <p role="status" className="px-1 text-sm text-muted-foreground">
          {jobs.length ? "Refreshing jobs…" : "Loading jobs…"}
        </p>
      )}
      {groups.map((group) => (
        <details key={group.root || "no-project"} open className="group space-y-1">
          <summary className="flex cursor-pointer select-none items-center gap-2 list-none px-1 py-1 text-xs font-semibold text-foreground [&::-webkit-details-marker]:hidden">
            <ChevronRight aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-90" />
            <span>{group.name}</span>
            {group.root ? (
              <span title={group.root} className="truncate font-normal text-muted-foreground">
                {group.root}
              </span>
            ) : null}
            <span className="ml-auto font-normal text-muted-foreground">
              {group.items.length}
              <span className="sr-only">{group.items.length === 1 ? " job" : " jobs"}</span>
            </span>
          </summary>
          <div className="flex flex-col gap-1">
            {group.items.map((job) => {
              const { title, meta } = jobLabel(job);
              const isSelected = job.id === selectedId;
              return (
                <Button
                  key={job.id}
                  className="relative h-auto min-h-9 flex-col items-start justify-start py-1.5 text-left whitespace-normal break-all"
                  variant={isSelected ? "default" : "ghost"}
                  aria-current={isSelected ? "page" : undefined}
                  onClick={() => onSelect(job.id)}
                >
                  <span className="flex items-center gap-1.5 font-medium">
                    <span aria-hidden="true" className={cn("size-2 shrink-0 rounded-full", stateDotClass(job.state), isSelected && "ring-1 ring-primary-foreground/60")} />
                    <span>{title}</span>
                  </span>
                  <span className={cn("text-xs", isSelected ? "text-primary-foreground/80" : "text-muted-foreground")}>{meta ? `${meta} · ${job.state}` : job.state}</span>
                </Button>
              );
            })}
          </div>
        </details>
      ))}
      {jobs.length === 0 && !loading && !error && <p className="px-1 text-sm text-muted-foreground">No jobs found.</p>}
    </nav>
  );
}
