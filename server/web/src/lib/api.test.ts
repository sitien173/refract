import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  fetchStatus,
  fetchProjects,
  fetchProjectJobs,
  fetchJob,
  fetchJobEvents,
  fetchTargets,
  fetchProfiles,
  ApiError,
} from './api';

describe('API client wrappers', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('fetchStatus fetches /dashboard/api/status', async () => {
    const mockStatus = { status: 'running', workers: 2, active_jobs: 1, queued_jobs: 0 };
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockStatus,
    });

    const result = await fetchStatus();
    expect(global.fetch).toHaveBeenCalledWith('/dashboard/api/status', { signal: undefined });
    expect(result).toEqual(mockStatus);
  });

  it('fetchProjects fetches /dashboard/api/projects', async () => {
    const mockProjects = [{ id: 'p1', alias: 'proj1', root: '/path', head_commit: 'abc', clean: true, created_at: '2026-01-01' }];
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockProjects,
    });

    const result = await fetchProjects();
    expect(global.fetch).toHaveBeenCalledWith('/dashboard/api/projects', { signal: undefined });
    expect(result).toEqual(mockProjects);
  });

  it('fetchProjectJobs fetches encoded project jobs path', async () => {
    const mockJobs = [{ id: 'j1', project_id: 'p/1', workflow: 'wf', profile: 'default', state: 'queued', context_key: '', base_commit: '', target_id: '', attempts: 0, created_at: '', updated_at: '', result: { text: '', commit: '', error: '' } }];
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockJobs,
    });

    const result = await fetchProjectJobs('p/1');
    expect(global.fetch).toHaveBeenCalledWith('/dashboard/api/projects/p%2F1/jobs', { signal: undefined });
    expect(result).toEqual(mockJobs);
  });

  it('fetchJob fetches encoded job detail path with signal', async () => {
    const controller = new AbortController();
    const mockJob = { id: 'j1', project_id: 'p1', workflow: 'wf', profile: 'default', state: 'running', context_key: '', base_commit: '', target_id: '', attempts: 0, created_at: '', updated_at: '', result: { text: '', commit: '', error: '' } };
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockJob,
    });

    const result = await fetchJob('j/1', controller.signal);
    expect(global.fetch).toHaveBeenCalledWith('/dashboard/api/jobs/j%2F1', { signal: controller.signal });
    expect(result).toEqual(mockJob);
  });

  it('fetchJobEvents fetches encoded job events path', async () => {
    const mockEvents = [{ id: 1, created_at: '2026-01-01', kind: 'job.started', data: { detail: 'start' } }];
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockEvents,
    });

    const result = await fetchJobEvents('j1');
    expect(global.fetch).toHaveBeenCalledWith('/dashboard/api/jobs/j1/events', { signal: undefined });
    expect(result).toEqual(mockEvents);
  });

  it('fetchTargets fetches /dashboard/api/targets', async () => {
    const mockTargets = [{ id: 't1', model: 'claude-3-5-sonnet', capabilities: ['tool'], max_concurrency: 1, active: 0, healthy: true, circuit_open_until: '' }];
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockTargets,
    });

    const result = await fetchTargets();
    expect(global.fetch).toHaveBeenCalledWith('/dashboard/api/targets', { signal: undefined });
    expect(result).toEqual(mockTargets);
  });

  it('fetchProfiles fetches /dashboard/api/profiles', async () => {
    const mockProfiles = { default: 'standard', available: ['standard', 'fast'] };
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => mockProfiles,
    });

    const result = await fetchProfiles();
    expect(global.fetch).toHaveBeenCalledWith('/dashboard/api/profiles', { signal: undefined });
    expect(result).toEqual(mockProfiles);
  });

  it('rejects transport failures with endpoint and original cause', async () => {
    const cause = new TypeError('network unavailable');
    (global.fetch as any).mockRejectedValueOnce(cause);

    try {
      await fetchStatus();
      throw new Error('expected fetchStatus to reject');
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.endpoint).toBe('/dashboard/api/status');
      expect(err.status).toBeUndefined();
      expect(err.cause).toBe(cause);
    }
  });

  it('rejects JSON decode failures with endpoint and original cause', async () => {
    const cause = new SyntaxError('invalid JSON');
    (global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: async () => {
        throw cause;
      },
    });

    try {
      await fetchStatus();
      throw new Error('expected fetchStatus to reject');
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.endpoint).toBe('/dashboard/api/status');
      expect(err.status).toBeUndefined();
      expect(err.cause).toBe(cause);
    }
  });

  it('rejects with ApiError containing endpoint and HTTP status on non-ok response', async () => {
    (global.fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    });

    await expect(fetchJob('j999')).rejects.toThrow(ApiError);
    await (global.fetch as any).mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
    });
    try {
      await fetchJob('j999');
    } catch (err: any) {
      expect(err).toBeInstanceOf(ApiError);
      expect(err.endpoint).toBe('/dashboard/api/jobs/j999');
      expect(err.status).toBe(404);
    }
  });

  it('rethrows original abort error unchanged when request signal is aborted', async () => {
    const abortError = new DOMException('The operation was aborted.', 'AbortError');
    (global.fetch as any).mockRejectedValue(abortError);

    const controller = new AbortController();
    controller.abort();

    await expect(fetchJob('j1', controller.signal)).rejects.toBe(abortError);
    try {
      await fetchJob('j1', controller.signal);
    } catch (err: any) {
      expect(err).not.toBeInstanceOf(ApiError);
      expect(err).toBe(abortError);
    }
  });
});
