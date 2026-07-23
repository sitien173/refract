import React from 'react';
import fs from 'fs';
import path from 'path';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { focusManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
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

async function flushQuery() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    vi.advanceTimersByTime(0);
    await Promise.resolve();
  });
}

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
    focusManager.setFocused(true);
    vi.useRealTimers();
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

  it('polls status every 3000ms while mounted', async () => {
    vi.useFakeTimers();
    vi.mocked(api.fetchStatus).mockResolvedValue({
      status: 'running',
      workers: 1,
      active_jobs: 1,
      queued_jobs: 0,
    });

    const { result } = renderHook(() => useStatus(), { wrapper: createWrapper() });
    expect(api.fetchStatus).toHaveBeenCalledTimes(1);
    await flushQuery();
    expect(result.current.isSuccess).toBe(true);
    expect(api.fetchStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(2999);
      await Promise.resolve();
    });
    expect(api.fetchStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(1);
      await Promise.resolve();
    });
    await flushQuery();
    expect(api.fetchStatus).toHaveBeenCalledTimes(2);
  });

  it('polls enabled job detail and events every 2000ms', async () => {
    vi.useFakeTimers();
    vi.mocked(api.fetchJob).mockResolvedValue({ id: 'j1', state: 'running' } as any);
    vi.mocked(api.fetchJobEvents).mockResolvedValue([{ id: 1 }] as any);

    const { result } = renderHook(
      () => ({
        job: useJob('j1', { enabled: true }),
        events: useJobEvents('j1', { enabled: true }),
      }),
      { wrapper: createWrapper() }
    );
    await flushQuery();
    expect(result.current.job.isSuccess).toBe(true);
    expect(result.current.events.isSuccess).toBe(true);
    expect(api.fetchJob).toHaveBeenCalledTimes(1);
    expect(api.fetchJobEvents).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(1999);
      await Promise.resolve();
    });
    expect(api.fetchJob).toHaveBeenCalledTimes(1);
    expect(api.fetchJobEvents).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(1);
      await Promise.resolve();
    });
    await flushQuery();
    expect(api.fetchJob).toHaveBeenCalledTimes(2);
    expect(api.fetchJobEvents).toHaveBeenCalledTimes(2);
  });

  it('suppresses polling while the window is hidden', async () => {
    vi.useFakeTimers();
    vi.mocked(api.fetchStatus).mockResolvedValue({
      status: 'running',
      workers: 1,
      active_jobs: 0,
      queued_jobs: 0,
    });

    const { result } = renderHook(() => useStatus(), { wrapper: createWrapper() });
    await flushQuery();
    expect(result.current.isSuccess).toBe(true);
    focusManager.setFocused(false);

    await act(async () => {
      vi.advanceTimersByTime(6000);
      await Promise.resolve();
    });
    expect(api.fetchStatus).toHaveBeenCalledTimes(1);
    focusManager.setFocused(true);
    await flushQuery();
  });

  it('refetches immediately when window visibility is restored', async () => {
    vi.useFakeTimers();
    vi.mocked(api.fetchStatus).mockResolvedValue({
      status: 'running',
      workers: 1,
      active_jobs: 0,
      queued_jobs: 0,
    });

    const { result } = renderHook(() => useStatus(), { wrapper: createWrapper() });
    await flushQuery();
    expect(result.current.isSuccess).toBe(true);
    focusManager.setFocused(false);
    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
    });
    expect(api.fetchStatus).toHaveBeenCalledTimes(1);

    focusManager.setFocused(true);
    await flushQuery();
    expect(api.fetchStatus).toHaveBeenCalledTimes(2);
  });

  it('stops disabled job polling and unmounted job polling', async () => {
    vi.useFakeTimers();
    vi.mocked(api.fetchJob).mockResolvedValue({ id: 'j1', state: 'running' } as any);

    const disabled = renderHook(() => useJob('j1', { enabled: false }), {
      wrapper: createWrapper(),
    });
    await act(async () => {
      vi.advanceTimersByTime(4000);
      await Promise.resolve();
    });
    expect(api.fetchJob).not.toHaveBeenCalled();
    disabled.unmount();

    const mounted = renderHook(() => useJob('j1', { enabled: true }), {
      wrapper: createWrapper(),
    });
    await flushQuery();
    expect(mounted.result.current.isSuccess).toBe(true);
    expect(api.fetchJob).toHaveBeenCalledTimes(1);
    mounted.unmount();

    await act(async () => {
      vi.advanceTimersByTime(4000);
      await Promise.resolve();
    });
    expect(api.fetchJob).toHaveBeenCalledTimes(1);
  });

  it('retains status data and dataUpdatedAt after a failed refetch', async () => {
    vi.useFakeTimers();
    const status = {
      status: 'running' as const,
      workers: 2,
      active_jobs: 1,
      queued_jobs: 0,
    };
    vi.mocked(api.fetchStatus)
      .mockResolvedValueOnce(status)
      .mockRejectedValueOnce(new Error('temporary failure'));

    const { result } = renderHook(() => useStatus(), { wrapper: createWrapper() });
    await flushQuery();
    expect(result.current.isSuccess).toBe(true);
    const dataUpdatedAt = result.current.dataUpdatedAt;

    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
    });
    await flushQuery();
    expect(result.current.isError).toBe(true);

    expect(result.current.data).toEqual(status);
    expect(result.current.dataUpdatedAt).toBe(dataUpdatedAt);
  });

  it('useAllJobs merges project jobs, sorts newest first with deterministic ascending ID tie-breaker for equal created_at, and preserves partial data on error', async () => {
    const mockProjects = [
      { id: 'p1', alias: 'proj1', root: '/p1', head_commit: '1', clean: true, created_at: '2026-01-01' },
      { id: 'p2', alias: 'proj2', root: '/p2', head_commit: '2', clean: true, created_at: '2026-01-01' },
    ];
    // Supplied with equal created_at jobs (j-tie2 and j-tie1) in inverse ID order
    const mockP1Jobs = [
      { id: 'j-old', project_id: 'p1', created_at: '2026-01-01T10:00:00Z', workflow: 'wf', profile: '', state: 'succeeded', context_key: '', base_commit: '', target_id: '', attempts: 1, updated_at: '', result: { text: '', commit: '', error: '' } },
      { id: 'j-tie2', project_id: 'p1', created_at: '2026-01-01T12:00:00Z', workflow: 'wf', profile: '', state: 'running', context_key: '', base_commit: '', target_id: '', attempts: 1, updated_at: '', result: { text: '', commit: '', error: '' } },
      { id: 'j-tie1', project_id: 'p1', created_at: '2026-01-01T12:00:00Z', workflow: 'wf', profile: '', state: 'running', context_key: '', base_commit: '', target_id: '', attempts: 1, updated_at: '', result: { text: '', commit: '', error: '' } },
      { id: 'j-newest', project_id: 'p1', created_at: '2026-01-01T14:00:00Z', workflow: 'wf', profile: '', state: 'running', context_key: '', base_commit: '', target_id: '', attempts: 1, updated_at: '', result: { text: '', commit: '', error: '' } },
    ];

    vi.mocked(api.fetchProjects).mockResolvedValue(mockProjects as any);
    vi.mocked(api.fetchProjectJobs).mockImplementation((projectId) => {
      if (projectId === 'p1') return Promise.resolve(mockP1Jobs as any);
      return Promise.reject(new api.ApiError('/dashboard/api/projects/p2/jobs', 500));
    });

    const { result } = renderHook(() => useAllJobs(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.jobs.length).toBe(4));

    // Asserts newest-first (14:00 -> 12:00 -> 10:00) with deterministic ascending ID tie-break (j-tie1 before j-tie2)
    expect(result.current.jobs.map(j => j.id)).toEqual(['j-newest', 'j-tie1', 'j-tie2', 'j-old']);
    expect(result.current.errors.length).toBe(1);
    expect(result.current.errors[0].projectId).toBe('p2');
  });

  it('defines statusIcon mask rules explicitly without unset shorthand references', () => {
    const cssPath = path.resolve(__dirname, '../styles/app.module.css');
    const cssContent = fs.readFileSync(cssPath, 'utf8');
    const statusIconMatch = cssContent.match(/\.statusIcon\s*\{([^}]+)\}/);
    expect(statusIconMatch).not.toBeNull();
    const rules = statusIconMatch![1];
    expect(rules).not.toContain('var(--icon-url)');
    expect(rules).toContain('mask-repeat: no-repeat');
    expect(rules).toContain('-webkit-mask-repeat: no-repeat');
    expect(rules).toContain('mask-position: center');
    expect(rules).toContain('-webkit-mask-position: center');
    expect(rules).toContain('mask-size: contain');
    expect(rules).toContain('-webkit-mask-size: contain');
  });
});
