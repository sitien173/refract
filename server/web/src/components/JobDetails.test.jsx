import { createRef } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import JobDetails from './JobDetails'
import * as api from '../api'

function assertCanonicalMetadata(metadata) {
  expect(metadata).toBeDefined()
  expect(Object.keys(metadata).sort()).toEqual(['execution', 'failure', 'retry', 'telemetry'])
  expect(Object.keys(metadata.execution).sort()).toEqual(['duration_ms', 'model'])
  if (metadata.failure !== null) {
    expect(Object.keys(metadata.failure).sort()).toEqual(['kind'])
  }
  expect(Object.keys(metadata.retry).sort()).toEqual(['next_target', 'retryable'])
  expect(Object.keys(metadata.telemetry).sort()).toEqual([
    'cache_read_tokens',
    'cache_write_tokens',
    'completeness',
    'context_remaining_percent',
    'context_used_tokens',
    'context_window_size',
    'total_input_tokens',
    'total_output_tokens',
  ])
  const metricNames = [
    'context_remaining_percent',
    'context_window_size',
    'context_used_tokens',
    'total_input_tokens',
    'total_output_tokens',
    'cache_read_tokens',
    'cache_write_tokens',
  ]
  for (const name of metricNames) {
    const m = metadata.telemetry[name]
    expect(typeof m).toBe('object')
    expect(m).not.toBeNull()
    expect(Object.keys(m).sort()).toEqual(['observed_at', 'quality', 'source', 'value'])
  }
}

