import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
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

  it('renders all five summary areas with live data and time dateTime elements', () => {
    vi.mocked(queries.useStatus).mockReturnValue({
      data: { status: 'running', workers: 4, active_jobs: 2, queued_jobs: 1 },
      isLoading: false,
      isError: false,
      isFetching: false,
    } as any);

    vi.mocked(queries.useTargets).mockReturnValue({
      data: [
        { id: 't1', model: 'gpt-4o', max_concurrency: 2, active: 1, healthy: true, circuit_open_until: '' },
        { id: 't2', model: 'claude-3-5-sonnet', max_concurrency: 2, active: 0, healthy: false, circuit_open_until: new Date(Date.now() + 60000).toISOString() },
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
          { id: 'p1', alias: 'main-app', root: '/app', created_at: '2026-07-01T00:00:00Z' },
          { id: 'p2', alias: 'service-b', root: '/b', created_at: '2026-07-02T00:00:00Z' },
        ],
        isLoading: false,
        isError: false,
      },
    } as any);

    const { container } = render(<Overview />);

    // Area 1: Worker / active / queued status
    expect(screen.getByText('Workers')).toBeTruthy();
    expect(screen.getByText('4')).toBeTruthy();
    expect(screen.getByText('Active Jobs')).toBeTruthy();
    expect(screen.getAllByText('2').length).toBeGreaterThan(0);
    expect(screen.getByText('Queued Jobs')).toBeTruthy();
    expect(screen.getAllByText('1').length).toBeGreaterThan(0);

    // Area 2: Recent jobs (sliced to max 5)
    expect(screen.getByText('Recent Jobs')).toBeTruthy();
    expect(screen.getByText('j1')).toBeTruthy();
    expect(screen.getByText('j5')).toBeTruthy();
    expect(screen.queryByText('j6')).toBeNull();

    // Timestamp requirement check
    const timeEl = container.querySelector('time[dateTime="2026-07-23T10:00:00Z"]');
    expect(timeEl).toBeTruthy();

    // Area 3: Target counts (Total: 2, Healthy: 1, Degraded: 1, Open Circuit: 1)
    expect(screen.getByText('Target Health')).toBeTruthy();
    expect(screen.getByText('Total Targets')).toBeTruthy();
    expect(screen.getByText('Open Circuits')).toBeTruthy();

    // Area 4: Projects summary (Total: 2, Clean: 1, Dirty: 1)
    expect(screen.getByText('Projects Summary')).toBeTruthy();

    // Area 5: Profiles summary (Default: standard, Available: standard, fast, thorough)
    expect(screen.getByText('Profiles Summary')).toBeTruthy();
    expect(screen.getAllByText('standard').length).toBeGreaterThan(0);
    expect(screen.getByText('fast')).toBeTruthy();
    expect(screen.getByText('thorough')).toBeTruthy();
    expect(screen.getByText('Default')).toBeTruthy();
  });

  it('renders mixed loaded and loading resources independently without whole-page blocking', () => {
    vi.mocked(queries.useStatus).mockReturnValue({ isLoading: true, data: undefined } as any);
    vi.mocked(queries.useTargets).mockReturnValue({
      data: [{ id: 't1', model: 'gpt-4', max_concurrency: 1, active: 0, healthy: true, circuit_open_until: '' }],
      isLoading: false,
    } as any);
    vi.mocked(queries.useProfiles).mockReturnValue({ data: { default: 'std', available: ['std'] }, isLoading: false } as any);
    vi.mocked(queries.useAllJobs).mockReturnValue({ jobs: [], isLoading: false, projectsQuery: { data: [], isLoading: false } } as any);

    render(<Overview />);

    // System Status is loading
    expect(screen.getByText('Loading system status...')).toBeTruthy();
    // Target Health panel displays loaded data
    expect(screen.getByText('Target Health')).toBeTruthy();
    expect(screen.getByText('Total Targets')).toBeTruthy();
  });

  it('renders panel initial error alongside other successful panels', () => {
    vi.mocked(queries.useStatus).mockReturnValue({ isError: true, data: undefined } as any);
    vi.mocked(queries.useTargets).mockReturnValue({
      data: [{ id: 't1', model: 'gpt-4', max_concurrency: 1, active: 0, healthy: true, circuit_open_until: '' }],
      isLoading: false,
    } as any);
    vi.mocked(queries.useProfiles).mockReturnValue({ data: { default: 'std', available: ['std'] }, isLoading: false } as any);
    vi.mocked(queries.useAllJobs).mockReturnValue({ jobs: [], isLoading: false, projectsQuery: { data: [], isLoading: false } } as any);

    render(<Overview />);

    // System Status panel shows inline error
    expect(screen.getByText('Failed to load system status.')).toBeTruthy();
    // Profiles panel shows successful data
    expect(screen.getByText('Profiles Summary')).toBeTruthy();
    expect(screen.getByText('std')).toBeTruthy();
  });

  it('renders successful empty summaries gracefully', () => {
    vi.mocked(queries.useStatus).mockReturnValue({ data: { status: 'running', workers: 0, active_jobs: 0, queued_jobs: 0 } } as any);
    vi.mocked(queries.useTargets).mockReturnValue({ data: [] } as any);
    vi.mocked(queries.useProfiles).mockReturnValue({ data: { default: '', available: [] } } as any);
    vi.mocked(queries.useAllJobs).mockReturnValue({ jobs: [], isLoading: false, projectsQuery: { data: [] } } as any);

    render(<Overview />);

    expect(screen.getByText('No recent jobs found.')).toBeTruthy();
    expect(screen.getByText('Profiles Summary')).toBeTruthy();
    expect(screen.getByText('None')).toBeTruthy();
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

  it('shows partial-results warning for useAllJobs project errors while retaining jobs', () => {
    vi.mocked(queries.useStatus).mockReturnValue({ data: { workers: 1, active_jobs: 0, queued_jobs: 0 } } as any);
    vi.mocked(queries.useTargets).mockReturnValue({ data: [] } as any);
    vi.mocked(queries.useProfiles).mockReturnValue({ data: { default: 'std', available: ['std'] } } as any);
    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: [{ id: 'j1', project_id: 'p1', workflow: 'wf1', profile: 'std', state: 'succeeded', created_at: '2026-07-23T10:00:00Z' }],
      errors: [{ projectId: 'p2', error: new Error('Failed to fetch p2 jobs') }],
      projectsQuery: { data: [{ id: 'p1' }, { id: 'p2' }] },
    } as any);

    render(<Overview />);

    expect(screen.getByText('Could not load jobs for all projects. Showing partial results.')).toBeTruthy();
    expect(screen.getByText('j1')).toBeTruthy();
  });

  it('shows refetch warning and empty state for cached empty projects with refetch error without initial error', () => {
    vi.mocked(queries.useStatus).mockReturnValue({ data: { workers: 1, active_jobs: 0, queued_jobs: 0 } } as any);
    vi.mocked(queries.useTargets).mockReturnValue({ data: [] } as any);
    vi.mocked(queries.useProfiles).mockReturnValue({ data: { default: 'std', available: [] } } as any);
    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: [],
      isError: true,
      errors: [],
      projectsQuery: { data: [], isError: true },
    } as any);

    render(<Overview />);

    expect(screen.getByText('Could not refresh. Showing last known data.')).toBeTruthy();
    expect(screen.getByText('No recent jobs found.')).toBeTruthy();
    expect(screen.queryByText('Failed to load recent jobs.')).toBeNull();
  });

  it('shows initial error when there is a true initial jobs/projects failure without cached data', () => {
    vi.mocked(queries.useStatus).mockReturnValue({ data: { workers: 1, active_jobs: 0, queued_jobs: 0 } } as any);
    vi.mocked(queries.useTargets).mockReturnValue({ data: [] } as any);
    vi.mocked(queries.useProfiles).mockReturnValue({ data: { default: 'std', available: [] } } as any);
    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: [],
      isLoading: false,
      isError: true,
      errors: [],
      projectsQuery: { data: undefined, isLoading: false, isError: true },
    } as any);

    render(<Overview />);

    expect(screen.getByText('Failed to load recent jobs.')).toBeTruthy();
    expect(screen.queryByText('Could not refresh. Showing last known data.')).toBeNull();
  });
});
