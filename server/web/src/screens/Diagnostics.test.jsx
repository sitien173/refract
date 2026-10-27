import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import Diagnostics from './Diagnostics'

vi.mock('../api', () => ({
  getDiagnostics: vi.fn(),
}))

const mockReportsPage1 = [
  {
    id: '102',
    job_id: 'job-alpha',
    category: 'protocol',
    created_at: '2026-10-27 12:00:00',
    expected: 'Status code 200 with JSON payload',
    observed: 'Status code 502 Bad Gateway',
    project_id: 'proj-1',
    current_state: 'succeeded',
  },
  {
    id: '101',
    job_id: 'job-beta',
    category: 'output',
    created_at: '2026-10-27 11:30:00',
    expected: 'Output matching schema',
    observed: 'Output was empty string',
    project_id: 'proj-1',
    current_state: 'failed',
  },
]

const mockReportsPage2 = [
  {
    id: '99',
    job_id: 'job-gamma',
    category: 'protocol',
    created_at: '2026-10-27 11:00:00',
    expected: 'Heartbeat within 3600s',
    observed: 'Connection terminated unexpectedly',
    project_id: 'proj-2',
    current_state: 'interrupted',
  },
]

describe('Diagnostics screen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.pushState({}, '', '/dashboard/diagnostics')
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders page header, filters, and reports table with explicit current execution state', async () => {
    vi.mocked(api.getDiagnostics).mockResolvedValue({
      reports: mockReportsPage1,
      next_before: '101',
    })

    render(<Diagnostics />)

    expect(screen.getByRole('heading', { name: /^Diagnostics$/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/filter by project/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/filter by job/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/filter by category/i)).toBeInTheDocument()

    // Await reports to render
    expect(await screen.findByText('102')).toBeInTheDocument()
    expect(screen.getByText('101')).toBeInTheDocument()
    expect(screen.getAllByText('protocol').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('output').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Status code 200 with JSON payload')).toBeInTheDocument()
    expect(screen.getByText('Status code 502 Bad Gateway')).toBeInTheDocument()
    expect(screen.getByText('Output matching schema')).toBeInTheDocument()
    expect(screen.getByText('Output was empty string')).toBeInTheDocument()

    // Explicitly labeled current execution state
    expect(screen.getByText(/Current: succeeded|Current execution state/i)).toBeInTheDocument()
    expect(screen.getByText(/Current: failed|Current execution state/i)).toBeInTheDocument()

    // Job links navigate to job
    const jobLink = screen.getByRole('link', { name: 'job-alpha' })
    expect(jobLink).toHaveAttribute('href', '/dashboard/projects/proj-1/jobs/job-alpha')
  })

  it('renders untrusted summary text as plain text, never executing or injecting HTML elements', async () => {
    const dangerousReport = {
      id: '200',
      job_id: 'job-xss',
      category: 'protocol',
      created_at: '2026-10-27 12:00:00',
      expected: '<div id="malicious-expected">expected <b>bold</b> text</div>',
      observed: '<img src="invalid" id="malicious-img" onerror="alert(1)" />',
      project_id: 'proj-1',
      current_state: 'failed',
    }

    vi.mocked(api.getDiagnostics).mockResolvedValue({
      reports: [dangerousReport],
      next_before: null,
    })

    const { container } = render(<Diagnostics />)

    expect(await screen.findByText('200')).toBeInTheDocument()

    // Verify raw HTML strings are rendered as text content
    expect(screen.getByText(/<div id="malicious-expected">/)).toBeInTheDocument()
    expect(screen.getByText(/<img src="invalid"/)).toBeInTheDocument()

    // Verify elements are NOT present in the DOM
    expect(container.querySelector('#malicious-expected')).toBeNull()
    expect(container.querySelector('#malicious-img')).toBeNull()
  })

  it('navigates bounded next-page pagination and resets when filter changes', async () => {
    vi.mocked(api.getDiagnostics)
      .mockResolvedValueOnce({
        reports: mockReportsPage1,
        next_before: '101',
      })
      .mockResolvedValueOnce({
        reports: mockReportsPage2,
        next_before: null,
      })
      .mockResolvedValueOnce({
        reports: [mockReportsPage1[0]],
        next_before: null,
      })

    render(<Diagnostics />)

    expect(await screen.findByText('102')).toBeInTheDocument()
    const nextBtn = screen.getByRole('button', { name: /next page/i })
    const prevBtn = screen.getByRole('button', { name: /previous page/i })

    expect(prevBtn).toBeDisabled()
    expect(nextBtn).toBeEnabled()

    // Click next page
    fireEvent.click(nextBtn)

    await waitFor(() => {
      expect(api.getDiagnostics).toHaveBeenCalledWith(
        expect.objectContaining({ before: '101' }),
        expect.anything()
      )
    })

    expect(await screen.findByText('99')).toBeInTheDocument()
    expect(prevBtn).toBeEnabled()
    expect(nextBtn).toBeDisabled()

    // Changing filter resets pagination and fetches page 1
    const categorySelect = screen.getByLabelText(/filter by category/i)
    fireEvent.change(categorySelect, { target: { value: 'protocol' } })

    await waitFor(() => {
      expect(api.getDiagnostics).toHaveBeenCalledWith(
        expect.objectContaining({ category: 'protocol', before: undefined }),
        expect.anything()
      )
    })
    expect(prevBtn).toBeDisabled()
  })

  it('ignores stale responses when filter changes rapidly', async () => {
    let resolveFirst
    const firstPromise = new Promise((resolve) => {
      resolveFirst = resolve
    })

    vi.mocked(api.getDiagnostics)
      .mockImplementationOnce(() => firstPromise)
      .mockResolvedValueOnce({
        reports: [mockReportsPage1[1]], // job-beta
        next_before: null,
      })

    render(<Diagnostics />)

    const jobInput = screen.getByLabelText(/filter by job/i)
    fireEvent.change(jobInput, { target: { value: 'job-beta' } })

    // Second request finishes first
    expect(await screen.findByText('job-beta')).toBeInTheDocument()

    // Now resolve first request with older data
    resolveFirst({
      reports: [mockReportsPage1[0]], // job-alpha
      next_before: null,
    })

    // Wait a tick and verify stale job-alpha is NOT displayed
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByText('job-alpha')).not.toBeInTheDocument()
    expect(screen.getByText('job-beta')).toBeInTheDocument()
  })

  it('renders loading, empty, and daemon error states', async () => {
    vi.mocked(api.getDiagnostics).mockResolvedValueOnce({
      reports: [],
      next_before: null,
    })

    const { rerender } = render(<Diagnostics />)

    expect(await screen.findByText(/No diagnostic reports found/i)).toBeInTheDocument()

    // Initial error state when no reports loaded
    vi.mocked(api.getDiagnostics).mockRejectedValueOnce(new Error('Connection to daemon refused'))
    const refreshBtn = screen.getByRole('button', { name: /refresh/i })
    fireEvent.click(refreshBtn)

    expect(await screen.findByText(/Connection to daemon refused/i)).toBeInTheDocument()

    // Successful reload followed by background refresh failure keeps previous data and displays warning
    vi.mocked(api.getDiagnostics)
      .mockResolvedValueOnce({ reports: mockReportsPage1, next_before: null })
      .mockRejectedValueOnce(new Error('Background network drop'))

    fireEvent.click(refreshBtn)
    expect(await screen.findByText('102')).toBeInTheDocument()

    fireEvent.click(refreshBtn)
    expect(await screen.findByText(/Showing previously loaded diagnostics/i)).toBeInTheDocument()
    expect(screen.getByText('102')).toBeInTheDocument()
  })

  it('supports keyboard activation on clear filters with Enter and Space', async () => {
    vi.mocked(api.getDiagnostics).mockResolvedValue({
      reports: mockReportsPage1,
      next_before: null,
    })

    render(<Diagnostics />)

    const projectInput = screen.getByLabelText(/filter by project/i)
    fireEvent.change(projectInput, { target: { value: 'proj-1' } })

    expect(await screen.findByRole('button', { name: /clear filters/i })).toBeInTheDocument()
    const clearBtn = screen.getByRole('button', { name: /clear filters/i })

    // Activate clear button with keyboard Enter key only, without firing click
    fireEvent.keyDown(clearBtn, { key: 'Enter', code: 'Enter' })
    expect(projectInput).toHaveValue('')

    // Set filter again and activate with Space key only
    fireEvent.change(projectInput, { target: { value: 'proj-2' } })
    expect(projectInput).toHaveValue('proj-2')
    const clearBtnAgain = screen.getByRole('button', { name: /clear filters/i })
    fireEvent.keyDown(clearBtnAgain, { key: ' ', code: 'Space' })
    expect(projectInput).toHaveValue('')
  })

  it('clears old reports when query changes and does not attribute old reports or show warning on new query failure', async () => {
    let rejectQueryB
    const queryBPromise = new Promise((resolve, reject) => {
      rejectQueryB = reject
    })

    vi.mocked(api.getDiagnostics)
      .mockResolvedValueOnce({
        reports: mockReportsPage1,
        next_before: null,
      })
      .mockImplementationOnce(() => queryBPromise)

    render(<Diagnostics />)

    // Wait for initial query results
    expect(await screen.findByText('102')).toBeInTheDocument()

    // Change filter to proj-2
    const projectInput = screen.getByLabelText(/filter by project/i)
    fireEvent.change(projectInput, { target: { value: 'proj-2' } })

    // Old reports must immediately NOT be in the document
    expect(screen.queryByText('102')).toBeNull()

    // Query B fails
    rejectQueryB(new Error('Network error on proj-2'))

    // Error alert must be shown, NOT warning alert, and old reports must remain absent
    expect(await screen.findByText(/Network error on proj-2/i)).toBeInTheDocument()
    expect(screen.queryByText(/Showing previously loaded diagnostics/i)).toBeNull()
    expect(screen.queryByText('102')).toBeNull()
  })

  it('synchronizes filters and fetches reports on popstate navigation events', async () => {
    vi.mocked(api.getDiagnostics).mockResolvedValue({
      reports: mockReportsPage2,
      next_before: null,
    })

    render(<Diagnostics />)

    // Simulate browser history navigation
    window.history.pushState({}, '', '/dashboard/diagnostics?job_id=job-gamma&category=protocol')
    fireEvent(window, new PopStateEvent('popstate'))

    await waitFor(() => {
      expect(api.getDiagnostics).toHaveBeenCalledWith(
        expect.objectContaining({ jobId: 'job-gamma', category: 'protocol' }),
        expect.anything()
      )
    })

    expect(await screen.findByText('99')).toBeInTheDocument()
    expect(screen.getByLabelText(/filter by job/i)).toHaveValue('job-gamma')
  })

  it('shows loading indicator while request is in-flight', async () => {
    let resolveQuery
    const queryPromise = new Promise((resolve) => {
      resolveQuery = resolve
    })

    vi.mocked(api.getDiagnostics).mockImplementationOnce(() => queryPromise)

    render(<Diagnostics />)

    const refreshBtn = screen.getByRole('button', { name: /refresh/i })
    expect(refreshBtn).toHaveTextContent('Loading…')
    expect(refreshBtn).toBeDisabled()

    resolveQuery({ reports: mockReportsPage1, next_before: null })
    expect(await screen.findByText('102')).toBeInTheDocument()
    expect(refreshBtn).toHaveTextContent('Refresh')
    expect(refreshBtn).toBeEnabled()
  })
})
