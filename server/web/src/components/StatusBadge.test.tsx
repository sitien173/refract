import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { StatusBadge, BadgeState } from './StatusBadge';

describe('StatusBadge', () => {
  const allStates: BadgeState[] = [
    'queued',
    'running',
    'succeeded',
    'failed',
    'cancelled',
    'interrupted',
    'healthy',
    'degraded',
    'clean',
    'dirty',
    'circuit-open',
    'circuit-closed',
    'circuit-unknown',
  ];

  allStates.forEach((state) => {
    it(`renders label and aria-hidden icon for state: ${state}`, () => {
      const { container } = render(<StatusBadge state={state} />);
      const badge = container.querySelector('[data-testid^="status-badge"]');
      expect(badge).toBeTruthy();

      const icon = container.querySelector('[aria-hidden="true"]');
      expect(icon).toBeTruthy();

      expect(badge?.textContent).toBeTruthy();
    });
  });

  it('renders correct text label for circuit-open and circuit-closed', () => {
    render(
      <>
        <StatusBadge state="circuit-open" />
        <StatusBadge state="circuit-closed" />
        <StatusBadge state="circuit-unknown" />
      </>
    );

    expect(screen.getByText('Circuit Open')).toBeTruthy();
    expect(screen.getByText('Closed')).toBeTruthy();
    expect(screen.getByText('Circuit State Unknown')).toBeTruthy();
  });

  it('renders correct text label for degraded health', () => {
    render(<StatusBadge state="degraded" />);
    expect(screen.getByText('Degraded')).toBeTruthy();
  });
});
