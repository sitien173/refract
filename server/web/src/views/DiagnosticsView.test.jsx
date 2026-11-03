import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { DiagnosticsView } from './DiagnosticsView.jsx'
import * as api from '../api.js'

describe('DiagnosticsView', () => {
  const mockReportsPage1 = {
    reports: [
      {
        id: 'diag-1',
        job_id: 'job-101',
        category: 'protocol',
        created_at: '2026-11-03T12:00:00Z',
        expected: 'Expected handshake packet',
        observed: 'Received invalid opcode 0xFF',
        project_id: 'proj-1',
        current_state: 'failed',
      },
    ],
    next_before: 'diag-1',
  }

  const mockReportsPage2 = {
    reports: [
      {
        id: 'diag-2',
        job_id: 'job-102',
        category: 'output',
        created_at: '2026-11-03T12:05:00Z',
        expected: 'Expected non-empty output text',
        observed: 'Empty stdout received',
        project_id: 'proj-1',
        current_state: 'failed',
      },
    ],
    next_before: null,
  }

  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(api, 'fetchProjects').mockResolvedValue([
      { id: 'proj-1', alias: 'primary-project' },
    ])
  })

  it('renders loading state when fetching diagnostics', async () => {
    vi.spyOn(api, 'fetchDiagnostics').mockImplementation(() => new Promise(() => {}))
    vi.spyOn(api, 'fetchProjects').mockImplementation(() => new Promise(() => {}))
    render(<DiagnosticsView />)
    expect(screen.getByText(/loading diagnostics/i)).toBeInTheDocument()
  })

  it('renders empty state when diagnostics are empty', async () => {
    vi.spyOn(api, 'fetchDiagnostics').mockResolvedValue({ reports: [], next_before: null })
    render(<DiagnosticsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText(/no diagnostic reports found/i)).toBeInTheDocument()
  })

  it('renders error state when fetch diagnostics fails', async () => {
    vi.spyOn(api, 'fetchDiagnostics').mockRejectedValue(new Error('Failed to query diagnostics'))
    render(<DiagnosticsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/failed to query diagnostics/i)).toBeInTheDocument()
  })

  it('renders diagnostic reports table with link to job_id', async () => {
    vi.spyOn(api, 'fetchDiagnostics').mockResolvedValue(mockReportsPage1)
    render(<DiagnosticsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getAllByText('protocol').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('proj-1')).toBeInTheDocument()

    const jobLink = screen.getByRole('link', { name: 'job-101' })
    expect(jobLink).toBeInTheDocument()
    expect(jobLink).toHaveAttribute('href', '#/jobs/job-101')
  })

  it('expands row to show expected and observed text', async () => {
    vi.spyOn(api, 'fetchDiagnostics').mockResolvedValue(mockReportsPage1)
    render(<DiagnosticsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.queryByText(/Expected handshake packet/)).not.toBeInTheDocument()

    // Click toggle button or row to expand
    const expandBtn = screen.getByRole('button', { name: /expand/i })
    expect(expandBtn).toHaveAttribute('aria-expanded', 'false')
    expect(expandBtn).toHaveAttribute('aria-controls', 'diag-detail-diag-1')

    fireEvent.click(expandBtn)

    expect(expandBtn).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Expected handshake packet/)).toBeInTheDocument()
    expect(screen.getByText(/Received invalid opcode 0xFF/)).toBeInTheDocument()
  })

  it('paginates with before cursor: requests before=<next_before> and hides control when next_before is null', async () => {
    const fetchSpy = vi.spyOn(api, 'fetchDiagnostics')
      .mockResolvedValueOnce(mockReportsPage1)
      .mockResolvedValueOnce(mockReportsPage2)

    render(<DiagnosticsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText('job-101')).toBeInTheDocument()
    expect(screen.queryByText('job-102')).not.toBeInTheDocument()

    const loadMoreBtn = screen.getByRole('button', { name: /load more/i })
    expect(loadMoreBtn).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(loadMoreBtn)
      await Promise.resolve()
    })

    expect(fetchSpy).toHaveBeenCalledWith(expect.objectContaining({ before: 'diag-1' }))
    expect(screen.getByText('job-101')).toBeInTheDocument()
    expect(screen.getByText('job-102')).toBeInTheDocument()

    // Control should now disappear because next_before is null
    expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument()
  })

  it('filters by project, category, and job id using filter controls', async () => {
    const fetchSpy = vi.spyOn(api, 'fetchDiagnostics').mockResolvedValue({ reports: [], next_before: null })
    render(<DiagnosticsView />)

    await act(async () => {
      await Promise.resolve()
    })

    // Category select filter
    const categorySelect = screen.getByLabelText(/filter by category/i)
    await act(async () => {
      fireEvent.change(categorySelect, { target: { value: 'protocol' } })
      await Promise.resolve()
    })

    expect(fetchSpy).toHaveBeenCalledWith(expect.objectContaining({ category: 'protocol' }))

    // Job ID search input filter
    const jobIdInput = screen.getByLabelText(/filter by job id/i)
    await act(async () => {
      fireEvent.change(jobIdInput, { target: { value: 'job-999' } })
      await Promise.resolve()
    })

    expect(fetchSpy).toHaveBeenCalledWith(expect.objectContaining({ job_id: 'job-999' }))
  })

  it('STRICT INVARIANT: contains no form, no non-filter input, and no mutating button', async () => {
    vi.spyOn(api, 'fetchDiagnostics').mockResolvedValue(mockReportsPage1)
    const { container } = render(<DiagnosticsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(container.querySelectorAll('form').length).toBe(0)
    container.querySelectorAll('input').forEach((input) => {
      expect(['checkbox', 'radio', 'search'].includes(input.getAttribute('type'))).toBe(true)
    })
    container.querySelectorAll('button').forEach((button) => {
      expect(button.getAttribute('type') || 'button').toBe('button')
    })
  })

  it('filter change while a load-more request is in flight discards the stale response', async () => {
    let resolveLoadMore
    const loadMorePromise = new Promise((resolve) => {
      resolveLoadMore = resolve
    })

    vi.spyOn(api, 'fetchDiagnostics')
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-old-1', category: 'protocol', job_id: 'job-old-1' }],
        next_before: 'cursor-1',
      })
      .mockImplementationOnce(() => loadMorePromise)
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-new-1', category: 'output', job_id: 'job-new-1' }],
        next_before: null,
      })

    render(<DiagnosticsView />)
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByText('job-old-1')).toBeInTheDocument()

    // Start load-more (stays pending)
    const loadMoreBtn = screen.getByRole('button', { name: /load more/i })
    await act(async () => {
      fireEvent.click(loadMoreBtn)
    })

    // Now change category filter to 'output'
    const categorySelect = screen.getByLabelText(/filter by category/i)
    await act(async () => {
      fireEvent.change(categorySelect, { target: { value: 'output' } })
      await Promise.resolve()
    })

    // Now resolve the in-flight load-more from the OLD query
    await act(async () => {
      resolveLoadMore({
        reports: [{ id: 'diag-old-stale-2', category: 'protocol', job_id: 'job-old-stale-2' }],
        next_before: 'cursor-2',
      })
      await Promise.resolve()
    })

    // The stale response from the old filter must NOT be present
    expect(screen.queryByText('job-old-stale-2')).not.toBeInTheDocument()
    // The new filter's reports must render
    expect(screen.getByText('job-new-1')).toBeInTheDocument()
    expect(screen.queryByText('job-old-1')).not.toBeInTheDocument()
  })

  it('does not leave isLoadingMore true after a filter change during a pending load-more', async () => {
    let resolveLoadMore
    const loadMorePromise = new Promise((resolve) => {
      resolveLoadMore = resolve
    })

    vi.spyOn(api, 'fetchDiagnostics')
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-1', category: 'protocol', job_id: 'job-1' }],
        next_before: 'cursor-1',
      })
      .mockImplementationOnce(() => loadMorePromise)
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-new-1', category: 'output', job_id: 'job-new-1' }],
        next_before: 'new-cursor',
      })

    render(<DiagnosticsView />)
    await act(async () => {
      await Promise.resolve()
    })

    const loadMoreBtn = screen.getByRole('button', { name: /load more/i })
    expect(loadMoreBtn).not.toBeDisabled()

    // Trigger load-more (pending)
    await act(async () => {
      fireEvent.click(loadMoreBtn)
    })
    expect(screen.getByRole('button', { name: /loading\.\.\./i })).toBeDisabled()

    // Change category filter while load-more is in flight
    const categorySelect = screen.getByLabelText(/filter by category/i)
    await act(async () => {
      fireEvent.change(categorySelect, { target: { value: 'output' } })
      await Promise.resolve()
    })

    // Resolve the old load-more response
    await act(async () => {
      resolveLoadMore({
        reports: [{ id: 'diag-old-stale', category: 'protocol', job_id: 'job-stale' }],
        next_before: 'old-cursor-2',
      })
      await Promise.resolve()
    })

    // The load more button for the new filter must not be stuck in loading/disabled state
    const newLoadMoreBtn = screen.getByRole('button', { name: /load more/i })
    expect(newLoadMoreBtn).toBeInTheDocument()
    expect(newLoadMoreBtn).not.toBeDisabled()
  })

  it('filter change does not repopulate from the previous filter data', async () => {
    let resolveNewFilter
    const newFilterPromise = new Promise((resolve) => {
      resolveNewFilter = resolve
    })

    vi.spyOn(api, 'fetchDiagnostics')
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-1', category: 'protocol', job_id: 'job-proto-1' }],
        next_before: 'cursor-1',
      })
      .mockImplementationOnce(() => newFilterPromise)

    render(<DiagnosticsView />)
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByText('job-proto-1')).toBeInTheDocument()

    // Change category filter to 'output'
    const categorySelect = screen.getByLabelText(/filter by category/i)
    await act(async () => {
      fireEvent.change(categorySelect, { target: { value: 'output' } })
    })

    // Before new filter resolves, old reports must not be repopulated
    expect(screen.queryByText('job-proto-1')).not.toBeInTheDocument()

    await act(async () => {
      resolveNewFilter({
        reports: [{ id: 'diag-2', category: 'output', job_id: 'job-out-1' }],
        next_before: null,
      })
      await Promise.resolve()
    })
    expect(screen.getByText('job-out-1')).toBeInTheDocument()
    expect(screen.queryByText('job-proto-1')).not.toBeInTheDocument()
  })

  it('a poll after paging keeps the paged cursor and produces no duplicate rows', async () => {
    vi.useFakeTimers()
    const fetchSpy = vi.spyOn(api, 'fetchDiagnostics')
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-1', category: 'protocol', job_id: 'job-1' }],
        next_before: 'cursor-page-1',
      })
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-2', category: 'protocol', job_id: 'job-2' }],
        next_before: 'cursor-page-2',
      })
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-1', category: 'protocol', job_id: 'job-1', current_state: 'succeeded' }],
        next_before: 'cursor-page-1',
      })
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-3', category: 'protocol', job_id: 'job-3' }],
        next_before: null,
      })

    render(<DiagnosticsView />)
    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText('job-1')).toBeInTheDocument()

    // Load more to establish cursor-page-2
    const loadMoreBtn = screen.getByRole('button', { name: /load more/i })
    await act(async () => {
      fireEvent.click(loadMoreBtn)
      await Promise.resolve()
    })

    expect(screen.getByText('job-2')).toBeInTheDocument()

    // Trigger next background poll (5s interval)
    await act(async () => {
      vi.advanceTimersByTime(5000)
      await Promise.resolve()
    })

    // Next poll must not duplicate rows
    expect(screen.getAllByText('job-1').length).toBe(1)
    expect(screen.getAllByText('job-2').length).toBe(1)

    // And clicking load more again must use the paged cursor ('cursor-page-2'), not 'cursor-page-1'
    const nextLoadMore = screen.getByRole('button', { name: /load more/i })
    await act(async () => {
      fireEvent.click(nextLoadMore)
      await Promise.resolve()
    })

    expect(fetchSpy).toHaveBeenCalledWith(expect.objectContaining({ before: 'cursor-page-2' }))
    vi.useRealTimers()
  })

  it('project filter passes project_id and resets the cursor', async () => {
    const fetchSpy = vi.spyOn(api, 'fetchDiagnostics')
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-1', category: 'protocol', job_id: 'job-1' }],
        next_before: 'cursor-1',
      })
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-2', category: 'protocol', job_id: 'job-2' }],
        next_before: 'cursor-2',
      })
      .mockResolvedValueOnce({
        reports: [{ id: 'diag-p2-1', category: 'protocol', job_id: 'job-p2-1' }],
        next_before: null,
      })

    render(<DiagnosticsView />)
    await act(async () => {
      await Promise.resolve()
    })

    // Load more to establish cursor-2
    const loadMoreBtn = screen.getByRole('button', { name: /load more/i })
    await act(async () => {
      fireEvent.click(loadMoreBtn)
      await Promise.resolve()
    })
    expect(screen.getByText('job-2')).toBeInTheDocument()

    // Change project filter
    const projectSelect = screen.getByLabelText(/filter by project/i)
    await act(async () => {
      fireEvent.change(projectSelect, { target: { value: 'proj-1' } })
      await Promise.resolve()
    })

    expect(fetchSpy).toHaveBeenLastCalledWith(expect.objectContaining({ project_id: 'proj-1' }))
    expect(fetchSpy).not.toHaveBeenLastCalledWith(expect.objectContaining({ before: expect.anything() }))
  })
})
