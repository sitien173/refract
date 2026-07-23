import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { EmptyState } from './EmptyState';

describe('EmptyState', () => {
  it('renders sentence-case declarative copy', () => {
    render(<EmptyState message="No projects found." />);
    expect(screen.getByText('No projects found.')).toBeTruthy();
  });
});
