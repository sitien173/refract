import type { JobDetail as Detail, OutputPage } from "../api";
import { TranscriptView } from "./TranscriptView";

type DetailError = { status?: number; message?: string };

type JobDetailProps = {
  detail: Detail | null;
  events: Record<string, unknown>[];
  actions: React.ReactNode;
  loading?: boolean;
  error?: DetailError | null;
  outputStatus?: OutputPage | null;
  outputLoading?: boolean;
  outputError?: string | null;
};

function ErrorPanel({ error }: { error: DetailError }) {
  return (
    <section aria-label="Job detail">
      <div role="alert" className="tds-announcement tds-announcement--error">
        {error.status === 404 ? "Job not found." : (error.message ?? "Unable to load job.")}
      </div>
    </section>
  );
}

export function JobDetail({ detail, events, actions, loading, error, outputStatus, outputLoading, outputError }: JobDetailProps) {
  // A failed first load replaces the pane; a failed refresh keeps the last good detail.
  if (error && !detail) return <ErrorPanel error={error} />;
  if (loading && !detail) {
    return (
      <section aria-label="Job detail">
        <p role="status">Loading job…</p>
      </section>
    );
  }
  if (!detail) {
    return (
      <section aria-label="Job detail">
        <p>Select a job to view its details.</p>
      </section>
    );
  }
  return (
    <section aria-label="Job detail" className="flex flex-col gap-(--gap-md)">
      {error && (
        <div role="status" className="tds-announcement tds-announcement--warning">
          Showing the last loaded details. Refreshing failed: {error.message ?? "Unable to refresh job."}
        </div>
      )}
      <h2 className="text-heading-lg">Job {detail.id}</h2>
      <p>{detail.state}</p>
      <dl>
        <dt>Workflow</dt>
        <dd>{detail.workflow ?? "Not specified"}</dd>
        <dt>Target</dt>
        <dd>{detail.target ?? "Not specified"}</dd>
      </dl>
      {actions}
      <p className="whitespace-pre-wrap">{detail.result?.text ?? detail.prompt}</p>
      {outputError && (
        <div role="alert" className="tds-announcement tds-announcement--error">
          {outputError}
        </div>
      )}
      {outputLoading && <p role="status">Loading output…</p>}
      {outputStatus?.available === false && <p role="status">Output is not available.</p>}
      <TranscriptView events={events} />
    </section>
  );
}
