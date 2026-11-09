export const TABS = ["transcript", "prompt", "result", "metadata"] as const;
export type DashboardTab = (typeof TABS)[number];

export type DashboardRoute = {
  view: "targets" | "console" | "board";
  jobId: string | null;
  cardId: string | null;
  filters: Record<string, string>;
  tab: DashboardTab;
};

const FILTER_KEYS = ["state", "project", "workflow", "target", "q"];
const JOB_PATH = /^\/dashboard\/jobs\/([^/]+)\/?$/;

export function readRoute(url = new URL(window.location.href)): DashboardRoute {
  const jobId = url.pathname.match(JOB_PATH)?.[1];
  const filters: Record<string, string> = {};
  for (const key of FILTER_KEYS) {
    const value = url.searchParams.get(key);
    if (value) filters[key] = value;
  }
  const isTargets = url.pathname === "/dashboard/targets" || url.pathname === "/dashboard/targets/";
  const isBoard = url.pathname === "/dashboard/board" || url.pathname === "/dashboard/board/";
  const cardParam = url.searchParams.get("card");
  const tab = url.searchParams.get("tab");
  return {
    view: isBoard ? "board" : isTargets ? "targets" : "console",
    jobId: jobId ? decodeURIComponent(jobId) : null,
    cardId: isBoard && cardParam ? cardParam : null,
    filters,
    tab: TABS.find((t) => t === tab) ?? "transcript",
  };
}

export function jobPath(id: string): string {
  return `/dashboard/jobs/${encodeURIComponent(id)}`;
}

/** Returns a copy of `url` with `tab` set; the default tab is omitted. */
export function tabUrl(url: URL, tab: DashboardTab): URL {
  const next = new URL(url);
  if (tab === "transcript") next.searchParams.delete("tab");
  else next.searchParams.set("tab", tab);
  return next;
}
