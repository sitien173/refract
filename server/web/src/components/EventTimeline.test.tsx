import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EventTimeline } from './EventTimeline';
import * as queries from '../lib/queries';

vi.mock('../lib/queries', async () => {
  const actual = await vi.importActual<typeof import('../lib/queries')>('../lib/queries');
  return {
    ...actual,
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

describe('EventTimeline', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state when events are loading with no cached data', () => {
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as any);

    render(<EventTimeline jobId="j1" />, { wrapper: createWrapper() });

    expect(screen.getByRole('status')).toHaveTextContent('Loading events...');
  });

  it('renders initial error state when events fail to load with no data', () => {
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as any);

    render(<EventTimeline jobId="j1" />, { wrapper: createWrapper() });

    expect(screen.getByRole('alert')).toHaveTextContent('Failed to load events.');
  });

  it('renders empty events message when data is an empty array', () => {
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as any);

    render(<EventTimeline jobId="j1" />, { wrapper: createWrapper() });

    expect(screen.getByText('No events recorded.')).toBeInTheDocument();
  });

  it('renders ordered semantic list with readable JSON data preserving received array order', () => {
    const mockEvents = [
      { id: 10, kind: 'job.started', created_at: '2026-01-01T10:00:00Z', data: { step: 'init' } },
      { id: 5, kind: 'job.progress', created_at: '2026-01-01T10:05:00Z', data: { percent: 50 } },
    ];
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: mockEvents,
      isLoading: false,
      isError: false,
    } as any);

    const { container } = render(<EventTimeline jobId="j1" />, { wrapper: createWrapper() });

    const ol = container.querySelector('ol');
    expect(ol).toBeInTheDocument();

    const items = screen.getAllByRole('listitem');
    expect(items.length).toBe(2);

    expect(items[0]).toHaveTextContent('job.started');
    expect(items[0].querySelector('time')).toHaveAttribute('datetime', '2026-01-01T10:00:00Z');
    expect(items[0].querySelector('pre')?.textContent).toBe(JSON.stringify({ step: 'init' }, null, 2));

    expect(items[1]).toHaveTextContent('job.progress');
    expect(items[1].querySelector('time')).toHaveAttribute('datetime', '2026-01-01T10:05:00Z');
    expect(items[1].querySelector('pre')?.textContent).toBe(JSON.stringify({ percent: 50 }, null, 2));
  });

  it('renders cached-refetch warning when refetch fails but cached data exists', () => {
    const mockEvents = [{ id: 1, kind: 'job.started', created_at: '2026-01-01T10:00:00Z', data: {} }];
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: mockEvents,
      isLoading: false,
      isError: true,
    } as any);

    render(<EventTimeline jobId="j1" />, { wrapper: createWrapper() });

    expect(screen.getByText('Could not refresh. Showing last known data.')).toBeInTheDocument();
    expect(screen.getByText('job.started')).toBeInTheDocument();
  });

  it('renders cached-refetch warning and empty message when refetch fails with cached empty array', () => {
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: [],
      isLoading: false,
      isError: true,
    } as any);

    render(<EventTimeline jobId="j1" />, { wrapper: createWrapper() });

    expect(screen.getByText('Could not refresh. Showing last known data.')).toBeInTheDocument();
    expect(screen.getByText('No events recorded.')).toBeInTheDocument();
  });

  it('handles full-history replacement from [event 1] to [event 1, event 2] with exactly two rendered events and no duplicates', () => {
    const initialEvents = [
      { id: 1, kind: 'event 1', created_at: '2026-01-01T10:00:00Z', data: { step: 1 } },
    ];
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: initialEvents,
      isLoading: false,
      isError: false,
    } as any);

    const { rerender } = render(<EventTimeline jobId="j1" />, { wrapper: createWrapper() });

    let items = screen.getAllByRole('listitem');
    expect(items.length).toBe(1);
    expect(items[0]).toHaveTextContent('event 1');

    const updatedEvents = [
      { id: 1, kind: 'event 1', created_at: '2026-01-01T10:00:00Z', data: { step: 1 } },
      { id: 2, kind: 'event 2', created_at: '2026-01-01T10:01:00Z', data: { step: 2 } },
    ];
    vi.mocked(queries.useJobEvents).mockReturnValue({
      data: updatedEvents,
      isLoading: false,
      isError: false,
    } as any);

    rerender(<EventTimeline jobId="j1" />);

    items = screen.getAllByRole('listitem');
    expect(items.length).toBe(2);
    expect(items[0]).toHaveTextContent('event 1');
    expect(items[1]).toHaveTextContent('event 2');
    expect(screen.getAllByText('event 1').length).toBe(1);
  });
});
