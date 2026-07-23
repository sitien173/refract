import { useQuery, useQueries } from '@tanstack/react-query';
import {
  fetchStatus,
  fetchProjects,
  fetchProjectJobs,
  fetchJob,
  fetchJobEvents,
  fetchTargets,
  fetchProfiles,
} from './api';
import { Job } from './types';

export const GENERAL_POLL_INTERVAL = 3000;
export const JOB_DETAIL_POLL_INTERVAL = 2000;

export const queryKeys = {
  all: ['dashboard'] as const,
  status: () => [...queryKeys.all, 'status'] as const,
  projects: () => [...queryKeys.all, 'projects'] as const,
  projectJobs: (projectId: string) => [...queryKeys.all, 'projects', projectId, 'jobs'] as const,
  job: (jobId: string) => [...queryKeys.all, 'jobs', jobId] as const,
  jobEvents: (jobId: string) => [...queryKeys.all, 'jobs', jobId, 'events'] as const,
  targets: () => [...queryKeys.all, 'targets'] as const,
  profiles: () => [...queryKeys.all, 'profiles'] as const,
};

const defaultQueryOptions = {
  refetchIntervalInBackground: false,
  refetchOnWindowFocus: 'always' as const,
  retry: false,
};

export function useStatus() {
  return useQuery({
    queryKey: queryKeys.status(),
    queryFn: ({ signal }) => fetchStatus(signal),
    refetchInterval: GENERAL_POLL_INTERVAL,
    ...defaultQueryOptions,
  });
}

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects(),
    queryFn: ({ signal }) => fetchProjects(signal),
    refetchInterval: GENERAL_POLL_INTERVAL,
    ...defaultQueryOptions,
  });
}

export function useTargets() {
  return useQuery({
    queryKey: queryKeys.targets(),
    queryFn: ({ signal }) => fetchTargets(signal),
    refetchInterval: GENERAL_POLL_INTERVAL,
    ...defaultQueryOptions,
  });
}

export function useProfiles() {
  return useQuery({
    queryKey: queryKeys.profiles(),
    queryFn: ({ signal }) => fetchProfiles(signal),
    refetchInterval: GENERAL_POLL_INTERVAL,
    ...defaultQueryOptions,
  });
}

export function useJob(jobId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: ({ signal }) => fetchJob(jobId, signal),
    refetchInterval: JOB_DETAIL_POLL_INTERVAL,
    enabled: options?.enabled ?? Boolean(jobId),
    ...defaultQueryOptions,
  });
}

export function useJobEvents(jobId: string, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.jobEvents(jobId),
    queryFn: ({ signal }) => fetchJobEvents(jobId, signal),
    refetchInterval: JOB_DETAIL_POLL_INTERVAL,
    enabled: options?.enabled ?? Boolean(jobId),
    ...defaultQueryOptions,
  });
}

export function useAllJobs() {
  const projectsQuery = useProjects();
  const projects = projectsQuery.data ?? [];

  const jobQueries = useQueries({
    queries: projects.map((project) => ({
      queryKey: queryKeys.projectJobs(project.id),
      queryFn: ({ signal }: { signal?: AbortSignal }) => fetchProjectJobs(project.id, signal),
      refetchInterval: GENERAL_POLL_INTERVAL,
      enabled: Boolean(projectsQuery.data),
      ...defaultQueryOptions,
    })),
  });

  const jobsMap = new Map<string, Job>();
  const errors: Array<{ projectId: string; error: unknown }> = [];

  jobQueries.forEach((query, index) => {
    const project = projects[index];
    if (query.data) {
      query.data.forEach((job) => jobsMap.set(job.id, job));
    }
    if (query.isError && project) {
      errors.push({ projectId: project.id, error: query.error });
    }
  });

  const jobs = Array.from(jobsMap.values()).sort((a, b) => {
    const timeA = new Date(a.created_at).getTime();
    const timeB = new Date(b.created_at).getTime();
    if (timeB !== timeA) {
      return timeB - timeA;
    }
    return a.id.localeCompare(b.id);
  });

  const hasProjectsData = projectsQuery.data !== undefined;

  let hasData = false;
  let isInitialLoading = false;
  let isInitialError = false;
  let hasPartialFailure = false;
  let hasRefetchError = false;

  if (!hasProjectsData) {
    isInitialLoading = projectsQuery.isLoading;
    isInitialError = projectsQuery.isError;
  } else if (projects.length === 0) {
    hasData = true;
    hasRefetchError = projectsQuery.isError;
  } else {
    const numWithData = jobQueries.filter((q) => q.data !== undefined).length;
    const numFailedNoData = jobQueries.filter((q) => q.isError && q.data === undefined).length;
    const numPendingNoData = jobQueries.filter((q) => q.data === undefined && !q.isError).length;
    const numRefetchError = jobQueries.filter((q) => q.data !== undefined && q.isError).length;

    isInitialLoading = numPendingNoData > 0;
    isInitialError = !isInitialLoading && numFailedNoData === projects.length && numWithData === 0;
    hasPartialFailure =
      !isInitialLoading && !isInitialError && numWithData > 0 && numFailedNoData > 0;
    hasRefetchError =
      !isInitialLoading &&
      !isInitialError &&
      !hasPartialFailure &&
      (projectsQuery.isError || numRefetchError > 0);
    hasData = numWithData > 0;
  }

  const isLoading = isInitialLoading;
  const isFetching = projectsQuery.isFetching || jobQueries.some((q) => q.isFetching);
  const isError = isInitialError || errors.length > 0;

  return {
    jobs,
    isLoading,
    isFetching,
    isError,
    errors,
    projectsQuery,
    jobQueries,
    hasData,
    isInitialLoading,
    isInitialError,
    hasPartialFailure,
    hasRefetchError,
  };
}
