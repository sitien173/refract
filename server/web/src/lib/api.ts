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
  status: number;

  constructor(endpoint: string, status: number, message?: string) {
    super(message || `Request to ${endpoint} failed with status ${status}`);
    this.name = 'ApiError';
    this.endpoint = endpoint;
    this.status = status;
  }
}

async function request<T>(endpoint: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(endpoint, { signal });
  if (!res.ok) {
    throw new ApiError(endpoint, res.status);
  }
  return res.json() as Promise<T>;
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
