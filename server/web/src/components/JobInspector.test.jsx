import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { JobInspector } from './JobInspector.jsx'

describe('JobInspector component', () => {
  const sampleJob = {
    id: 'job-inspect-1',
    workflow: 'code-review',
    profile: 'strict',
    target_id: 'target-alpha',
    context_key: 'session-42',
    state: 'succeeded',
    created_at: '2026-11-03T10:00:00Z',
    updated_at: '2026-11-03T10:05:00Z',
    attempts: 2,
    result: {
      text: 'Analysis complete: No errors found.',
      error: '',
      metadata: {
        telemetry: {
          context_used_tokens: { value: 1540 },
          total_output_tokens: { value: 320 },
        },
      },
    },
    execution_plan: {
      profile: 'strict',
      workflow: 'code-review',
      targets: [{ id: 'target-alpha', model: 'gpt-4o' }],
    },
  }

  it('renders inspector header with id, workflow, profile, target, timestamps, attempts, and telemetry', async () => {
    render(<JobInspector job={sampleJob} />)
    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText('job-inspect-1')).toBeInTheDocument()
    expect(screen.getByText(/code-review/)).toBeInTheDocument()
    expect(screen.getByText(/strict/)).toBeInTheDocument()
    expect(screen.getByText(/target-alpha/)).toBeInTheDocument()
    expect(screen.getByText(/session-42/)).toBeInTheDocument()
    expect(screen.getByText(/Attempts: 2/)).toBeInTheDocument()
    expect(screen.getByText(/1,540/)).toBeInTheDocument()
  })

  it('renders inline "Job not found" state', () => {
    render(<JobInspector notFound={true} jobId="missing-job-99" />)

    expect(screen.getByText(/job not found/i)).toBeInTheDocument()
    expect(screen.getByText('missing-job-99')).toBeInTheDocument()
  })

  it('renders failure card when failure metadata or error is present', async () => {
    const failedJob = {
      ...sampleJob,
      state: 'failed',
      result: {
        text: '',
        error: 'Target unreachable timeout',
        metadata: {
          failure: { kind: 'target_fatal' },
          retry: { retryable: true, next_target: 'target-beta' },
        },
      },
    }

    render(<JobInspector job={failedJob} />)
    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText(/target_fatal/i)).toBeInTheDocument()
    expect(screen.getByText(/Retryable: Yes/i)).toBeInTheDocument()
    expect(screen.getByText(/target-beta/i)).toBeInTheDocument()
    const diagLink = screen.getByRole('link', { name: /view diagnostics/i })
    expect(diagLink).toHaveAttribute('href', '#/diagnostics?job_id=job-inspect-1')

    const card = screen.getByRole('region', { name: /failure details/i })
    expect(card.className).not.toMatch(/stacked/)
    expect(card).toHaveClass('tds-announcement')
  })

  it('renders failure card when only result.error is set without failure metadata', async () => {
    const errorJob = {
      ...sampleJob,
      state: 'failed',
      result: {
        text: '',
        error: 'Execution failed due to network reset',
        metadata: {},
      },
    }

    render(<JobInspector job={errorJob} />)
    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText(/Execution failed due to network reset/i)).toBeInTheDocument()
    expect(screen.getByText(/Failure:/i)).toBeInTheDocument()
    const card = screen.getByRole('region', { name: /failure details/i })
    expect(card.className).not.toMatch(/stacked/)
  })

  it('builds tabs with documented TDS class structure including content and indicator', async () => {
    const { container } = render(<JobInspector job={sampleJob} />)
    await act(async () => {
      await Promise.resolve()
    })

    expect(container.querySelector('.tds-tabs')).toBeInTheDocument()
    expect(container.querySelector('.tds-tabs__row')).toBeInTheDocument()
    expect(container.querySelector('.tds-tabs__list')).toBeInTheDocument()
    expect(container.querySelector('.tds-tabs__divider')).toBeInTheDocument()

    const tabButtons = screen.getAllByRole('tab')
    tabButtons.forEach((btn) => {
      expect(btn.querySelector('.tds-tab-item__content')).toBeInTheDocument()
      expect(btn.querySelector('.tds-tab-item__indicator')).toBeInTheDocument()
    })
  })

  it('supports ARIA tab semantics and tab keyboard navigation', async () => {
    render(<JobInspector job={sampleJob} />)
    await act(async () => {
      await Promise.resolve()
    })

    const tabList = screen.getByRole('tablist')
    const transcriptTab = screen.getByRole('tab', { name: /transcript/i })
    const resultTab = screen.getByRole('tab', { name: /result/i })
    const planTab = screen.getByRole('tab', { name: /plan/i })

    expect(transcriptTab).toHaveAttribute('aria-selected', 'true')
    expect(resultTab).toHaveAttribute('aria-selected', 'false')

    // Navigate to Result tab with keyboard arrow right
    await act(async () => {
      fireEvent.keyDown(tabList, { key: 'ArrowRight' })
    })
    expect(resultTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByText(/Analysis complete: No errors found\./)).toBeInTheDocument()

    // Navigate to Plan tab
    await act(async () => {
      fireEvent.keyDown(tabList, { key: 'ArrowRight' })
    })
    expect(planTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getAllByText(/target-alpha/).length).toBeGreaterThan(1)
  })
})
