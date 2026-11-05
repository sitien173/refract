export type DashboardRoute = {
  view: "targets" | "console";
  jobId: string | null;
  filters: Record<string, string>;
};

const FILTER_KEYS = ["state", "project", "workflow", "target", "q"];
const JOB_PATH = /^\/dashboard\/jobs\/([^/]+)\/?$/;

export function readRoute(url = new URL(window.location.href)): DashboardRoute {
  const match = url.pathname.match(JOB_PATH);
  const filters: Record<string, string> = {};
  for (const key of FILTER_KEYS) {
    const value = url.searchParams.get(key);
    if (value) filters[key] = value;
  }
  const isTargets = url.pathname === "/dashboard/targets" || url.pathname === "/dashboard/targets/";
  return {
    view: isTargets ? "targets" : "console",
    jobId: match ? decodeURIComponent(match[1]!) : null,
    filters,
  };
}

export function jobPath(id: string): string {
  return `/dashboard/jobs/${encodeURIComponent(id)}`;
}
