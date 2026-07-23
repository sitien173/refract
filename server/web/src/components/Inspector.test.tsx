import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Inspector } from './Inspector';
import * as queries from '../lib/queries';

vi.mock('../lib/queries', async () => {
  const actual = await vi.importActual<typeof import('../lib/queries')>('../lib/queries');
  return {
    ...actual,
    useJob: vi.fn(),
    useJobEvents: vi.fn(),
  };
});

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('Inspector', () => {
  const defaultJob = {
    id: 'job-123',
    project_id: 'proj-1',
    workflow: 'build-deploy',
    profile: 'production',
    state: 'succeeded' as const,
    attempts: 2,
    base_commit: 'abc1234',
    result_commit: 'def5678',
    created_at: '2026-01-01T10:00:00Z',
    updated_at: '2026-01-01T10:05:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as any);
  });

  it('renders Title Case Job Details heading, accessible close button, and aria-labelledby attribute', () => {
    vi.mocked(queries.useJob).mockReturnValue({
      data: defaultJob,
      isLoading: false,
      isError: false,
    } as any);

    const onClose = vi.fn();
    const { container } = render(<Inspector jobId="job-123" onClose={onClose} />, {
      wrapper: createWrapper(),
    });

    const aside = container.querySelector('aside');
    expect(aside).toBeInTheDocument();
    expect(aside).toHaveAttribute('aria-labelledby', 'inspector-heading');

    const heading = screen.getByRole('heading', { level: 2, name: 'Job Details' });
    expect(heading).toBeInTheDocument();
    expect(heading.id).toBe('inspector-heading');

    const closeBtn = screen.getByRole('button', { name: /close/i });
    expect(closeBtn).toBeInTheDocument();

    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders loading state when job detail is loading with no cached data while timeline remains mounted', () => {
    vi.mocked(queries.useJob).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as any);
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: [{ id: 1, kind: 'job.created', created_at: '2026-01-01T10:00:00Z', data: {} }],
      isLoading: false,
      isError: false,
    } as any);

    render(<Inspector jobId="job-123" onClose={vi.fn()} />, { wrapper: createWrapper() });

    expect(screen.getByRole('status')).toHaveTextContent('Loading job details...');
    expect(screen.getByText('Event Timeline')).toBeInTheDocument();
    expect(screen.getByText('job.created')).toBeInTheDocument();
  });

  it('renders initial error state when job detail fails with no data while timeline remains mounted', () => {
    vi.mocked(queries.useJob).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as any);
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as any);

    render(<Inspector jobId="job-123" onClose={vi.fn()} />, { wrapper: createWrapper() });

    expect(screen.getByRole('alert')).toHaveTextContent('Failed to load job details.');
    expect(screen.getByText('Event Timeline')).toBeInTheDocument();
  });

  it('renders cached-refetch warning when detail refetch fails with cached data', () => {
    vi.mocked(queries.useJob).mockReturnValue({
      data: defaultJob,
      isLoading: false,
      isError: true,
    } as any);

    render(<Inspector jobId="job-123" onClose={vi.fn()} />, { wrapper: createWrapper() });

    expect(screen.getByText('Could not refresh. Showing last known data.')).toBeInTheDocument();
    expect(screen.getByText('job-123')).toBeInTheDocument();
  });

  it('renders all detail fields, status badge, timestamps, commit values and commit relationship', () => {
    vi.mocked(queries.useJob).mockReturnValue({
      data: defaultJob,
      isLoading: false,
      isError: false,
    } as any);

    render(<Inspector jobId="job-123" onClose={vi.fn()} />, { wrapper: createWrapper() });

    expect(screen.getByText('job-123')).toBeInTheDocument();
    expect(screen.getByText('build-deploy')).toBeInTheDocument();
    expect(screen.getByText('production')).toBeInTheDocument();
    expect(screen.getByText('proj-1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('abc1234')).toBeInTheDocument();
    expect(screen.getByText('def5678')).toBeInTheDocument();
    expect(screen.getByText(/Base to Result: abc1234 → def5678/)).toBeInTheDocument();
  });

  it('renders Not available fallback for empty base_commit and result_commit', () => {
    const jobNoCommits = {
      ...defaultJob,
      base_commit: null as any,
      result_commit: '',
    };
    vi.mocked(queries.useJob).mockReturnValue({
      data: jobNoCommits,
      isLoading: false,
      isError: false,
    } as any);

    render(<Inspector jobId="job-123" onClose={vi.fn()} />, { wrapper: createWrapper() });

    const notAvailables = screen.getAllByText('Not available');
    expect(notAvailables.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/Base to Result: Not available → Not available/)).toBeInTheDocument();
  });
});
