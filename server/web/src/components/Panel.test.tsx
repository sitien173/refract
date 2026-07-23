import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { Panel } from './Panel';

describe('Panel', () => {
  it('renders Title Case heading and children', () => {
    render(
      <Panel title="System Status">
        <div>Child content</div>
      </Panel>
    );
    expect(screen.getByRole('heading', { level: 2, name: 'System Status' })).toBeTruthy();
    expect(screen.getByText('Child content')).toBeTruthy();
  });

  it('supports custom heading level and supporting text', () => {
    render(
      <Panel title="Recent Activity" headingLevel="h3" supportingText="Last 5 jobs">
        <div>Details</div>
      </Panel>
    );
    expect(screen.getByRole('heading', { level: 3, name: 'Recent Activity' })).toBeTruthy();
    expect(screen.getByText('Last 5 jobs')).toBeTruthy();
  });
});
