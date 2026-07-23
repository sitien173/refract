import {
  DaemonStatus,
  Project,
  Job,
  JobEvent,
  Target,
  ProfilesResponse,
} from './types';

export class ApiError extends Error {
  endpoint: string;
  status?: number;

  constructor(endpoint: string, statusOrCause?: number | unknown, message?: string) {
    if (typeof statusOrCause === 'number') {
      super(message || `Request to ${endpoint} failed with status ${statusOrCause}`);
      this.name = 'ApiError';
      this.endpoint = endpoint;
      this.status = statusOrCause;
    } else {
      const cause = statusOrCause;
      const causeMsg = cause instanceof Error ? cause.message : String(cause || '');
      super(
        message || `Request to ${endpoint} failed: ${causeMsg}`,
        cause ? { cause } : undefined
      );
      this.name = 'ApiError';
      this.endpoint = endpoint;
      this.cause = cause;
    }
  }
}

async function request<T>(endpoint: string, signal?: AbortSignal): Promise<T> {
  try {
    const res = await fetch(endpoint, { signal });
    if (!res.ok) {
      throw new ApiError(endpoint, res.status);
    }
    return await (res.json() as Promise<T>);
  } catch (err: unknown) {
    if (err instanceof ApiError) {
      throw err;
    }
    if (
      signal?.aborted ||
      (err instanceof Error && err.name === 'AbortError') ||
      (err as { name?: string })?.name === 'AbortError'
    ) {
      throw err;
    }
    throw new ApiError(endpoint, err);
  }
}

export function fetchStatus(signal?: AbortSignal): Promise<DaemonStatus> {
  return request<DaemonStatus>('/dashboard/api/status', signal);
}

export function fetchProjects(signal?: AbortSignal): Promise<Project[]> {
  return request<Project[]>('/dashboard/api/projects', signal);
}

export function fetchProjectJobs(
  projectId: string,
  signal?: AbortSignal
): Promise<Job[]> {
  const encodedId = encodeURIComponent(projectId);
  return request<Job[]>(`/dashboard/api/projects/${encodedId}/jobs`, signal);
}

export function fetchJob(
  jobId: string,
  signal?: AbortSignal
): Promise<Job> {
  const encodedId = encodeURIComponent(jobId);
  return request<Job>(`/dashboard/api/jobs/${encodedId}`, signal);
}

export function fetchJobEvents(
  jobId: string,
  signal?: AbortSignal
): Promise<JobEvent[]> {
  const encodedId = encodeURIComponent(jobId);
  return request<JobEvent[]>(`/dashboard/api/jobs/${encodedId}/events`, signal);
}

export function fetchTargets(signal?: AbortSignal): Promise<Target[]> {
  return request<Target[]>('/dashboard/api/targets', signal);
}

export function fetchProfiles(signal?: AbortSignal): Promise<ProfilesResponse> {
  return request<ProfilesResponse>('/dashboard/api/profiles', signal);
}
