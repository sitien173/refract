import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Projects } from './Projects';
import * as queries from '../lib/queries';

vi.mock('../lib/queries', () => ({
  useProjects: vi.fn(),
}));

describe('Projects view', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders projects table with live hook data', () => {
    vi.mocked(queries.useProjects).mockReturnValue({
      data: [
        {
          id: 'p1',
          alias: 'main-service',
          root: '/home/ngosi/main-service',
          head_commit: '1234567890abcdef',
          clean: true,
          created_at: '2026-07-23T10:00:00Z',
        },
        {
          id: 'p2',
          alias: 'worker-agent',
          root: '/home/ngosi/worker-agent',
          head_commit: 'fedcba0987654321',
          clean: false,
          created_at: '2026-07-23T11:00:00Z',
        },
      ],
      isLoading: false,
      isError: false,
    } as any);

    const { container } = render(<Projects />);

    expect(screen.getByText('main-service')).toBeTruthy();
    expect(screen.getByText('worker-agent')).toBeTruthy();
    expect(screen.getByText('/home/ngosi/main-service')).toBeTruthy();

    const commitCode = screen.getByTitle('1234567890abcdef');
    expect(commitCode).toBeTruthy();
    expect(commitCode.textContent).toBe('1234567');

    expect(screen.getByText('Clean')).toBeTruthy();
    expect(screen.getByText('Dirty')).toBeTruthy();

    const timeElements = container.querySelectorAll('time');
    expect(timeElements.length).toBe(2);
    expect(timeElements[0].getAttribute('datetime')).toBe('2026-07-23T10:00:00Z');
  });

  it('renders initial loading state', () => {
    vi.mocked(queries.useProjects).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as any);

    render(<Projects />);
    expect(screen.getByRole('status')).toBeTruthy();
  });

  it('renders initial error state', () => {
    vi.mocked(queries.useProjects).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as any);

    render(<Projects />);
    expect(screen.getByRole('alert')).toBeTruthy();
  });

  it('renders empty state when projects array is empty', () => {
    vi.mocked(queries.useProjects).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as any);

    render(<Projects />);
    expect(screen.getByText('No projects found.')).toBeTruthy();
  });

  it('shows refetch warning banner when in error with cached data', () => {
    vi.mocked(queries.useProjects).mockReturnValue({
      data: [
        {
          id: 'p1',
          alias: 'main-service',
          root: '/app',
          head_commit: '1234567',
          clean: true,
          created_at: '2026-07-23T10:00:00Z',
        },
      ],
      isLoading: false,
      isError: true,
    } as any);

    render(<Projects />);
    expect(screen.getByText('Could not refresh. Showing last known data.')).toBeTruthy();
    expect(screen.getByText('main-service')).toBeTruthy();
  });
});
