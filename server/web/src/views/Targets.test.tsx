import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Targets } from './Targets';
import * as queries from '../lib/queries';

vi.mock('../lib/queries', () => ({
  useTargets: vi.fn(),
}));

describe('Targets view', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders targets table with live hook data and derives circuit states', () => {
    const futureDate = new Date(Date.now() + 60000).toISOString();
    vi.mocked(queries.useTargets).mockReturnValue({
      data: [
        {
          id: 'target-1',
          model: 'gpt-4o',
          capabilities: ['code_execution', 'web_search'],
          max_concurrency: 4,
          active: 2,
          healthy: true,
          circuit_open_until: '',
        },
        {
          id: 'target-2',
          model: 'claude-3-5-sonnet',
          capabilities: ['reasoning'],
          max_concurrency: 2,
          active: 1,
          healthy: false,
          circuit_open_until: futureDate,
        },
      ],
      isLoading: false,
      isError: false,
    } as any);

    render(<Targets />);

    expect(screen.getByText('target-1')).toBeTruthy();
    expect(screen.getByText('gpt-4o')).toBeTruthy();
    expect(screen.getByText('code_execution, web_search')).toBeTruthy();
    expect(screen.getByText('2 / 4')).toBeTruthy();
    expect(screen.getByText('Healthy')).toBeTruthy();
    expect(screen.getByText('Closed')).toBeTruthy();

    expect(screen.getByText('target-2')).toBeTruthy();
    expect(screen.getByText('claude-3-5-sonnet')).toBeTruthy();
    expect(screen.getByText('1 / 2')).toBeTruthy();
    expect(screen.getByText('Degraded')).toBeTruthy();
    expect(screen.getByText('Circuit Open')).toBeTruthy();
  });

  it('renders simultaneous Degraded health and Circuit Open badges for unhealthy target', () => {
    const futureDate = new Date(Date.now() + 60000).toISOString();
    vi.mocked(queries.useTargets).mockReturnValue({
      data: [
        {
          id: 't-degraded-open',
          model: 'local-llm',
          capabilities: [],
          max_concurrency: 1,
          active: 0,
          healthy: false,
          circuit_open_until: futureDate,
        },
      ],
      isLoading: false,
      isError: false,
    } as any);

    render(<Targets />);

    expect(screen.getByText('Degraded')).toBeTruthy();
    expect(screen.getByText('Circuit Open')).toBeTruthy();
  });

  it('renders initial loading state', () => {
    vi.mocked(queries.useTargets).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as any);

    render(<Targets />);
    expect(screen.getByRole('status')).toBeTruthy();
  });

  it('renders initial error state', () => {
    vi.mocked(queries.useTargets).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as any);

    render(<Targets />);
    expect(screen.getByRole('alert')).toBeTruthy();
  });

  it('renders empty state when targets array is empty', () => {
    vi.mocked(queries.useTargets).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as any);

    render(<Targets />);
    expect(screen.getByText('No targets found.')).toBeTruthy();
  });
});
