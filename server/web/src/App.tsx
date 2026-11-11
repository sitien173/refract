import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import type { DashboardApiError, StatsDays } from "./api";
import { JobActions } from "./components/JobActions";
import { ViewNav } from "./components/ViewNav";
import { useBoardCards, useCardDetail, useJobDetail, useStats, useTargets } from "./hooks/queries";
import { useJobActions } from "./hooks/useJobActions";
import { useJobPages } from "./hooks/useJobPages";
import { useJobTranscript } from "./hooks/useJobTranscript";
import { type DashboardTab, jobPath, readRoute, tabUrl } from "./router";
import { BoardView } from "./views/BoardView";
import { ConsoleView } from "./views/ConsoleView";
import { InsightsView } from "./views/InsightsView";
import { TargetsView } from "./views/TargetsView";

const CONSOLE_PATH = "/dashboard/";

/** Runs a user-initiated update inside a View Transition when the browser supports it and motion is allowed. */
function withViewTransition(update: () => void) {
  const canAnimate = typeof document.startViewTransition === "function" && !matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (canAnimate) document.startViewTransition(() => flushSync(update));
  else update();
}

const messageOf = (error: unknown) => (error instanceof Error ? error.message : null);

export function App() {
  const [route, setRoute] = useState(() => readRoute());
  const [announcement, setAnnouncement] = useState("");
  const [statsDays, setStatsDays] = useState<StatsDays>(7);

  const navigate = useCallback((path: string, { keepAnnouncement = false, replace = false } = {}) => {
    if (replace) history.replaceState({}, "", path);
    else history.pushState({}, "", path);
    setRoute(readRoute(new URL(location.href)));
    if (!keepAnnouncement) setAnnouncement("");
  }, []);

  const clearSelection = useCallback(() => {
    navigate(CONSOLE_PATH + location.search, { keepAnnouncement: true, replace: true });
    setAnnouncement("Job not found");
  }, [navigate]);

  const clearCardSelection = useCallback(() => {
    const url = new URL(location.href);
    url.searchParams.delete("card");
    navigate(url.pathname + (url.search ? url.search : ""), { keepAnnouncement: true, replace: true });
    setAnnouncement("Card not found");
  }, [navigate]);

  const pages = useJobPages(route.filters, undefined, route.view !== "board" && route.view !== "insights");

  const detailQuery = useJobDetail(route.jobId, { onNotFound: clearSelection });
  const detail = detailQuery.data?.id === route.jobId ? detailQuery.data : null;
  const detailError = detailQuery.error instanceof Error ? { status: (detailQuery.error as DashboardApiError).status, message: detailQuery.error.message } : null;

  const targetsQuery = useTargets({ enabled: route.view === "targets" });
  const targets = targetsQuery.data?.targets ?? [];
  const config = targetsQuery.data?.config ?? null;
  const targetsLoading = targetsQuery.isLoading;
  const targetsError = targetsQuery.error ? (messageOf(targetsQuery.error) ?? "Unable to load targets.") : null;

  const boardQuery = useBoardCards(route.filters.project, { enabled: route.view === "board" });
  const boardCards = boardQuery.data?.cards ?? [];
  const boardOptions = boardQuery.data?.options ?? { projects: [] };
  const boardLoading = boardQuery.isLoading;
  const boardError = boardQuery.error ? (messageOf(boardQuery.error) ?? "Unable to load board.") : null;
  const boardTruncated = boardQuery.data?.truncated ?? false;

  const statsQuery = useStats(statsDays, { enabled: route.view === "insights" });
  const statsError = statsQuery.error ? (messageOf(statsQuery.error) ?? "Unable to load insights.") : null;

  const cardQuery = useCardDetail(route.cardId, { onNotFound: clearCardSelection });
  const cardDetail = cardQuery.data?.card.id === route.cardId ? cardQuery.data : null;
  const cardError = cardQuery.error instanceof Error ? { status: (cardQuery.error as DashboardApiError).status, message: cardQuery.error.message } : null;

  const output = useJobTranscript(route.jobId);

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

  const prevListErrorRef = useRef<unknown>(null);
  useEffect(() => {
    if (pages.error && !prevListErrorRef.current) {
      setAnnouncement(messageOf(pages.error) ?? "Failed to refresh jobs.");
    }
    prevListErrorRef.current = pages.error;
  }, [pages.error]);

  const selectJob = useCallback((id: string) => withViewTransition(() => navigate(jobPath(id) + location.search)), [navigate]);

  const changeTab = useCallback((tab: DashboardTab) => {
    withViewTransition(() => {
      const url = tabUrl(new URL(location.href), tab);
      history.replaceState({}, "", url);
      setRoute(readRoute(url));
    });
  }, []);

  const followRetry = useCallback((id: string) => navigate(jobPath(id) + location.search, { keepAnnouncement: true }), [navigate]);

  const jobActions = useJobActions({
    jobId: route.jobId,
    announce: setAnnouncement,
    onRetried: followRetry,
  });

  const changeFilter = useCallback((key: string, value: string) => {
    const url = new URL(location.href);
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
    url.searchParams.delete("cursor");
    history.replaceState({}, "", url);
    setRoute(readRoute(url));
  }, []);

  if (route.view === "targets") {
    return <TargetsView targets={targets} config={config} loading={targetsLoading} error={targetsError} onNavigate={navigate} />;
  }

  if (route.view === "insights") {
    return <InsightsView stats={statsQuery.data ?? null} days={statsDays} loading={statsQuery.isLoading} error={statsError} onDaysChange={setStatsDays} onNavigate={navigate} />;
  }

  if (route.view === "board") {
    return (
      <BoardView
        cards={boardCards}
        options={boardOptions}
        loading={boardLoading}
        error={boardError}
        project={route.filters.project}
        truncated={boardTruncated}
        onProjectChange={(value) => changeFilter("project", value)}
        onNavigate={navigate}
        cardId={route.cardId}
        cardDetail={cardDetail}
        cardLoading={cardQuery.isLoading}
        cardError={cardError}
        announcement={announcement}
      />
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-[1600px] flex-col gap-4 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Refract dashboard</h1>
        <ViewNav current="console" onNavigate={navigate} />
      </header>
      <ConsoleView
        jobs={pages.jobs}
        selectedId={route.jobId}
        onSelect={selectJob}
        filters={route.filters}
        options={pages.options}
        onFilter={changeFilter}
        detail={detail}
        events={output.rows}
        tab={route.tab}
        onTabChange={changeTab}
        announcement={announcement}
        listLoading={pages.loading}
        listError={messageOf(pages.error)}
        detailLoading={detailQuery.isLoading}
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
