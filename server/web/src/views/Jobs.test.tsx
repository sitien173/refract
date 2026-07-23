import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Jobs } from './Jobs';
import * as queries from '../lib/queries';
import { Job } from '../lib/types';

vi.mock('../lib/queries', async () => {
  const actual = await vi.importActual<typeof import('../lib/queries')>('../lib/queries');
  return {
    ...actual,
    useAllJobs: vi.fn(),
    useJob: vi.fn(),
    useJobEvents: vi.fn(),
  };
});

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
}

function NavigationHelper() {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(-1)} data-testid="back-btn">
      Back
    </button>
  );
}

function renderJobs(initialEntries = ['/jobs']) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <Routes>
          <Route
            path="/jobs"
            element={
              <>
                <Jobs />
                <LocationDisplay />
                <NavigationHelper />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Jobs View', () => {
  const mockJobs: Job[] = [
    {
      id: 'job-2',
      project_id: 'proj-1',
      workflow: 'test',
      profile: 'dev',
      state: 'running' as const,
      context_key: 'ctx-2',
      target_id: 'target-1',
      attempts: 1,
      base_commit: 'aaa',
      created_at: '2026-01-01T12:00:00Z',
      updated_at: '2026-01-01T12:01:00Z',
      result: { text: '', commit: 'bbb', error: '' },
    },
    {
      id: 'job-1',
      project_id: 'proj-2',
      workflow: 'build',
      profile: 'prod',
      state: 'succeeded' as const,
      context_key: 'ctx-1',
      target_id: 'target-1',
      attempts: 1,
      base_commit: 'ccc',
      created_at: '2026-01-01T10:00:00Z',
      updated_at: '2026-01-01T10:05:00Z',
      result: { text: 'done', commit: 'ddd', error: '' },
    },
  ];

  const defaultProjectsData = [
    { id: 'proj-1', alias: 'Alpha Project' },
    { id: 'proj-2', alias: 'Beta Project' },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: mockJobs,
      isLoading: false,
      isFetching: false,
      isError: false,
      errors: [],
      hasData: true,
      isInitialLoading: false,
      isInitialError: false,
      hasPartialFailure: false,
      hasRefetchError: false,
      projectsQuery: { data: defaultProjectsData } as any,
      jobQueries: [],
    });
    vi.mocked(queries.useJob).mockImplementation((id) => {
      const job = mockJobs.find((j) => j.id === id) || mockJobs[0];
      return {
        data: job,
        isLoading: false,
        isError: false,
      } as any;
    });
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as any);
  });

  it('renders Jobs table with project aliases and descending order', () => {
    renderJobs();

    expect(screen.getByText('Alpha Project')).toBeInTheDocument();
    expect(screen.getByText('Beta Project')).toBeInTheDocument();

    const buttons = screen.getAllByRole('button', { name: /Open job/i });
    expect(buttons[0]).toHaveTextContent('Open job job-2');
    expect(buttons[1]).toHaveTextContent('Open job job-1');
  });

  it('falls back to project_id when alias is missing', () => {
    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: [{ ...mockJobs[0], project_id: 'unknown-proj' }],
      isLoading: false,
      isFetching: false,
      isError: false,
      errors: [],
      hasData: true,
      isInitialLoading: false,
      isInitialError: false,
      hasPartialFailure: false,
      hasRefetchError: false,
      projectsQuery: { data: [] } as any,
      jobQueries: [],
    });

    renderJobs();

    expect(screen.getByText('unknown-proj')).toBeInTheDocument();
  });

  it('filters by state client-side while preserving order', () => {
    renderJobs();

    const select = screen.getByLabelText(/State/i);
    fireEvent.change(select, { target: { value: 'succeeded' } });

    expect(screen.queryByText('Alpha Project')).not.toBeInTheDocument();
    expect(screen.getByText('Beta Project')).toBeInTheDocument();
  });

  it('renders Loading jobs... polite status when isInitialLoading is true', () => {
    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: [],
      isLoading: true,
      isFetching: true,
      isError: false,
      errors: [],
      hasData: false,
      isInitialLoading: true,
      isInitialError: false,
      hasPartialFailure: false,
      hasRefetchError: false,
      projectsQuery: { data: undefined } as any,
      jobQueries: [],
    });

    renderJobs();

    expect(screen.getByRole('status')).toHaveTextContent('Loading jobs...');
  });

  it('renders Failed to load jobs. alert when isInitialError is true', () => {
    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: [],
      isLoading: false,
      isFetching: false,
      isError: true,
      errors: [],
      hasData: false,
      isInitialLoading: false,
      isInitialError: true,
      hasPartialFailure: false,
      hasRefetchError: false,
      projectsQuery: { data: undefined } as any,
      jobQueries: [],
    });

    renderJobs();

    expect(screen.getByRole('alert')).toHaveTextContent('Failed to load jobs.');
  });

  it('renders No jobs found. when aggregate is empty with no filter', () => {
    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: [],
      isLoading: false,
      isFetching: false,
      isError: false,
      errors: [],
      hasData: true,
      isInitialLoading: false,
      isInitialError: false,
      hasPartialFailure: false,
      hasRefetchError: false,
      projectsQuery: { data: [] } as any,
      jobQueries: [],
    });

    renderJobs();

    expect(screen.getByText('No jobs found.')).toBeInTheDocument();
  });

  it('renders No jobs match this filter. when state filter has no matches', () => {
    renderJobs();

    const select = screen.getByLabelText(/State/i);
    fireEvent.change(select, { target: { value: 'failed' } });

    expect(screen.getByText('No jobs match this filter.')).toBeInTheDocument();
  });

  it('renders refetch error warning with cached rows when hasRefetchError is true', () => {
    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: mockJobs,
      isLoading: false,
      isFetching: false,
      isError: true,
      errors: [],
      hasData: true,
      isInitialLoading: false,
      isInitialError: false,
      hasPartialFailure: false,
      hasRefetchError: true,
      projectsQuery: { data: defaultProjectsData } as any,
      jobQueries: [],
    });

    renderJobs();

    expect(
      screen.getByText('Could not refresh. Showing last known data.')
    ).toBeInTheDocument();
    expect(screen.getByText('Alpha Project')).toBeInTheDocument();
  });

  it('renders partial results warning when hasPartialFailure is true', () => {
    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: mockJobs,
      isLoading: false,
      isFetching: false,
      isError: false,
      errors: [{ projectId: 'proj-2', error: new Error('fail') }],
      hasData: true,
      isInitialLoading: false,
      isInitialError: false,
      hasPartialFailure: true,
      hasRefetchError: false,
      projectsQuery: { data: defaultProjectsData } as any,
      jobQueries: [],
    });

    renderJobs();

    expect(
      screen.getByText('Could not load jobs for all projects. Showing partial results.')
    ).toBeInTheDocument();
    expect(screen.getByText('Alpha Project')).toBeInTheDocument();
  });

  it('renders No jobs found in available results. when partial failure occurs with 0 rows', () => {
    vi.mocked(queries.useAllJobs).mockReturnValue({
      jobs: [],
      isLoading: false,
      isFetching: false,
      isError: false,
      errors: [{ projectId: 'proj-2', error: new Error('fail') }],
      hasData: true,
      isInitialLoading: false,
      isInitialError: false,
      hasPartialFailure: true,
      hasRefetchError: false,
      projectsQuery: { data: defaultProjectsData } as any,
      jobQueries: [],
    });

    renderJobs();

    expect(
      screen.getByText('Could not load jobs for all projects. Showing partial results.')
    ).toBeInTheDocument();
    expect(screen.getByText('No jobs found in available results.')).toBeInTheDocument();
  });

  it('handles row cell click to set selection', () => {
    renderJobs();

    const cell = screen.getByText('Alpha Project');
    fireEvent.click(cell);

    expect(screen.getByTestId('location').textContent).toContain('selected=job-2');
  });

  it('opens inspector, updates search params, and preserves unrelated & duplicate parameters', () => {
    renderJobs(['/jobs?foo=1&foo=2']);

    const openBtn = screen.getByRole('button', { name: 'Open job job-2' });
    fireEvent.click(openBtn);

    expect(screen.getByRole('heading', { name: 'Job Details' })).toBeInTheDocument();
    expect(screen.getByTestId('location').textContent).toContain('selected=job-2');
    expect(screen.getByTestId('location').textContent).toContain('foo=1');
    expect(screen.getByTestId('location').textContent).toContain('foo=2');
  });

  it('supports keyboard accessibility for native Open job button with both Enter and Space activation while preserving native button semantics and row whitespace behavior', () => {
    renderJobs();

    const openBtn = screen.getByRole('button', { name: 'Open job job-2' }) as HTMLButtonElement;
    expect(openBtn.tagName).toBe('BUTTON');
    expect(openBtn.getAttribute('type')).toBe('button');

    // Confirm parent tr has no faux button roles or tabindices
    const tr = openBtn.closest('tr');
    expect(tr?.getAttribute('role')).toBeNull();
    expect(tr?.getAttribute('tabindex')).toBeNull();

    // Test Enter activation
    openBtn.focus();
    expect(document.activeElement).toBe(openBtn);
    fireEvent.keyDown(openBtn, { key: 'Enter', code: 'Enter' });
    expect(screen.getByTestId('location').textContent).toBe('?selected=job-2');

    // Reset URL to /jobs and test Space activation
    const closeBtn = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeBtn);
    expect(screen.getByTestId('location').textContent).toBe('');

    const openBtn1 = screen.getByRole('button', { name: 'Open job job-1' });
    openBtn1.focus();
    expect(document.activeElement).toBe(openBtn1);
    fireEvent.keyDown(openBtn1, { key: ' ', code: 'Space' });
    expect(screen.getByTestId('location').textContent).toBe('?selected=job-1');
  });

  it('directly opens inspector when loaded with ?selected=<id>', () => {
    renderJobs(['/jobs?selected=job-1']);

    expect(screen.getByRole('heading', { name: 'Job Details' })).toBeInTheDocument();
  });

  it('restores prior selection on Browser Back navigation', () => {
    renderJobs(['/jobs?selected=job-1']);

    const openBtn = screen.getByRole('button', { name: 'Open job job-2' });
    fireEvent.click(openBtn);

    expect(screen.getByTestId('location').textContent).toContain('selected=job-2');

    const backBtn = screen.getByTestId('back-btn');
    fireEvent.click(backBtn);

    expect(screen.getByTestId('location').textContent).toContain('selected=job-1');
  });

  it('closes inspector, removes selected param, and restores focus to row button', () => {
    renderJobs(['/jobs?selected=job-2']);

    const closeBtn = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeBtn);

    expect(screen.queryByRole('heading', { name: 'Job Details' })).not.toBeInTheDocument();
    expect(screen.getByTestId('location').textContent).not.toContain('selected');

    const openBtn = screen.getByRole('button', { name: 'Open job job-2' });
    expect(document.activeElement).toBe(openBtn);
  });

  it('restores focus to state filter when closed job row is no longer in table', () => {
    renderJobs(['/jobs?selected=job-2']);

    const select = screen.getByLabelText(/State/i);
    fireEvent.change(select, { target: { value: 'succeeded' } });

    const closeBtn = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeBtn);

    expect(document.activeElement).toBe(select);
  });

  it('switches selection from job A to job B, querying B and never showing stale A details', () => {
    renderJobs(['/jobs?selected=job-1']);

    expect(queries.useJob).toHaveBeenCalledWith('job-1', { enabled: true });

    const openBtn2 = screen.getByRole('button', { name: 'Open job job-2' });
    fireEvent.click(openBtn2);

    expect(queries.useJob).toHaveBeenCalledWith('job-2', { enabled: true });
    expect(screen.getByTestId('location').textContent).toContain('selected=job-2');
  });

  it('keeps inspector closed when selection parameter is missing or empty string', () => {
    const { unmount } = renderJobs(['/jobs']);
    expect(screen.queryByRole('heading', { name: 'Job Details' })).not.toBeInTheDocument();
    unmount();

    renderJobs(['/jobs?selected=']);
    expect(screen.queryByRole('heading', { name: 'Job Details' })).not.toBeInTheDocument();
  });

  it('mounts inspector and queries requested job when direct selected ID is absent from aggregate', () => {
    renderJobs(['/jobs?selected=absent-job-999']);

    expect(screen.getByRole('heading', { name: 'Job Details' })).toBeInTheDocument();
    expect(queries.useJob).toHaveBeenCalledWith('absent-job-999', { enabled: true });
  });

  it('handles encoded IDs containing slash, question mark, and ampersand', () => {
    const encodedId = encodeURIComponent('job/complex?param=1&other=2');
    renderJobs([`/jobs?selected=${encodedId}`]);

    expect(screen.getByRole('heading', { name: 'Job Details' })).toBeInTheDocument();
    expect(queries.useJob).toHaveBeenCalledWith('job/complex?param=1&other=2', { enabled: true });
  });

  it('navigates from unselected to selected, then Browser Back returns to unselected URL and closes inspector', () => {
    renderJobs(['/jobs']);

    expect(screen.queryByRole('heading', { name: 'Job Details' })).not.toBeInTheDocument();

    const openBtn = screen.getByRole('button', { name: 'Open job job-2' });
    fireEvent.click(openBtn);

    expect(screen.getByRole('heading', { name: 'Job Details' })).toBeInTheDocument();
    expect(screen.getByTestId('location').textContent).toContain('selected=job-2');

    const backBtn = screen.getByTestId('back-btn');
    fireEvent.click(backBtn);

    expect(screen.queryByRole('heading', { name: 'Job Details' })).not.toBeInTheDocument();
    expect(screen.getByTestId('location').textContent).toBe('');
  });

  it('explicit close uses replace and preserves duplicate unrelated search parameters', () => {
    renderJobs(['/jobs?foo=1&foo=2&selected=job-1']);

    const closeBtn = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeBtn);

    expect(screen.queryByRole('heading', { name: 'Job Details' })).not.toBeInTheDocument();
    const loc = screen.getByTestId('location').textContent;
    expect(loc).not.toContain('selected');
    expect(loc).toContain('foo=1');
    expect(loc).toContain('foo=2');
  });
});
