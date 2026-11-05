import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { JobActions } from "./components/JobActions";
import { getJob, getTargets, isTerminalJobState, type ConfigHealth, type DashboardApiError, type JobDetail, type TargetView } from "./api";
import { jobPath, readRoute } from "./router";
import { useJobActions } from "./hooks/useJobActions";
import { useJobOutput } from "./hooks/useJobOutput";
import { useJobPages } from "./hooks/useJobPages";
import { usePolling } from "./hooks/usePolling";
import { ConsoleView } from "./views/ConsoleView";
import { TargetsView } from "./views/TargetsView";

const CONSOLE_PATH = "/dashboard/";
const TARGETS_PATH = "/dashboard/targets";

const loadDetail = (key: string) => {
  const [id] = JSON.parse(key) as [string, number];
  return getJob(id);
};
const isJobActive = (detail: JobDetail) => !isTerminalJobState(detail.state);
const messageOf = (error: unknown) => (error instanceof Error ? error.message : null);

export function App() {
  const [route, setRoute] = useState(() => readRoute());
  const [announcement, setAnnouncement] = useState("");
  const [detailRevision, setDetailRevision] = useState(0);

  const [targets, setTargets] = useState<TargetView[]>([]);
  const [config, setConfig] = useState<ConfigHealth | null>(null);
  const [targetsLoading, setTargetsLoading] = useState(false);
  const [targetsError, setTargetsError] = useState<string | null>(null);

  const pages = useJobPages(route.filters);

  // Detail polling stops once the job is terminal; a key change (job or revision) restarts it.
  const detailKey = route.jobId ? JSON.stringify([route.jobId, detailRevision]) : null;
  const detailPoll = usePolling(detailKey, loadDetail, 1000, isJobActive);
  const detail = detailPoll.value?.id === route.jobId ? detailPoll.value : null;
  const detailError = detailPoll.error instanceof Error ? { status: (detailPoll.error as DashboardApiError).status, message: detailPoll.error.message } : null;

  const output = useJobOutput(route.jobId);

  useEffect(() => {
    const onPopState = () => {
      setRoute(readRoute());
      setAnnouncement("");
    };
    addEventListener("popstate", onPopState);
    return () => removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (pages.loadMoreError) setAnnouncement(pages.loadMoreError);
  }, [pages.loadMoreError]);

  useEffect(() => {
    if (route.view !== "targets") return;
    let active = true;
    setTargetsLoading(true);
    setTargetsError(null);
    setConfig(null);
    getTargets()
      .then((data) => {
        if (!active) return;
        setTargets(data.targets);
        setConfig(data.config);
      })
      .catch((error) => {
        if (active) setTargetsError(messageOf(error) ?? "Unable to load targets.");
      })
      .finally(() => {
        if (active) setTargetsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [route.view]);

  const navigate = (path: string, { keepAnnouncement = false } = {}) => {
    history.pushState({}, "", path);
    setRoute(readRoute(new URL(location.href)));
    if (!keepAnnouncement) setAnnouncement("");
  };
  const selectJob = (id: string) => navigate(jobPath(id) + location.search);
  // Automatic navigation after a retry must not erase that retry's own announcement.
  const followRetry = useCallback((id: string) => navigate(jobPath(id) + location.search, { keepAnnouncement: true }), []);
  const refreshDetail = useCallback(() => setDetailRevision((value) => value + 1), []);

  const jobActions = useJobActions({
    jobId: route.jobId,
    announce: setAnnouncement,
    onRetried: followRetry,
    onStaleQuestion: refreshDetail,
  });

  const changeFilter = (key: string, value: string) => {
    const url = new URL(location.href);
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
    url.searchParams.delete("cursor");
    history.replaceState({}, "", url);
    setRoute(readRoute(url));
  };

  if (route.view === "targets") {
    return (
      <TargetsView
        targets={targets}
        config={config}
        loading={targetsLoading}
        error={targetsError}
        onNavigate={() => navigate(CONSOLE_PATH)}
      />
    );
  }

  return (
    <main className="flex min-h-screen flex-col gap-(--gap-md) p-(--padding-xl)">
      <header className="flex items-center justify-between">
        <h1 className="text-heading-xl">Refract dashboard</h1>
        <Button variant="secondary" onClick={() => navigate(TARGETS_PATH)}>
          Targets
        </Button>
      </header>
      <ConsoleView
        jobs={pages.jobs}
        selectedId={route.jobId}
        onSelect={selectJob}
        filters={route.filters}
        options={pages.options}
        onFilter={changeFilter}
        detail={detail}
        events={output.events}
        announcement={announcement}
        listLoading={pages.loading}
        listError={messageOf(pages.error)}
        detailLoading={detailPoll.loading}
        detailError={detailError}
        outputStatus={output.status}
        outputLoading={output.loading}
        outputError={messageOf(output.error)}
        nextCursor={pages.nextCursor}
        loadingMore={pages.loadingMore}
        onLoadMore={() => void pages.loadMore()}
        actions={
          <JobActions
            jobId={route.jobId ?? undefined}
            state={detail?.state}
            pendingQuestion={detail?.pending_question ?? null}
            busy={jobActions.busy}
            onCancel={jobActions.cancel}
            onRetry={jobActions.retry}
            onAnswer={jobActions.answer}
          />
        }
      />
    </main>
  );
}
