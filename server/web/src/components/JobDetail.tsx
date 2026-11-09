import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { JobDetail as Detail, OutputPage } from "../api";
import { type DashboardTab, TABS } from "../router";
import type { TranscriptRow } from "../transcript/reduce";
import { TranscriptView } from "./TranscriptView";

type DetailError = { status?: number; message?: string };

type JobDetailProps = {
  detail: Detail | null;
  events: readonly TranscriptRow[];
  tab: DashboardTab;
  onTabChange: (tab: DashboardTab) => void;
  actions: React.ReactNode;
  loading?: boolean;
  error?: DetailError | null;
  outputStatus?: OutputPage | null;
  outputLoading?: boolean;
  outputError?: string | null;
};

const TAB_LABELS: Record<DashboardTab, string> = { transcript: "Transcript", prompt: "Prompt", result: "Result", metadata: "Metadata" };

function metadataRows(detail: Detail): [string, string | number | null | undefined][] {
  return [
    ["State", detail.state],
    ["Project", detail.project_id],
    ["Project root", detail.project_root],
    ["Workflow", detail.workflow],
    ["Profile", detail.profile],
    ["Target", detail.target],
    ["Session", detail.session],
    ["Retry of", detail.retry_of],
    ["Created", detail.created_at],
    ["Updated", detail.updated_at],
    ["Started", detail.started_at],
    ["Finished", detail.finished_at],
    ["Model", detail.result?.model],
    ["Duration (ms)", detail.result?.duration_ms],
    ["Failure kind", detail.failure_kind],
    ["Error", detail.result?.error],
  ];
}

function ErrorPanel({ error }: { error: DetailError }) {
  return (
    <section aria-label="Job detail">
      <div role="alert" className="callout callout-error">
        {error.status === 404 ? "Job not found." : (error.message ?? "Unable to load job.")}
      </div>
    </section>
  );
}

export function JobDetail({ detail, events, tab, onTabChange, actions, loading, error, outputStatus, outputLoading, outputError }: JobDetailProps) {
  // A failed first load replaces the pane; a failed refresh keeps the last good detail.
  if (error && !detail) return <ErrorPanel error={error} />;
  if (loading && !detail) {
    return (
      <section aria-label="Job detail">
        <p role="status" className="text-sm text-muted-foreground">
          Loading job…
        </p>
      </section>
    );
  }
  if (!detail) {
    return (
      <section aria-label="Job detail">
        <p className="text-sm text-muted-foreground">Select a job to view its details.</p>
      </section>
    );
  }
  return (
    <section aria-label="Job detail" className="flex flex-col gap-4">
      {error && (
        <div role="status" className="callout callout-warning">
          Showing the last loaded details. Refreshing failed: {error.message ?? "Unable to refresh job."}
        </div>
      )}
      <h2 className="text-xl font-semibold tracking-tight break-all">Job {detail.id}</h2>
      <p className="text-sm font-medium text-muted-foreground">{detail.state}</p>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-muted-foreground">Workflow</dt>
        <dd>{detail.workflow ?? "Not specified"}</dd>
        <dt className="text-muted-foreground">Target</dt>
        <dd>{detail.target ?? "Not specified"}</dd>
      </dl>
      {actions}
      {outputError && (
        <div role="alert" className="callout callout-error">
          {outputError}
        </div>
      )}
      {outputLoading && (
        <p role="status" className="text-sm text-muted-foreground">
          Loading output…
        </p>
      )}
      {outputStatus?.available === false && (
        <p role="status" className="text-sm text-muted-foreground">
          Output unavailable
        </p>
      )}
      <Tabs value={tab} onValueChange={(value) => onTabChange(value as DashboardTab)}>
        <TabsList aria-label="Job sections">
          {TABS.map((value) => (
            <TabsTrigger key={value} value={value}>
              {TAB_LABELS[value]}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="transcript" keepMounted aria-label="Transcript">
          <TranscriptView rows={events} />
        </TabsContent>
        <TabsContent value="prompt" aria-label="Prompt">
          <p className="whitespace-pre-wrap text-sm">{detail.prompt}</p>
        </TabsContent>
        <TabsContent value="result" aria-label="Result">
          <p className="whitespace-pre-wrap text-sm">{detail.result?.text ?? "No result yet."}</p>
        </TabsContent>
        <TabsContent value="metadata" aria-label="Metadata">
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            {metadataRows(detail).map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="break-all">{value ?? "Not specified"}</dd>
              </div>
            ))}
          </dl>
        </TabsContent>
      </Tabs>
    </section>
  );
}
