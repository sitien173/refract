import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TopBar } from './TopBar';
import * as queries from '../lib/queries';

vi.mock('../lib/queries', async () => {
  const actual = await vi.importActual<typeof import('../lib/queries')>('../lib/queries');
  return {
    ...actual,
    useStatus: vi.fn(),
  };
});

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('TopBar component connection state and counts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders Connecting state before first success or error', () => {
    vi.mocked(queries.useStatus).mockReturnValue({
      data: undefined,
      isError: false,
      isLoading: true,
      dataUpdatedAt: 0,
    } as any);

    renderWithClient(<TopBar />);

    expect(screen.getByTestId('status-pill')).toHaveTextContent('Connecting');
    expect(screen.getByTestId('count-workers')).toHaveTextContent('—');
    expect(screen.getByTestId('count-active')).toHaveTextContent('—');
    expect(screen.getByTestId('count-queued')).toHaveTextContent('—');
    expect(screen.getByTestId('last-updated')).toHaveTextContent('—');
  });

  it('renders Running state and numeric counts on status success', () => {
    const timestamp = new Date('2026-07-23T12:00:00Z').getTime();
    vi.mocked(queries.useStatus).mockReturnValue({
      data: { status: 'running', workers: 4, active_jobs: 2, queued_jobs: 1 },
      isError: false,
      isLoading: false,
      dataUpdatedAt: timestamp,
    } as any);

    renderWithClient(<TopBar />);

    expect(screen.getByTestId('status-pill')).toHaveTextContent('Running');
    expect(screen.getByTestId('count-workers')).toHaveTextContent('4');
    expect(screen.getByTestId('count-active')).toHaveTextContent('2');
    expect(screen.getByTestId('count-queued')).toHaveTextContent('1');
    expect(screen.getByTestId('last-updated')).not.toHaveTextContent('—');
  });

  it('renders Degraded state when status response is not running', () => {
    vi.mocked(queries.useStatus).mockReturnValue({
      data: { status: 'stopping', workers: 1, active_jobs: 0, queued_jobs: 0 },
      isError: false,
      isLoading: false,
      dataUpdatedAt: Date.now(),
    } as any);

    renderWithClient(<TopBar />);

    expect(screen.getByTestId('status-pill')).toHaveTextContent('Degraded');
  });

  it('renders Disconnected on status query error but retains last known counts and last updated timestamp', () => {
    const initialTimestamp = 1700000000000;
    const { rerender } = renderWithClient(<TopBar />);

    // First render: success
    vi.mocked(queries.useStatus).mockReturnValue({
      data: { status: 'running', workers: 3, active_jobs: 1, queued_jobs: 0 },
      isError: false,
      isLoading: false,
      dataUpdatedAt: initialTimestamp,
    } as any);

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <TopBar />
      </QueryClientProvider>
    );

    expect(screen.getByTestId('status-pill')).toHaveTextContent('Running');
    const initialLastUpdatedText = screen.getByTestId('last-updated').textContent;
    expect(initialLastUpdatedText).not.toBe('—');

    // Second render: error during background refetch
    vi.mocked(queries.useStatus).mockReturnValue({
      data: { status: 'running', workers: 3, active_jobs: 1, queued_jobs: 0 }, // cached data
      isError: true,
      isLoading: false,
      dataUpdatedAt: initialTimestamp,
    } as any);

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <TopBar />
      </QueryClientProvider>
    );

    expect(screen.getByTestId('status-pill')).toHaveTextContent('Disconnected');
    expect(screen.getByTestId('count-workers')).toHaveTextContent('3');
    expect(screen.getByTestId('count-active')).toHaveTextContent('1');
    expect(screen.getByTestId('count-queued')).toHaveTextContent('0');
    expect(screen.getByTestId('last-updated')).toHaveTextContent(initialLastUpdatedText!);
  });

  it('recovers connection status on subsequent successful fetch', () => {
    vi.mocked(queries.useStatus).mockReturnValue({
      data: undefined,
      isError: true,
      isLoading: false,
      dataUpdatedAt: 0,
    } as any);

    const { rerender } = renderWithClient(<TopBar />);

    expect(screen.getByTestId('status-pill')).toHaveTextContent('Disconnected');

    // Later successful fetch
    vi.mocked(queries.useStatus).mockReturnValue({
      data: { status: 'running', workers: 2, active_jobs: 0, queued_jobs: 0 },
      isError: false,
      isLoading: false,
      dataUpdatedAt: Date.now(),
    } as any);

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <TopBar />
      </QueryClientProvider>
    );

    expect(screen.getByTestId('status-pill')).toHaveTextContent('Running');
    expect(screen.getByTestId('count-workers')).toHaveTextContent('2');
  });
});
