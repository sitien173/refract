import { createRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import JobDetails from './JobDetails'
import * as api from '../api'

describe('JobDetails component', () => {
  const mockJob = {
    id: 'job-xyz-123',
    project_id: 'proj-alpha',
    workflow: 'implement',
    profile: 'strict-review',
    state: 'running',
    target_id: 'target-node-1',
    context_key: 'ctx-abc-999',
    attempts: 2,
    config_revision: 'rev-sha256-abcdef1234567890',
    created_at: '2026-09-08 10:00:00',
    updated_at: '2026-09-08 10:05:00',
    execution_plan: {
      profile: 'strict-review',
      workflow: 'implement',
      selection: {
        targets: ['target-node-1', 'target-node-2'],
        max_attempts: 3,
        timeout_s: 180,
      },
      targets: [
        {
          id: 'target-node-1',
          backend: 'codex',
          model: 'claude-3-7-sonnet',
          isolated: true,
          read_only: false,
          max_concurrency: 4,
          system_prompt: 'SECRET_SYSTEM_PROMPT_DO_NOT_LEAK',
          secret_key: 'API_KEY_LEAK_CHECK',
        },
      ],
      raw_prompt: 'SECRET_PROMPT_PAYLOAD',
      env: { SECRET_ENV_VAR: 'TOP_SECRET' },
    },
    result: {
      error: 'Execution warning in sub-task',
      output: 'All tests compiled and passed.',
    },
  }

  it('renders all allowlisted job metadata and execution status', () => {
    render(<JobDetails job={mockJob} />)

    expect(screen.getByRole('heading', { name: 'Job job-xyz-123' })).toBeInTheDocument()
    expect(screen.getAllByText('proj-alpha').length).toBeGreaterThan(0)
    expect(screen.getAllByText('strict-review').length).toBeGreaterThan(0)
    expect(screen.getAllByText('target-node-1').length).toBeGreaterThan(0)
    expect(screen.getByText('ctx-abc-999')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('2026-09-08 10:00:00')).toBeInTheDocument()
    expect(screen.getByText('2026-09-08 10:05:00')).toBeInTheDocument()
    expect(screen.getByText('rev-sha256-abcdef1234567890')).toBeInTheDocument()
  })

  it('renders allowlisted execution plan details and candidate targets', () => {
    render(<JobDetails job={mockJob} />)

    expect(screen.getByText('target-node-1, target-node-2')).toBeInTheDocument()
    expect(screen.getByText('180s')).toBeInTheDocument()
    expect(screen.getByText('claude-3-7-sonnet')).toBeInTheDocument()
    expect(screen.getByText(/Isolation: Isolated/)).toBeInTheDocument()
    expect(screen.getByText(/Access: Read-write/)).toBeInTheDocument()
  })

  it('strictly excludes sensitive/non-allowlisted execution plan fields', () => {
    const { container } = render(<JobDetails job={mockJob} />)

    expect(screen.queryByText('SECRET_SYSTEM_PROMPT_DO_NOT_LEAK')).not.toBeInTheDocument()
    expect(screen.queryByText('API_KEY_LEAK_CHECK')).not.toBeInTheDocument()
    expect(screen.queryByText('SECRET_PROMPT_PAYLOAD')).not.toBeInTheDocument()
    expect(screen.queryByText('TOP_SECRET')).not.toBeInTheDocument()
    expect(container.innerHTML).not.toContain('SECRET_SYSTEM_PROMPT_DO_NOT_LEAK')
    expect(container.innerHTML).not.toContain('SECRET_PROMPT_PAYLOAD')
  })

  it('renders execution results including errors and output', () => {
    render(<JobDetails job={mockJob} />)

    expect(screen.getByText('Execution warning in sub-task')).toBeInTheDocument()
    expect(screen.getByText('All tests compiled and passed.')).toBeInTheDocument()
  })

  it('shows polling indicator for active jobs and hides it for terminal jobs', () => {
    const { rerender } = render(<JobDetails job={mockJob} />)
    expect(screen.getByText(/Live polling active/i)).toBeInTheDocument()

    const terminalJob = { ...mockJob, state: 'succeeded' }
    rerender(<JobDetails job={terminalJob} />)
    expect(screen.queryByText(/Live polling active/i)).not.toBeInTheDocument()
  })

  it('renders warning alert on refreshError while preserving displayed job details', () => {
    render(<JobDetails job={mockJob} refreshError="Failed to refresh" />)

    expect(screen.getByText(/Background refresh failed/i)).toBeInTheDocument()
    expect(screen.getByText('job-xyz-123')).toBeInTheDocument()
  })

  it('calls onBack and onRefresh callbacks when buttons are clicked', () => {
    const handleBack = vi.fn()
    const handleRefresh = vi.fn()

    render(<JobDetails job={mockJob} onBack={handleBack} onRefresh={handleRefresh} />)

    fireEvent.click(screen.getByRole('button', { name: /Back to jobs list/i }))
    expect(handleBack).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByRole('button', { name: /Refresh job details/i }))
    expect(handleRefresh).toHaveBeenCalledTimes(1)
  })

  it('renders error view when job failed to load and no job data is present', () => {
    const handleBack = vi.fn()
    render(<JobDetails error={{ message: 'Job not found' }} onBack={handleBack} />)

    expect(screen.getByText('Job not found')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Back to jobs list/i }))
    expect(handleBack).toHaveBeenCalledTimes(1)
  })

  it('binds headingRef with tabIndex -1 to allow programmatic focus', () => {
    const ref = createRef()
    render(<JobDetails job={mockJob} headingRef={ref} />)

    expect(ref.current).toBeInTheDocument()
    expect(ref.current).toHaveAttribute('tabindex', '-1')
    ref.current.focus()
    expect(document.activeElement).toBe(ref.current)
  })

  it('renders transcript section above execution result', () => {
    const mockStream = {
      entities: [
        {
          type: 'attempt',
          attempt: 1,
          target_id: 'target-node-1',
          backend: 'codex',
          status: 'running',
          items: [
            { type: 'assistant_message', entity_id: 'm1', text: 'Live streaming progress', status: 'streaming' },
          ],
        },
      ],
      status: 'live',
      streamStatus: 'active',
      error: null,
      isLoading: false,
    }

    render(<JobDetails job={mockJob} stream={mockStream} />)

    expect(screen.getByText('Live streaming progress')).toBeInTheDocument()
    expect(screen.getByText('Execution status')).toBeInTheDocument()
  })

  it('suppresses duplicate final result text when transcript matches job.result.text exactly', () => {
    const matchingJob = {
      ...mockJob,
      state: 'succeeded',
      result: { text: 'Exact matching text.' },
    }
    const mockStream = {
      entities: [
        {
          type: 'attempt',
          attempt: 1,
          target_id: 'target-node-1',
          backend: 'codex',
          status: 'succeeded',
          items: [
            { type: 'assistant_message', entity_id: 'm1', text: 'Exact matching text.', status: 'completed' },
          ],
        },
      ],
      status: 'complete',
      streamStatus: 'complete',
      error: null,
      isLoading: false,
    }

    render(<JobDetails job={matchingJob} stream={mockStream} />)

    // Transcript has the text
    expect(screen.getByText('Exact matching text.')).toBeInTheDocument()
    // Duplicate "Result output" block is suppressed
    expect(screen.queryByText('Result output')).not.toBeInTheDocument()
  })

  it('does not suppress final result when text differs by whitespace', () => {
    const whitespaceJob = {
      ...mockJob,
      state: 'succeeded',
      result: { text: 'Exact matching text.\n' },
    }
    const mockStream = {
      entities: [
        {
          type: 'attempt',
          attempt: 1,
          target_id: 'target-node-1',
          backend: 'codex',
          status: 'succeeded',
          items: [
            { type: 'assistant_message', entity_id: 'm1', text: 'Exact matching text.', status: 'completed' },
          ],
        },
      ],
      status: 'complete',
      streamStatus: 'complete',
      error: null,
      isLoading: false,
    }

    render(<JobDetails job={whitespaceJob} stream={mockStream} />)

    // Both transcript and authoritative result output render because text differs by trailing whitespace
    expect(screen.getAllByText(/Exact matching text/)).toHaveLength(2)
    expect(screen.getByText('Result output')).toBeInTheDocument()
  })

  it('retains authoritative result output when transcript is truncated or unavailable', () => {
    const truncatedJob = {
      ...mockJob,
      state: 'succeeded',
      result: { text: 'Authoritative final text.' },
    }
    const mockStream = {
      entities: [
        {
          type: 'attempt',
          attempt: 1,
          target_id: 'target-node-1',
          backend: 'codex',
          status: 'succeeded',
          items: [
            { type: 'assistant_message', entity_id: 'm1', text: 'Partial...', status: 'streaming' },
            { type: 'truncated', reason: 'max_job_bytes' },
          ],
        },
      ],
      status: 'truncated',
      streamStatus: 'truncated',
      error: null,
      isLoading: false,
    }

    render(<JobDetails job={truncatedJob} stream={mockStream} />)

    expect(screen.getByText('Result output')).toBeInTheDocument()
    expect(screen.getByText('Authoritative final text.')).toBeInTheDocument()
  })

  it('handles loading-to-job transition without altering React hook execution order', () => {
    // Initial render with no job while loading
    const { rerender } = render(<JobDetails job={null} isLoading={true} />)
    expect(screen.getByTestId('job-details-loading')).toBeInTheDocument()

    // Transition to loaded job state
    rerender(<JobDetails job={mockJob} isLoading={false} />)
    expect(screen.getByTestId('job-details')).toBeInTheDocument()
    expect(screen.getByText('Job job-xyz-123')).toBeInTheDocument()
  })

  it('makes no network request when job is absent', () => {
    const getJobOutputSpy = vi.spyOn(api, 'getJobOutput')
    render(<JobDetails job={null} isLoading={true} />)
    expect(getJobOutputSpy).not.toHaveBeenCalled()
  })
})