describe('JobDetails component', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getDiagnostics').mockResolvedValue({ reports: [], next_before: null })
  })
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

  it('renders chronological transcript with expandable tool details inside job details view', () => {
    const mockStream = {
      entities: [
        {
          type: 'attempt',
          attempt: 1,
          target_id: 'worker-node-1',
          backend: 'codex',
          status: 'succeeded',
          items: [
            { type: 'assistant_message', entity_id: 'm1', text: 'Analyzing repository.', status: 'completed' },
            {
              type: 'tool_call',
              entity_id: 't1',
              tool_name: 'git_status',
              status: 'completed',
              input: { path: '.' },
              output: 'clean working tree',
            },
            { type: 'assistant_message', entity_id: 'm2', text: 'Repository is clean.', status: 'completed' },
          ],
        },
      ],
      status: 'complete',
      streamStatus: 'complete',
      error: null,
      isLoading: false,
    }

    render(<JobDetails job={mockJob} stream={mockStream} />)

    expect(screen.getByText('Analyzing repository.')).toBeInTheDocument()
    expect(screen.getByText('git_status')).toBeInTheDocument()
    expect(screen.getByText('Repository is clean.')).toBeInTheDocument()

    const details = document.querySelector('details.transcript-tool-disclosure')
    expect(details).toBeInTheDocument()
    expect(details.open).toBe(false)
  })

  it('renders clearly labeled prompt details in a collapsed native details disclosure preserving whitespace', () => {
    const promptJob = {
      ...mockJob,
      prompt: 'Task description:\n  - step one\n  - step two',
    }
    const { container } = render(<JobDetails job={promptJob} />)

    expect(screen.getByRole('heading', { name: 'Prompt details' })).toBeInTheDocument()
    const details = container.querySelector('details.job-prompt-disclosure')
    expect(details).toBeInTheDocument()
    expect(details.open).toBe(false)

    const pre = container.querySelector('pre.prompt-text')
    expect(pre).toBeInTheDocument()
    expect(pre.textContent).toBe('Task description:\n  - step one\n  - step two')
  })

  it('renders explicit unavailable text when stored job prompt is empty', () => {
    const emptyPromptJob = {
      ...mockJob,
      prompt: '',
    }
    render(<JobDetails job={emptyPromptJob} />)

    expect(screen.getByRole('heading', { name: 'Prompt details' })).toBeInTheDocument()
    expect(screen.getByText('Prompt unavailable')).toBeInTheDocument()
  })

  it('strictly displays stored prompt without exposing target system_prompt or execution_plan.raw_prompt', () => {
    const secureJob = {
      ...mockJob,
      prompt: 'Legitimate stored job prompt',
    }
    const { container } = render(<JobDetails job={secureJob} />)

    expect(screen.getAllByText('Legitimate stored job prompt').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('SECRET_SYSTEM_PROMPT_DO_NOT_LEAK')).not.toBeInTheDocument()
    expect(screen.queryByText('SECRET_PROMPT_PAYLOAD')).not.toBeInTheDocument()
    expect(container.innerHTML).not.toContain('SECRET_SYSTEM_PROMPT_DO_NOT_LEAK')
    expect(container.innerHTML).not.toContain('SECRET_PROMPT_PAYLOAD')
  })

  it('passes only exact stored job.prompt as submittedPrompt to transcript and renders User card', () => {
    const promptJob = {
      ...mockJob,
      prompt: 'Exact stored prompt for transcript',
      execution_plan: {
        raw_prompt: 'Expanded prompt secret',
      },
    }
    const mockStream = {
      entities: [
        {
          type: 'attempt',
          attempt: 1,
          status: 'running',
          items: [{ type: 'assistant_message', role: 'assistant', contentType: 'text', text: 'Working on it' }],
        },
      ],
      status: 'live',
      streamStatus: 'active',
      error: null,
      isLoading: false,
    }
    render(<JobDetails job={promptJob} stream={mockStream} />)

    const userCard = document.querySelector('.transcript-user-card')
    expect(userCard).toBeInTheDocument()
    expect(userCard.textContent).toContain('Exact stored prompt for transcript')
    expect(userCard.textContent).not.toContain('Expanded prompt secret')
  })

  it('preserves unavailable stream state without rendering a synthetic User card when historical stream is unavailable', () => {
    const promptJob = {
      ...mockJob,
      prompt: 'Stored prompt that should not appear as transcript',
    }
    const mockStream = {
      entities: [],
      status: 'complete',
      streamStatus: 'unavailable',
      error: null,
      isLoading: false,
    }
    render(<JobDetails job={promptJob} stream={mockStream} />)

    expect(screen.getByText('Transcript is not available for this job.')).toBeInTheDocument()
    expect(document.querySelector('.transcript-user-card')).not.toBeInTheDocument()
  })

  describe('Normalized Telemetry rendering (Phase 4 Task 1)', () => {
    const fullTelemetryJob = {
      ...mockJob,
      state: 'succeeded',
      result: {
        output: 'Done.',
        metadata: {
          execution: {
            model: 'claude-3-7-sonnet',
            duration_ms: 2400,
          },
          failure: null,
          retry: {
            retryable: false,
            next_target: null,
          },
          telemetry: {
            completeness: 'complete',
            context_remaining_percent: {
              value: 65.5,
              quality: 'derived',
              source: 'derived',
              observed_at: '2026-10-26T17:00:00Z',
            },
            context_window_size: {
              value: 128000,
              quality: 'reported',
              source: 'session',
              observed_at: '2026-10-26T17:00:00Z',
            },
            context_used_tokens: {
              value: 44160,
              quality: 'derived',
              source: 'response',
              observed_at: '2026-10-26T17:00:00Z',
            },
            total_input_tokens: {
              value: 12500,
              quality: 'reported',
              source: 'provider',
              observed_at: '2026-10-26T17:00:00Z',
            },
            total_output_tokens: {
              value: 850,
              quality: 'reported',
              source: 'provider',
              observed_at: '2026-10-26T17:00:00Z',
            },
            cache_read_tokens: {
              value: 3000,
              quality: 'reported',
              source: 'provider',
              observed_at: '2026-10-26T17:00:00Z',
            },
            cache_write_tokens: {
              value: 1200,
              quality: 'reported',
              source: 'provider',
              observed_at: '2026-10-26T17:00:00Z',
            },
          },
        },
      },
    }

    it('renders normalized telemetry panel with separated context and consumption, all five primary measurements, quality, source, and observation time', () => {
      assertCanonicalMetadata(fullTelemetryJob.result.metadata)
      render(<JobDetails job={fullTelemetryJob} />)

      expect(screen.getByRole('heading', { name: 'Telemetry' })).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'Context' })).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'Consumption' })).toBeInTheDocument()

      // Primary measurements
      expect(screen.getByText('Context used')).toBeInTheDocument()
      expect(screen.getByText('44160')).toBeInTheDocument()

      expect(screen.getByText('Context capacity')).toBeInTheDocument()
      expect(screen.getByText('128000')).toBeInTheDocument()

      expect(screen.getByText('Context remaining')).toBeInTheDocument()
      expect(screen.getByText('65.5%')).toBeInTheDocument()

      expect(screen.getByText('Job input tokens')).toBeInTheDocument()
      expect(screen.getByText('12500')).toBeInTheDocument()

      expect(screen.getByText('Job output tokens')).toBeInTheDocument()
      expect(screen.getByText('850')).toBeInTheDocument()

      // Cache components
      expect(screen.getByText('Cache read tokens')).toBeInTheDocument()
      expect(screen.getByText('3000')).toBeInTheDocument()
      expect(screen.getByText('Cache write tokens')).toBeInTheDocument()
      expect(screen.getByText('1200')).toBeInTheDocument()

      // Completeness, quality, source, observed_at
      expect(screen.getByText('complete')).toBeInTheDocument()
      expect(screen.getAllByText('derived').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('reported').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('response').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('session').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('2026-10-26T17:00:00Z').length).toBeGreaterThanOrEqual(1)
    })

    it('distinguishes reported zero from unavailable null values', () => {
      const zeroJob = {
        ...mockJob,
        state: 'succeeded',
        result: {
          output: 'Zero output',
          metadata: {
            execution: { model: 'codex-model', duration_ms: 100 },
            failure: null,
            retry: { retryable: false, next_target: null },
            telemetry: {
              completeness: 'complete',
              context_remaining_percent: { value: 100.0, quality: 'derived', source: 'derived', observed_at: '2026-10-26T17:00:00Z' },
              context_window_size: { value: 100000, quality: 'reported', source: 'provider', observed_at: '2026-10-26T17:00:00Z' },
              context_used_tokens: { value: 0, quality: 'reported', source: 'provider', observed_at: '2026-10-26T17:00:00Z' },
              total_input_tokens: { value: 0, quality: 'reported', source: 'provider', observed_at: '2026-10-26T17:00:00Z' },
              total_output_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
              cache_read_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
              cache_write_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
            },
          },
        },
      }
      assertCanonicalMetadata(zeroJob.result.metadata)
      render(<JobDetails job={zeroJob} />)

      // 0 is displayed for context used and input tokens
      expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(2)
      // Total output tokens is unavailable
      expect(screen.getAllByText('Unavailable').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('unavailable').length).toBeGreaterThanOrEqual(1)
    })

    it('distinguishes estimated quality and partial completeness', () => {
      const partialJob = {
        ...mockJob,
        state: 'running',
        result: {
          output: 'Partial output',
          metadata: {
            execution: { model: 'stream-model', duration_ms: 50 },
            failure: null,
            retry: { retryable: null, next_target: null },
            telemetry: {
              completeness: 'partial',
              context_remaining_percent: { value: null, quality: 'unavailable', source: null, observed_at: null },
              context_window_size: { value: null, quality: 'unavailable', source: null, observed_at: null },
              context_used_tokens: { value: 5000, quality: 'estimated', source: 'stream', observed_at: '2026-10-26T17:00:00Z' },
              total_input_tokens: { value: 5000, quality: 'estimated', source: 'stream', observed_at: '2026-10-26T17:00:00Z' },
              total_output_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
              cache_read_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
              cache_write_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
            },
          },
        },
      }
      assertCanonicalMetadata(partialJob.result.metadata)
      render(<JobDetails job={partialJob} />)

      expect(screen.getByText('partial')).toBeInTheDocument()
      expect(screen.getAllByText('estimated').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('stream').length).toBeGreaterThanOrEqual(1)
    })

    it('marks remaining percentage unavailable when capacity is null even if percentage value is supplied', () => {
      const missingCapacityJob = {
        ...mockJob,
        state: 'succeeded',
        result: {
          output: 'No capacity',
          metadata: {
            execution: { model: 'pi-model', duration_ms: 300 },
            failure: null,
            retry: { retryable: false, next_target: null },
            telemetry: {
              completeness: 'complete',
              context_remaining_percent: { value: 75.0, quality: 'derived', source: 'derived', observed_at: '2026-10-26T17:00:00Z' },
              context_window_size: { value: null, quality: 'unavailable', source: null, observed_at: null },
              context_used_tokens: { value: 2000, quality: 'reported', source: 'provider', observed_at: '2026-10-26T17:00:00Z' },
              total_input_tokens: { value: 2000, quality: 'reported', source: 'provider', observed_at: '2026-10-26T17:00:00Z' },
              total_output_tokens: { value: 100, quality: 'reported', source: 'provider', observed_at: '2026-10-26T17:00:00Z' },
              cache_read_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
              cache_write_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
            },
          },
        },
      }
      assertCanonicalMetadata(missingCapacityJob.result.metadata)
      render(<JobDetails job={missingCapacityJob} />)

      expect(screen.getByText('Context remaining')).toBeInTheDocument()
      // Should NOT render 75.0% or 75% because capacity is unknown
      expect(screen.queryByText('75%')).not.toBeInTheDocument()
      expect(screen.queryByText('75.0%')).not.toBeInTheDocument()
    })

    it('renders canonical unavailable telemetry snapshot in terminal and running states without internal fields', () => {
      const terminalUnavailableJob = {
        ...mockJob,
        state: 'succeeded',
        result: {
          output: 'Done.',
          metadata: {
            execution: { model: 'claude-3-7-sonnet', duration_ms: 500 },
            failure: null,
            retry: { retryable: false, next_target: null },
            telemetry: {
              completeness: 'unavailable',
              context_remaining_percent: { value: null, source: null, quality: 'unavailable', observed_at: null },
              context_window_size: { value: null, source: null, quality: 'unavailable', observed_at: null },
              context_used_tokens: { value: null, source: null, quality: 'unavailable', observed_at: null },
              total_input_tokens: { value: null, source: null, quality: 'unavailable', observed_at: null },
              total_output_tokens: { value: null, source: null, quality: 'unavailable', observed_at: null },
              cache_read_tokens: { value: null, source: null, quality: 'unavailable', observed_at: null },
              cache_write_tokens: { value: null, source: null, quality: 'unavailable', observed_at: null },
            },
          },
        },
      }
      assertCanonicalMetadata(terminalUnavailableJob.result.metadata)

      const { rerender } = render(<JobDetails job={terminalUnavailableJob} />)
      expect(screen.getByRole('heading', { name: 'Telemetry' })).toBeInTheDocument()
      expect(document.querySelector('.telemetry-completeness')).toHaveTextContent('unavailable')
      expect(screen.getAllByText('Unavailable')).toHaveLength(5)
      expect(screen.queryByText('Cache read tokens')).not.toBeInTheDocument()
      expect(screen.queryByText('Cache write tokens')).not.toBeInTheDocument()
      expect(screen.queryByText(/Live polling active/i)).not.toBeInTheDocument()

      const runningUnavailableJob = {
        ...terminalUnavailableJob,
        state: 'running',
      }
      assertCanonicalMetadata(runningUnavailableJob.result.metadata)
      rerender(<JobDetails job={runningUnavailableJob} />)
      expect(screen.getByText(/Live polling active/i)).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'Telemetry' })).toBeInTheDocument()
      expect(document.querySelector('.telemetry-completeness')).toHaveTextContent('unavailable')
    })

    it('does not fabricate measurements for historical migrated jobs with unavailable canonical telemetry', () => {
      const historicalMigratedJob = {
        ...mockJob,
        state: 'succeeded',
        result: {
          output: 'Historical output',
          metadata: {
            execution: { model: 'historical-model', duration_ms: null },
            failure: null,
            retry: { retryable: null, next_target: null },
            telemetry: {
              completeness: 'unavailable',
              context_remaining_percent: { value: null, source: null, quality: 'unavailable', observed_at: null },
              context_window_size: { value: null, source: null, quality: 'unavailable', observed_at: null },
              context_used_tokens: { value: null, source: null, quality: 'unavailable', observed_at: null },
              total_input_tokens: { value: null, source: null, quality: 'unavailable', observed_at: null },
              total_output_tokens: { value: null, source: null, quality: 'unavailable', observed_at: null },
              cache_read_tokens: { value: null, source: null, quality: 'unavailable', observed_at: null },
              cache_write_tokens: { value: null, source: null, quality: 'unavailable', observed_at: null },
            },
          },
        },
      }
      assertCanonicalMetadata(historicalMigratedJob.result.metadata)

      render(<JobDetails job={historicalMigratedJob} />)

      expect(screen.getByRole('heading', { name: 'Telemetry' })).toBeInTheDocument()
      expect(document.querySelector('.telemetry-completeness')).toHaveTextContent('unavailable')
      expect(screen.getAllByText('Unavailable')).toHaveLength(5)
      expect(screen.queryByText('Cache read tokens')).not.toBeInTheDocument()
      expect(screen.queryByText('Cache write tokens')).not.toBeInTheDocument()
    })

    it('handles jobs with genuinely absent result or absent result metadata cleanly without rendering telemetry', () => {
      const absentResultJob = {
        ...mockJob,
        state: 'running',
        result: null,
      }
      const { rerender } = render(<JobDetails job={absentResultJob} />)
      expect(screen.getByText('Telemetry unavailable')).toBeInTheDocument()
      expect(screen.queryByText('Context used')).not.toBeInTheDocument()

      const emptyResultJob = {
        ...mockJob,
        state: 'succeeded',
        result: {
          output: 'No metadata present',
        },
      }
      rerender(<JobDetails job={emptyResultJob} />)
      expect(screen.getByText('Telemetry unavailable')).toBeInTheDocument()
      expect(screen.queryByText('Context used')).not.toBeInTheDocument()
    })

    describe('Estimated context explanation and measurement rendering (Phase 3 Task 2)', () => {
      it('renders estimated badges and explanatory caption for server-qualified estimated context', () => {
        const estimatedContextJob = {
          ...mockJob,
          state: 'succeeded',
          result: {
            output: 'Done.',
            metadata: {
              execution: { model: 'claude-3-7-sonnet', duration_ms: 2400 },
              failure: null,
              retry: { retryable: false, next_target: null },
              telemetry: {
                completeness: 'complete',
                context_remaining_percent: {
                  value: 85.0,
                  quality: 'estimated',
                  source: 'derived',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                context_window_size: {
                  value: 100000,
                  quality: 'reported',
                  source: 'target_config',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                context_used_tokens: {
                  value: 15000,
                  quality: 'estimated',
                  source: 'derived',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                total_input_tokens: {
                  value: 10000,
                  quality: 'reported',
                  source: 'provider',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                total_output_tokens: {
                  value: 5000,
                  quality: 'reported',
                  source: 'provider',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                cache_read_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
                cache_write_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
              },
            },
          },
        };
        assertCanonicalMetadata(estimatedContextJob.result.metadata);
        render(<JobDetails job={estimatedContextJob} />);

        const estimatedBadges = screen.getAllByText('estimated');
        expect(estimatedBadges.length).toBeGreaterThanOrEqual(2);
        expect(screen.getByText('target_config')).toBeInTheDocument();

        const caption = document.querySelector('.telemetry-estimate-caption');
        expect(caption).toBeInTheDocument();
        expect(caption.textContent).toContain('cumulative job input plus output');
        expect(caption.textContent).toContain('overcount across turns, retries, and compaction');
      });

      it('excludes explanation caption when context usage is reported from provider snapshot', () => {
        const providerContextJob = {
          ...mockJob,
          state: 'succeeded',
          result: {
            output: 'Done.',
            metadata: {
              execution: { model: 'claude-3-7-sonnet', duration_ms: 2400 },
              failure: null,
              retry: { retryable: false, next_target: null },
              telemetry: {
                completeness: 'complete',
                context_remaining_percent: {
                  value: 85.0,
                  quality: 'derived',
                  source: 'derived',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                context_window_size: {
                  value: 100000,
                  quality: 'reported',
                  source: 'target_config',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                context_used_tokens: {
                  value: 15000,
                  quality: 'estimated',
                  source: 'provider',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                total_input_tokens: {
                  value: 10000,
                  quality: 'reported',
                  source: 'provider',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                total_output_tokens: {
                  value: 5000,
                  quality: 'reported',
                  source: 'provider',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                cache_read_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
                cache_write_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
              },
            },
          },
        };
        assertCanonicalMetadata(providerContextJob.result.metadata);
        render(<JobDetails job={providerContextJob} />);

        expect(document.querySelector('.telemetry-estimate-caption')).toBeNull();
        expect(screen.queryByText(/cumulative job input plus output/i)).not.toBeInTheDocument();
        expect(screen.getAllByText('estimated').length).toBeGreaterThan(0);
      });

      it('excludes explanation caption when consumption is estimated but context is reported provider snapshot', () => {
        const estimatedConsumptionJob = {
          ...mockJob,
          state: 'running',
          result: {
            output: 'Running...',
            metadata: {
              execution: { model: 'claude-3-7-sonnet', duration_ms: 1000 },
              failure: null,
              retry: { retryable: null, next_target: null },
              telemetry: {
                completeness: 'partial',
                context_remaining_percent: {
                  value: 70.0,
                  quality: 'derived',
                  source: 'derived',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                context_window_size: {
                  value: 100000,
                  quality: 'reported',
                  source: 'session',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                context_used_tokens: {
                  value: 30000,
                  quality: 'reported',
                  source: 'provider',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                total_input_tokens: {
                  value: 25000,
                  quality: 'estimated',
                  source: 'stream',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                total_output_tokens: {
                  value: 5000,
                  quality: 'estimated',
                  source: 'stream',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                cache_read_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
                cache_write_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
              },
            },
          },
        };
        assertCanonicalMetadata(estimatedConsumptionJob.result.metadata);
        render(<JobDetails job={estimatedConsumptionJob} />);

        expect(document.querySelector('.telemetry-estimate-caption')).toBeNull();
        expect(screen.queryByText(/cumulative job input plus output/i)).not.toBeInTheDocument();
      });

      it('preserves provider percentage when usage is absent and no configured capacity exists', () => {
        const percentageOnlyJob = {
          ...fullTelemetryJob,
          result: {
            ...fullTelemetryJob.result,
            metadata: {
              ...fullTelemetryJob.result.metadata,
              telemetry: {
                ...fullTelemetryJob.result.metadata.telemetry,
                context_remaining_percent: {
                  value: 42.5,
                  quality: 'reported',
                  source: 'provider',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                context_window_size: {
                  value: 100000,
                  quality: 'reported',
                  source: 'provider',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                context_used_tokens: {
                  value: null,
                  quality: 'unavailable',
                  source: null,
                  observed_at: null,
                },
              },
            },
          },
        };
        assertCanonicalMetadata(percentageOnlyJob.result.metadata);
        render(<JobDetails job={percentageOnlyJob} />);
        expect(screen.getByText('42.5%')).toBeInTheDocument();
        expect(screen.getAllByText('provider').length).toBeGreaterThan(0);
      });

      it('renders unavailable remaining when capacity is known but usage is unavailable without displaying 100%', () => {
        const capacityWithoutUsageJob = {
          ...mockJob,
          state: 'succeeded',
          result: {
            output: 'Done.',
            metadata: {
              execution: { model: 'claude-3-7-sonnet', duration_ms: 2400 },
              failure: null,
              retry: { retryable: false, next_target: null },
              telemetry: {
                completeness: 'partial',
                context_remaining_percent: {
                  value: null,
                  quality: 'unavailable',
                  source: null,
                  observed_at: null,
                },
                context_window_size: {
                  value: 200000,
                  quality: 'reported',
                  source: 'target_config',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                context_used_tokens: {
                  value: null,
                  quality: 'unavailable',
                  source: null,
                  observed_at: null,
                },
                total_input_tokens: {
                  value: 1000,
                  quality: 'reported',
                  source: 'provider',
                  observed_at: '2026-10-29T10:00:00Z',
                },
                total_output_tokens: {
                  value: null,
                  quality: 'unavailable',
                  source: null,
                  observed_at: null,
                },
                cache_read_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
                cache_write_tokens: { value: null, quality: 'unavailable', source: null, observed_at: null },
              },
            },
          },
        };
        assertCanonicalMetadata(capacityWithoutUsageJob.result.metadata);
        render(<JobDetails job={capacityWithoutUsageJob} />);

        expect(screen.getByText('Context capacity')).toBeInTheDocument();
        expect(screen.getByText('200000')).toBeInTheDocument();
        expect(screen.getByText('target_config')).toBeInTheDocument();

        expect(screen.getByText('Context remaining')).toBeInTheDocument();
        expect(screen.queryByText('100%')).not.toBeInTheDocument();
        expect(screen.queryByText('100.0%')).not.toBeInTheDocument();

        expect(document.querySelector('.telemetry-estimate-caption')).toBeNull();
      });
    })
  })

  describe('Diagnostic reports and suspect indicator', () => {
    it('renders a visually separate textual suspect badge when job is suspect, preserving execution status', () => {
      const suspectJob = {
        ...mockJob,
        state: 'succeeded',
        suspect: true,
        diagnostic_count: 2,
      }
      render(<JobDetails job={suspectJob} />)

      // Execution status remains intact
      expect(screen.getByText('succeeded')).toBeInTheDocument()

      // Textual suspect badge with non-color marker
      const suspectBadges = screen.getAllByText('Suspect')
      expect(suspectBadges.length).toBeGreaterThanOrEqual(1)
      const badge = suspectBadges[0].closest('.suspect-badge')
      expect(badge).toBeInTheDocument()
      expect(badge.querySelector('.suspect-icon')).toBeInTheDocument()
    })

    it('fetches bounded reports and renders them with explicit current state as plain text', async () => {
      const diagSpy = vi.spyOn(api, 'getDiagnostics').mockResolvedValue({
        reports: [
          {
            id: '501',
            job_id: mockJob.id,
            category: 'protocol',
            created_at: '2026-10-27 15:30:00',
            expected: 'JSON response <b>schema</b>',
            observed: 'Raw string <img src="x" onerror="alert(1)" />',
            project_id: mockJob.project_id,
            current_state: 'succeeded',
          },
        ],
        next_before: null,
      })

      const { container } = render(<JobDetails job={mockJob} />)

      await waitFor(() => {
        expect(diagSpy).toHaveBeenCalledWith(
          expect.objectContaining({ jobId: mockJob.id, limit: 50 }),
          expect.anything()
        )
      })

      expect(await screen.findByText('501')).toBeInTheDocument()
      expect(screen.getByText('protocol')).toBeInTheDocument()
      expect(screen.getByText('2026-10-27 15:30:00')).toBeInTheDocument()
      expect(screen.getByText(/Current: succeeded/)).toBeInTheDocument()

      // Plain text check: raw HTML tags rendered as text, not HTML elements
      expect(screen.getByText(/JSON response <b>schema<\/b>/)).toBeInTheDocument()
      expect(screen.getByText(/Raw string <img src="x"/)).toBeInTheDocument()
      expect(container.querySelector('b')).toBeNull()
      expect(container.querySelector('img[onerror]')).toBeNull()
    })

    it('renders empty message when job has no diagnostic reports', async () => {
      vi.spyOn(api, 'getDiagnostics').mockResolvedValue({ reports: [], next_before: null })

      render(<JobDetails job={mockJob} />)

      expect(await screen.findByText(/No diagnostic reports for this job/i)).toBeInTheDocument()
    })

    it('handles reports error alert and refresh discovery on terminal job', async () => {
      const onRefresh = vi.fn()
      const diagSpy = vi.spyOn(api, 'getDiagnostics')
        .mockResolvedValueOnce({ reports: [], next_before: null })
        .mockResolvedValueOnce({
          reports: [
            {
              id: '502',
              job_id: mockJob.id,
              category: 'output',
              created_at: '2026-10-27 16:00:00',
              expected: 'Valid output',
              observed: 'Empty output',
              project_id: mockJob.project_id,
              current_state: 'succeeded',
            },
          ],
          next_before: null,
        })

      const terminalJob = {
        ...mockJob,
        state: 'succeeded',
      }

      render(<JobDetails job={terminalJob} onRefresh={onRefresh} />)

      expect(await screen.findByText(/No diagnostic reports for this job/i)).toBeInTheDocument()

      const refreshBtn = screen.getByRole('button', { name: /Refresh job details/i })
      fireEvent.click(refreshBtn)

      expect(onRefresh).toHaveBeenCalledTimes(1)
      expect(await screen.findByText('502')).toBeInTheDocument()
      expect(screen.getByText('Valid output')).toBeInTheDocument()
    })

    it('renders explicit client-observation label, bounded-subset indication, and link to diagnostics when next_before is present', async () => {
      vi.spyOn(api, 'getDiagnostics').mockResolvedValue({
        reports: [
          {
            id: '501',
            job_id: mockJob.id,
            category: 'protocol',
            created_at: '2026-10-27 15:30:00',
            expected: 'Valid protocol response',
            observed: 'Unexpected status code',
            project_id: mockJob.project_id,
            current_state: 'succeeded',
          },
        ],
        next_before: '450',
      })

      render(<JobDetails job={mockJob} />)

      // Explicit client-observation labeling
      expect(await screen.findByText(/Client observations, not verified server failures/i)).toBeInTheDocument()

      // Bounded subset indication
      expect(screen.getByText(/bounded newest subset/i)).toBeInTheDocument()

      // Link to inspect remaining reports in diagnostics
      const link = screen.getByRole('link', { name: /Inspect remaining reports/i })
      expect(link).toBeInTheDocument()
      expect(link).toHaveAttribute(
        'href',
        `/dashboard/diagnostics?job_id=${encodeURIComponent(mockJob.id)}`
      )
    })

    it('clears old reports when job identity changes and does not attribute job A data to job B on slow or failed request', async () => {
      let rejectJobB
      const jobBPromise = new Promise((resolve, reject) => {
        rejectJobB = reject
      })

      const diagSpy = vi.spyOn(api, 'getDiagnostics')
        .mockResolvedValueOnce({
          reports: [
            {
              id: 'report-for-job-A',
              job_id: 'job-A',
              category: 'protocol',
              created_at: '2026-10-27 15:00:00',
              expected: 'Job A expected',
              observed: 'Job A observed',
              project_id: 'proj-1',
              current_state: 'failed',
            },
          ],
          next_before: null,
        })
        .mockImplementationOnce(() => jobBPromise)

      const jobA = { ...mockJob, id: 'job-A' }
      const jobB = { ...mockJob, id: 'job-B' }

      const { rerender } = render(<JobDetails job={jobA} />)

      // Job A reports load
      expect(await screen.findByText('report-for-job-A')).toBeInTheDocument()

      // Switch to job B
      rerender(<JobDetails job={jobB} />)

      // Job A reports must immediately NOT be in the document
      expect(screen.queryByText('report-for-job-A')).toBeNull()

      // Job B request fails
      rejectJobB(new Error('Failed to fetch job B diagnostics'))

      // Must show error alert, NEVER job A reports
      expect(await screen.findByText(/Failed to fetch job B diagnostics/i)).toBeInTheDocument()
      expect(screen.queryByText('report-for-job-A')).toBeNull()
      expect(screen.queryByText(/Showing previously loaded diagnostic reports/i)).toBeNull()
    })

    it('ignores late responses when switching jobs and preserves same-job refresh-failure with warning', async () => {
      let resolveSlowA
      const slowAPromise = new Promise((resolve) => {
        resolveSlowA = resolve
      })

      vi.spyOn(api, 'getDiagnostics')
        .mockImplementationOnce(() => slowAPromise)
        .mockResolvedValueOnce({
          reports: [
            {
              id: 'report-for-job-B',
              job_id: 'job-B',
              category: 'output',
              created_at: '2026-10-27 15:30:00',
              expected: 'Job B expected',
              observed: 'Job B observed',
              project_id: 'proj-1',
              current_state: 'succeeded',
            },
          ],
          next_before: null,
        })

      const jobA = { ...mockJob, id: 'job-A' }
      const jobB = { ...mockJob, id: 'job-B' }
      const onRefresh = vi.fn()

      const { rerender } = render(<JobDetails job={jobA} onRefresh={onRefresh} />)

      // Quickly switch to job B while job A request is still in-flight
      rerender(<JobDetails job={jobB} onRefresh={onRefresh} />)

      // Job B finishes
      expect(await screen.findByText('report-for-job-B')).toBeInTheDocument()

      // Now slow A finishes late
      resolveSlowA({
        reports: [
          {
            id: 'late-report-A',
            job_id: 'job-A',
            category: 'protocol',
            created_at: '2026-10-27 15:00:00',
            expected: 'Late A expected',
            observed: 'Late A observed',
            project_id: 'proj-1',
            current_state: 'failed',
          },
        ],
        next_before: null,
      })

      // Wait a tick and verify late-report-A is NOT displayed
      await new Promise((r) => setTimeout(r, 50))
      expect(screen.queryByText('late-report-A')).toBeNull()
      expect(screen.getByText('report-for-job-B')).toBeInTheDocument()

      // Now test same-job refresh failure: job B refresh fails
      vi.spyOn(api, 'getDiagnostics').mockRejectedValueOnce(new Error('Daemon unreachable on refresh'))
      const refreshBtn = screen.getByRole('button', { name: /Refresh job/i })
      fireEvent.click(refreshBtn)

      // Warning alert is shown, and report-for-job-B is preserved!
      expect(await screen.findByText(/Showing previously loaded diagnostic reports/i)).toBeInTheDocument()
      expect(screen.getByText('report-for-job-B')).toBeInTheDocument()
    })
  })
})
