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
    <nav aria-label="Jobs" className="flex flex-col gap-(--gap-sm)">
      {error && (
        <div role="alert" className="tds-announcement tds-announcement--error">
          {error}
        </div>
      )}
      {loading && <p role="status">{jobs.length ? "Refreshing jobs…" : "Loading jobs…"}</p>}
      {jobs.map((job) => (
        <Button
          key={job.id}
          variant={job.id === selectedId ? "default" : "secondary"}
          aria-current={job.id === selectedId ? "page" : undefined}
          onClick={() => onSelect(job.id)}
        >
          {job.id} · {job.state}
        </Button>
      ))}
      {jobs.length === 0 && !loading && !error && <p>No jobs found.</p>}
    </nav>
  );
}
