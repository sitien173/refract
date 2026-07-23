import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  useStatus,
  useProjects,
  useJob,
  useJobEvents,
  useTargets,
  useProfiles,
  useAllJobs,
  GENERAL_POLL_INTERVAL,
  JOB_DETAIL_POLL_INTERVAL,
  queryKeys,
} from './queries';
import * as api from './api';

vi.mock('./api');

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('TanStack Query hooks and polling policies', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('queryKeys produces correct hierarchical keys', () => {
    expect(queryKeys.status()).toEqual(['dashboard', 'status']);
    expect(queryKeys.projects()).toEqual(['dashboard', 'projects']);
    expect(queryKeys.projectJobs('p1')).toEqual(['dashboard', 'projects', 'p1', 'jobs']);
    expect(queryKeys.job('j1')).toEqual(['dashboard', 'jobs', 'j1']);
    expect(queryKeys.jobEvents('j1')).toEqual(['dashboard', 'jobs', 'j1', 'events']);
    expect(queryKeys.targets()).toEqual(['dashboard', 'targets']);
    expect(queryKeys.profiles()).toEqual(['dashboard', 'profiles']);
  });

  it('constants match requirements (3000ms general, 2000ms job detail)', () => {
    expect(GENERAL_POLL_INTERVAL).toBe(3000);
    expect(JOB_DETAIL_POLL_INTERVAL).toBe(2000);
  });

  it('useStatus calls fetchStatus', async () => {
    const mockStatus = { status: 'running', workers: 2, active_jobs: 1, queued_jobs: 0 };
    vi.mocked(api.fetchStatus).mockResolvedValueOnce(mockStatus as any);

    const { result } = renderHook(() => useStatus(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockStatus);
    expect(api.fetchStatus).toHaveBeenCalled();
  });

  it('useProjects, useTargets, and useProfiles call their respective API endpoints', async () => {
    vi.mocked(api.fetchProjects).mockResolvedValueOnce([]);
    vi.mocked(api.fetchTargets).mockResolvedValueOnce([]);
    vi.mocked(api.fetchProfiles).mockResolvedValueOnce({ default: 'def', available: [] });

    const wrapper = createWrapper();
    const { result: pRes } = renderHook(() => useProjects(), { wrapper });
    const { result: tRes } = renderHook(() => useTargets(), { wrapper });
    const { result: prRes } = renderHook(() => useProfiles(), { wrapper });

    await waitFor(() => expect(pRes.current.isSuccess).toBe(true));
    await waitFor(() => expect(tRes.current.isSuccess).toBe(true));
    await waitFor(() => expect(prRes.current.isSuccess).toBe(true));

    expect(api.fetchProjects).toHaveBeenCalled();
    expect(api.fetchTargets).toHaveBeenCalled();
    expect(api.fetchProfiles).toHaveBeenCalled();
  });

  it('useJob and useJobEvents observe enabled option', async () => {
    const mockJob = { id: 'j1', state: 'running' };
    const mockEvents = [{ id: 1, kind: 'started', data: {} }];
    vi.mocked(api.fetchJob).mockResolvedValue(mockJob as any);
    vi.mocked(api.fetchJobEvents).mockResolvedValue(mockEvents as any);

    const { result: jobResult } = renderHook(
      () => useJob('j1', { enabled: false }),
      { wrapper: createWrapper() }
    );

    expect(jobResult.current.fetchStatus).toBe('idle');
    expect(api.fetchJob).not.toHaveBeenCalled();

    const { result: eventsResult } = renderHook(
      () => useJobEvents('j1', { enabled: true }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => expect(eventsResult.current.isSuccess).toBe(true));
    expect(eventsResult.current.data).toEqual(mockEvents);
    expect(api.fetchJobEvents).toHaveBeenCalledWith('j1', expect.anything());
  });

  it('useAllJobs merges project jobs, sorts newest first with id tie-breaker, and preserves partial data on error', async () => {
    const mockProjects = [
      { id: 'p1', alias: 'proj1', root: '/p1', head_commit: '1', clean: true, created_at: '2026-01-01' },
      { id: 'p2', alias: 'proj2', root: '/p2', head_commit: '2', clean: true, created_at: '2026-01-01' },
    ];
    const mockP1Jobs = [
      { id: 'j-old', project_id: 'p1', created_at: '2026-01-01T10:00:00Z', workflow: 'wf', profile: '', state: 'succeeded', context_key: '', base_commit: '', target_id: '', attempts: 1, updated_at: '', result: { text: '', commit: '', error: '' } },
      { id: 'j-tie2', project_id: 'p1', created_at: '2026-01-01T12:00:00Z', workflow: 'wf', profile: '', state: 'running', context_key: '', base_commit: '', target_id: '', attempts: 1, updated_at: '', result: { text: '', commit: '', error: '' } },
    ];

    vi.mocked(api.fetchProjects).mockResolvedValue(mockProjects as any);
    vi.mocked(api.fetchProjectJobs).mockImplementation((projectId) => {
      if (projectId === 'p1') return Promise.resolve(mockP1Jobs as any);
      return Promise.reject(new api.ApiError('/dashboard/api/projects/p2/jobs', 500));
    });

    const { result } = renderHook(() => useAllJobs(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.jobs.length).toBe(2));

    expect(result.current.jobs.map(j => j.id)).toEqual(['j-tie2', 'j-old']);
    expect(result.current.errors.length).toBe(1);
    expect(result.current.errors[0].projectId).toBe('p2');
  });
});
