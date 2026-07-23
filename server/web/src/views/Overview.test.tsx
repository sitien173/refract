import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { Overview } from './Overview';
import * as queries from '../lib/queries';

vi.mock('../lib/queries', () => ({
  useStatus: vi.fn(),
  useTargets: vi.fn(),
  useProfiles: vi.fn(),
  useAllJobs: vi.fn(),
}));

describe('Overview view', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders all five summary areas with live data', () => {
    vi.mocked(queries.useStatus).mockReturnValue({
      data: { status: 'running', workers: 4, active_jobs: 2, queued_jobs: 1 },
      isLoading: false,
      isError: false,
      isFetching: false,
    } as any);

    vi.mocked(queries.useTargets).mockReturnValue({
      data: [
        { id: 't1', model: 'gpt-4o', capabilities: ['coding'], max_concurrency: 2, active: 1, healthy: true, circuit_open_until: '' },
        { id: 't2', model: 'claude-3-5-sonnet', capabilities: ['coding'], max_concurrency: 2, active: 0, healthy: false, circuit_open_until: new Date(Date.now() + 60000).toISOString() },
      ],
      isLoading: false,
      isError: false,
      isFetching: false,
    } as any);

    vi.mocked(queries.useProfiles).mockReturnValue({
      data: { default: 'standard', available: ['standard', 'fast', 'thorough'] },
      isLoading: false,
      isError: false,
      isFetching: false,
    } as any);

    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: [
        { id: 'j1', project_id: 'p1', workflow: 'wf1', profile: 'standard', state: 'running', created_at: '2026-07-23T10:00:00Z' },
        { id: 'j2', project_id: 'p1', workflow: 'wf2', profile: 'standard', state: 'succeeded', created_at: '2026-07-23T09:00:00Z' },
        { id: 'j3', project_id: 'p1', workflow: 'wf3', profile: 'standard', state: 'queued', created_at: '2026-07-23T08:00:00Z' },
        { id: 'j4', project_id: 'p1', workflow: 'wf4', profile: 'standard', state: 'failed', created_at: '2026-07-23T07:00:00Z' },
        { id: 'j5', project_id: 'p1', workflow: 'wf5', profile: 'standard', state: 'succeeded', created_at: '2026-07-23T06:00:00Z' },
        { id: 'j6', project_id: 'p1', workflow: 'wf6', profile: 'standard', state: 'succeeded', created_at: '2026-07-23T05:00:00Z' },
      ],
      isLoading: false,
      isFetching: false,
      isError: false,
      errors: [],
      projectsQuery: {
        data: [
          { id: 'p1', alias: 'main-app', root: '/app', head_commit: '123456789', clean: true, created_at: '2026-07-01T00:00:00Z' },
          { id: 'p2', alias: 'service-b', root: '/b', head_commit: 'abcdef987', clean: false, created_at: '2026-07-02T00:00:00Z' },
        ],
        isLoading: false,
        isError: false,
      },
    } as any);

    render(<Overview />);

    // Area 1: Worker / active / queued status
    expect(screen.getByText('Workers')).toBeTruthy();
    expect(screen.getByText('4')).toBeTruthy();
    expect(screen.getByText('Active Jobs')).toBeTruthy();
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
    expect(screen.getByText('Queued Jobs')).toBeTruthy();
    expect(screen.getByText('1')).toBeTruthy();

    // Area 2: Recent jobs (sliced to max 5)
    expect(screen.getByText('Recent Jobs')).toBeTruthy();
    expect(screen.getByText('j1')).toBeTruthy();
    expect(screen.getByText('j5')).toBeTruthy();
    expect(screen.queryByText('j6')).toBeNull();

    // Area 3: Target counts (Total: 2, Healthy: 1, Degraded: 1, Open Circuit: 1)
    expect(screen.getByText('Target Health')).toBeTruthy();
    expect(screen.getByText('Total Targets')).toBeTruthy();
    expect(screen.getByText('Open Circuits')).toBeTruthy();

    // Area 4: Projects summary (Total: 2, Clean: 1, Dirty: 1)
    expect(screen.getByText('Projects Summary')).toBeTruthy();

    // Area 5: Profiles summary (Default: standard, Available: 3)
    expect(screen.getByText('Profiles Summary')).toBeTruthy();
  });

  it('renders initial loading state when data is not yet available', () => {
    vi.mocked(queries.useStatus).mockReturnValue({ isLoading: true, data: undefined } as any);
    vi.mocked(queries.useTargets).mockReturnValue({ isLoading: true, data: undefined } as any);
    vi.mocked(queries.useProfiles).mockReturnValue({ isLoading: true, data: undefined } as any);
    vi.mocked(queries.useAllJobs).mockReturnValue({ isLoading: true, jobs: [], projectsQuery: { isLoading: true } } as any);

    render(<Overview />);
    expect(screen.getByRole('status')).toBeTruthy();
  });

  it('shows refetch warning banner when query is in error with cached data', () => {
    vi.mocked(queries.useStatus).mockReturnValue({
      data: { status: 'running', workers: 2, active_jobs: 0, queued_jobs: 0 },
      isError: true,
    } as any);
    vi.mocked(queries.useTargets).mockReturnValue({ data: [], isError: false } as any);
    vi.mocked(queries.useProfiles).mockReturnValue({ data: { default: 'std', available: [] }, isError: false } as any);
    vi.mocked(queries.useAllJobs).mockReturnValue({ jobs: [], isError: false, projectsQuery: { data: [] } } as any);

    render(<Overview />);
    expect(screen.getByText('Could not refresh. Showing last known data.')).toBeTruthy();
  });
});
