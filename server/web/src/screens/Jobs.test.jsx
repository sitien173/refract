import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import JobDetail from './JobDetail'
import Jobs from './Jobs'

vi.mock('../api', () => ({
  getProjects: vi.fn(),
  getProjectJobs: vi.fn(),
  getJob: vi.fn(),
}))

describe('Jobs screen and JobDetail screen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.getProjects).mockResolvedValue([
      { id: 'proj-1', alias: 'Primary Workspace', root: '/work/proj1' },
      { id: 'proj-2', alias: 'Secondary Workspace', root: '/work/proj2' },
    ])
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders scoped project jobs table with configuration revision and states', async () => {
    vi.mocked(api.getProjectJobs).mockResolvedValue([
      {
        id: 'job-101',
        workflow: 'implement',
        profile: 'balanced',
        state: 'running',
        target_id: 'worker-primary',
        config_revision: 'abc123def456789012345678',
        created_at: '2026-09-04 14:00:00',
      },
      {
        id: 'job-102',
        workflow: 'review',
        profile: 'balanced',
        state: 'succeeded',
        target_id: 'worker-review',
        config_revision: '',
        created_at: '2026-09-04 14:05:00',
      },
    ])

    render(<Jobs projectId="proj-1" />)

    expect(await screen.findByText('job-101')).toBeInTheDocument()
    expect(screen.getByText('job-102')).toBeInTheDocument()
    expect(screen.getByText('running')).toBeInTheDocument()
    expect(screen.getByText('succeeded')).toBeInTheDocument()

    // Config revision is optional and hidden by default
    expect(screen.queryByText('abc123def456')).not.toBeInTheDocument()

    // Toggle Config revision through Columns control
    fireEvent.click(screen.getByRole('button', { name: /Columns/i }))
    const configCheckbox = screen.getByRole('checkbox', { name: /Config revision/i })
    expect(configCheckbox).not.toBeChecked()
    fireEvent.click(configCheckbox)

    expect(screen.getByText('abc123def456')).toBeInTheDocument()
    expect(screen.getByText('Unavailable')).toBeInTheDocument()

    // Test sorting by Job ID descending
    const idSortBtn = screen.getByRole('button', { name: /Sort by Job ID/i })
    fireEvent.click(idSortBtn) // asc
    fireEvent.click(idSortBtn) // desc
    const rows = screen.getAllByRole('row').slice(1)
    expect(rows[0]).toHaveTextContent('job-102')
    expect(rows[1]).toHaveTextContent('job-101')
  })

  it('stops polling after an empty project result', async () => {
    vi.mocked(api.getProjectJobs).mockResolvedValue([])

    render(<Jobs projectId="proj-1" />)
    await waitFor(() => expect(api.getProjectJobs).toHaveBeenCalledTimes(1))

    vi.useFakeTimers()
    await vi.advanceTimersByTimeAsync(10000)
    expect(api.getProjectJobs).toHaveBeenCalledTimes(1)
  })

  it('stops polling when all jobs are in terminal states', async () => {
    vi.mocked(api.getProjectJobs).mockResolvedValue([
      {
        id: 'job-terminal-1',
        workflow: 'consult',
        profile: 'balanced',
        state: 'succeeded',
        target_id: 'worker-1',
        config_revision: 'rev1',
        created_at: '2026-09-04 14:00:00',
      },
    ])

    render(<Jobs projectId="proj-1" />)
    expect(await screen.findByText('job-terminal-1')).toBeInTheDocument()

    vi.useFakeTimers()
    const initialCalls = api.getProjectJobs.mock.calls.length

    // Advance 10 seconds - should not poll because job is terminal
    await vi.advanceTimersByTimeAsync(10000)
    expect(api.getProjectJobs).toHaveBeenCalledTimes(initialCalls)
  })

  it('cleans up polling timer and stops requests after unmount', async () => {
    vi.mocked(api.getProjectJobs).mockResolvedValue([
      {
        id: 'job-running-1',
        workflow: 'implement',
        profile: 'balanced',
        state: 'running',
        target_id: 'worker-1',
        config_revision: 'rev1',
        created_at: '2026-09-04 14:00:00',
      },
    ])

    const { unmount } = render(<Jobs projectId="proj-1" />)
    expect(await screen.findByText('job-running-1')).toBeInTheDocument()

    vi.useFakeTimers()
    const initialCalls = api.getProjectJobs.mock.calls.length

    unmount()

    await vi.advanceTimersByTimeAsync(30000)
    expect(api.getProjectJobs).toHaveBeenCalledTimes(initialCalls)
  })

  it('JobDetail renders allowlisted execution plan fields and unavailable fallbacks without leaking secrets', async () => {
    vi.mocked(api.getJob).mockResolvedValue({
      id: 'job-detail-1',
      project_id: 'proj-1',
      workflow: 'consult',
      profile: 'balanced',
      state: 'succeeded',
      target_id: 'primary-worker',
      config_revision: 'sha256-snapshot-revision-001',
      attempts: 1,
      created_at: '2026-09-04 14:00:00',
      updated_at: '2026-09-04 14:01:00',
      execution_plan: {
        profile: 'balanced',
        workflow: 'consult',
        selection: {
          targets: ['primary-worker', 'secondary-worker'],
          max_attempts: 2,
          timeout_s: 90,
        },
        targets: [
          {
            id: 'primary-worker',
            backend: 'pi',
            model: 'deepseek-v4',
            isolated: true,
            read_only: false,
            max_concurrency: 4,
          },
        ],
        // Secret fields that backend should redact or frontend must never display
        secret_instruction: 'unauthorized leakage',
        system_prompt: 'secret prompt text',
        args: ['--sensitive-flag'],
      },
      result: {
        error: '',
        output: 'Job completed successfully with detailed response.',
      },
    })

    const { container } = render(<JobDetail jobId="job-detail-1" />)

    expect(await screen.findByText('Job job-detail-1')).toBeInTheDocument()
    expect(screen.getByText('sha256-snapshot-revision-001')).toBeInTheDocument()
    expect(screen.getByText('primary-worker, secondary-worker')).toBeInTheDocument()
    expect(screen.getByText('deepseek-v4')).toBeInTheDocument()
    expect(screen.getByText('Job completed successfully with detailed response.')).toBeInTheDocument()

    // Assert that sensitive fields are not rendered anywhere in the DOM
    const html = container.innerHTML
    expect(html).not.toContain('unauthorized leakage')
    expect(html).not.toContain('secret prompt text')
    expect(html).not.toContain('--sensitive-flag')
  })

  it('JobDetail displays unavailable messages when revision or execution plan are empty', async () => {
    vi.mocked(api.getJob).mockResolvedValue({
      id: 'job-empty-plan',
      project_id: 'proj-1',
      workflow: 'other',
      profile: 'default',
      state: 'failed',
      target_id: '',
      config_revision: '',
      attempts: 1,
      created_at: '2026-09-04 14:00:00',
      updated_at: '2026-09-04 14:01:00',
      execution_plan: {},
      result: {
        error: 'Execution failed due to timeout.',
      },
    })

    render(<JobDetail jobId="job-empty-plan" />)

    expect(await screen.findByText('Job job-empty-plan')).toBeInTheDocument()
    expect(screen.getByText('Configuration revision unavailable')).toBeInTheDocument()
    expect(screen.getByText('Execution plan unavailable')).toBeInTheDocument()
    expect(screen.getByText('Execution failed due to timeout.')).toBeInTheDocument()
  })
})
