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
    context_key: 'ctx-1',
    target_id: 'target-1',
    attempts: 2,
    base_commit: 'abc1234',
    result: { text: 'success', commit: 'def5678', error: '' },
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
      base_commit: '',
      result: { text: '', commit: '', error: '' },
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

  it('enforces Phase 4 CSS styling contract tokens, motion overrides, responsive stacking, dark parity, and positioning rules', async () => {
    const fs = await import('fs');
    const path = await import('path');
    const cssPath = path.resolve(__dirname, '../styles/app.module.css');
    const cssContent = fs.readFileSync(cssPath, 'utf8');

    // Surface, border, radius, elevation, padding, motion and easing tokens
    expect(cssContent).toContain('background-color: var(--color-surface);');
    expect(cssContent).toContain('var(--color-border-subdued)');
    expect(cssContent).toContain('border-radius: var(--radius-xs);');
    expect(cssContent).toContain('box-shadow: var(--elev-depth4);');
    expect(cssContent).toContain('padding: var(--space-lg);');
    expect(cssContent).toContain('var(--motion-normal)');
    expect(cssContent).toContain('var(--ease-standard)');

    // Mount-time slide-in animation keyframe and property
    expect(cssContent).toContain('animation: inspectorSlideIn var(--motion-normal) var(--ease-standard);');
    expect(cssContent).toContain('@keyframes inspectorSlideIn');

    // Reduced motion override (disables both transition and animation)
    expect(cssContent).toContain('@media (prefers-reduced-motion: reduce)');
    expect(cssContent).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{\s*\.inspector\s*\{[^}]*transition:\s*none;[^}]*animation:\s*none;/);

    // Desktop list min-width: 0
    expect(cssContent).toContain('.jobsMainArea {');
    expect(cssContent).toContain('min-width: 0;');

    // 768px breakpoint stacking with full width and max-width: 100%
    expect(cssContent).toContain('@media (max-width: 768px)');
    expect(cssContent).toMatch(/\.inspector\s*\{[^}]*width:\s*100%;[^}]*max-width:\s*100%;/);

    // No fixed or absolute positioning for inspector
    const inspectorRuleBlock = cssContent.match(/\.inspector\s*\{([^}]+)\}/);
    expect(inspectorRuleBlock).not.toBeNull();
    if (inspectorRuleBlock) {
      expect(inspectorRuleBlock[1]).not.toContain('position: fixed');
      expect(inspectorRuleBlock[1]).not.toContain('position: absolute');
    }

    // No raw palette values in Phase 4 inspector styles (dark parity via variables)
    const inspectorSectionIndex = cssContent.indexOf('/* Phase 4 Jobs & Inspector Layout */');
    expect(inspectorSectionIndex).toBeGreaterThan(-1);
    const phase4Css = cssContent.slice(inspectorSectionIndex);
    expect(phase4Css).not.toMatch(/#[0-9a-fA-F]{3,8}/);
    expect(phase4Css).not.toMatch(/\brgb\(/i);
    expect(phase4Css).not.toMatch(/\bhsl\(/i);
  });
});
