import { Button } from "@/components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import type { JobDetail as Detail, JobPage, JobSummary, OutputPage } from "../api";
import { JobDetail } from "../components/JobDetail";
import { JobFilters } from "../components/JobFilters";
import { JobList } from "../components/JobList";

export type ConsoleViewProps = {
  jobs: JobSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  filters: Record<string, string>;
  options: JobPage["options"];
  onFilter: (key: string, value: string) => void;
  detail: Detail | null;
  events: Record<string, unknown>[];
  actions: React.ReactNode;
  announcement: string;
  listLoading?: boolean;
  listError?: string | null;
  detailLoading?: boolean;
  detailError?: { status?: number; message?: string } | null;
  outputStatus?: OutputPage | null;
  outputLoading?: boolean;
  outputError?: string | null;
  nextCursor?: string | null;
  loadingMore?: boolean;
  onLoadMore?: () => void;
};

export function ConsoleView({
  jobs,
  selectedId,
  onSelect,
  filters,
  options,
  onFilter,
  detail,
  events,
  actions,
  announcement,
  listLoading,
  listError,
  detailLoading,
  detailError,
  outputStatus,
  outputLoading,
  outputError,
  nextCursor,
  loadingMore,
  onLoadMore,
}: ConsoleViewProps) {
  return (
    <section aria-label="Job console" className="flex flex-col gap-(--gap-md)">
      <JobFilters filters={filters} options={options} onChange={onFilter} />
      <ResizablePanelGroup direction="horizontal" className="flex min-h-[70vh] gap-(--gap-sm)">
        <ResizablePanel defaultSize={35} minSize={20}>
          <JobList jobs={jobs} selectedId={selectedId} onSelect={onSelect} loading={listLoading} error={listError} />
          {nextCursor && (
            <Button variant="secondary" disabled={loadingMore} onClick={onLoadMore}>
              {loadingMore ? "Loading jobs…" : "Load more jobs"}
            </Button>
          )}
        </ResizablePanel>
        <ResizableHandle aria-label="Resize job list and detail" />
        <ResizablePanel defaultSize={65} minSize={30}>
          <JobDetail
            detail={detail}
            events={events}
            actions={actions}
            loading={detailLoading}
            error={detailError}
            outputStatus={outputStatus}
            outputLoading={outputLoading}
            outputError={outputError}
          />
          <div className="tds-announcement" role="status" aria-live="polite" aria-label="Announcements">
            {announcement}
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </section>
  );
}
