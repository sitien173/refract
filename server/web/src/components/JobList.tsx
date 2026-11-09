import { Button } from "@/components/ui/button";
import type { JobSummary } from "../api";

type JobListProps = {
  jobs: JobSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading?: boolean;
  error?: string | null;
};

export function JobList({ jobs, selectedId, onSelect, loading = false, error = null }: JobListProps) {
  return (
    <nav aria-label="Jobs" className="flex flex-col gap-1">
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
      {jobs.map((job) => (
        <Button
          key={job.id}
          className="h-auto min-h-9 justify-start py-1.5 text-left whitespace-normal break-all"
          variant={job.id === selectedId ? "default" : "ghost"}
          aria-current={job.id === selectedId ? "page" : undefined}
          onClick={() => onSelect(job.id)}
        >
          {job.id} · {job.state}
        </Button>
      ))}
      {jobs.length === 0 && !loading && !error && <p className="px-1 text-sm text-muted-foreground">No jobs found.</p>}
    </nav>
  );
}
