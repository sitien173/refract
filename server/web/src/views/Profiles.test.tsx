import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Profiles } from './Profiles';
import * as queries from '../lib/queries';

vi.mock('../lib/queries', () => ({
  useProfiles: vi.fn(),
}));

describe('Profiles view', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders default profile and lists all available profiles including default marked with badge', () => {
    vi.mocked(queries.useProfiles).mockReturnValue({
      data: {
        default: 'standard',
        available: ['standard', 'fast', 'thorough'],
      },
      isLoading: false,
      isError: false,
    } as any);

    render(<Profiles />);

    expect(screen.getByText('Default Profile')).toBeTruthy();

    const standardMatches = screen.getAllByText('standard');
    expect(standardMatches.length).toBeGreaterThanOrEqual(2);

    expect(screen.getByText('fast')).toBeTruthy();
    expect(screen.getByText('thorough')).toBeTruthy();

    expect(screen.getAllByText('Default').length).toBeGreaterThan(0);
  });

  it('handles missing default profile', () => {
    vi.mocked(queries.useProfiles).mockReturnValue({
      data: {
        default: '',
        available: ['fast', 'thorough'],
      },
      isLoading: false,
      isError: false,
    } as any);

    render(<Profiles />);

    expect(screen.getByText('No default profile specified.')).toBeTruthy();
    expect(screen.getByText('fast')).toBeTruthy();
    expect(screen.getByText('thorough')).toBeTruthy();
  });

  it('renders initial loading state', () => {
    vi.mocked(queries.useProfiles).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as any);

    render(<Profiles />);
    expect(screen.getByRole('status')).toBeTruthy();
  });

  it('renders initial error state', () => {
    vi.mocked(queries.useProfiles).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as any);

    render(<Profiles />);
    expect(screen.getByRole('alert')).toBeTruthy();
  });

  it('renders empty state when available profiles list is empty', () => {
    vi.mocked(queries.useProfiles).mockReturnValue({
      data: {
        default: '',
        available: [],
      },
      isLoading: false,
      isError: false,
    } as any);

    render(<Profiles />);
    expect(screen.getByText('No profiles available.')).toBeTruthy();
  });
});
