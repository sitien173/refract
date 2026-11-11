import { formatRelativeTime, getProjectName, shortCardId } from "./board";

export type JobLike = {
  id: string;
  workflow: string | null;
  session?: string | null;
  target: string | null;
  updated_at?: string;
  created_at?: string;
};

export type JobLabelResult = {
  title: string;
  meta: string;
};

export type ProjectGroup<T> = {
  root: string;
  name: string;
  items: T[];
};

export function jobLabel(job: JobLike, now?: number): JobLabelResult {
  const workflow = job.workflow || "job";
  const title = job.session ? `${workflow} · ${job.session}` : workflow;

  const parts: string[] = [];
  if (job.target) parts.push(job.target);
  if (job.updated_at && !Number.isNaN(Date.parse(job.updated_at))) parts.push(formatRelativeTime(job.updated_at, now));
  if (job.id) parts.push(shortCardId(job.id));

  return {
    title,
    meta: parts.join(" · "),
  };
}

export function groupByProject<T>(items: readonly T[], rootOf: (item: T) => string | null | undefined): ProjectGroup<T>[] {
  const map = new Map<string, ProjectGroup<T>>();
  for (const item of items) {
    const root = rootOf(item) || "";
    let group = map.get(root);
    if (!group) {
      group = { root, name: root ? getProjectName(root) : "No project", items: [] };
      map.set(root, group);
    }
    group.items.push(item);
  }
  return [...map.values()];
}
