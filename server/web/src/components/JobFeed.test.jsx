import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { JobFeed } from './JobFeed.jsx'

describe('JobFeed component', () => {
  const activeJobs = [
    { id: 'job-act-1', workflow: 'review', state: 'running', target_id: 'gpt-4o' },
    { id: 'job-act-2', workflow: 'consult', state: 'queued', target_id: 'claude-3-5' },
  ]
  const recentJobs = [
    { id: 'job-rec-1', workflow: 'impl', state: 'succeeded', target_id: 'gpt-4o' },
    { id: 'job-rec-2', workflow: 'review', state: 'failed', target_id: 'claude-3-5' },
  ]

  it('renders ACTIVE and RECENT sections with more_recent note', () => {
    render(
      <JobFeed
        activeJobs={activeJobs}
        recentJobs={recentJobs}
        moreRecent={5}
        selectedJobId="job-act-1"
        onSelectJob={() => {}}
      />
    )

    expect(screen.getByText(/ACTIVE/)).toBeInTheDocument()
    expect(screen.getByText('job-act-1')).toBeInTheDocument()
    expect(screen.getByText('job-act-2')).toBeInTheDocument()

    expect(screen.getByText(/RECENT/)).toBeInTheDocument()
    expect(screen.getByText('job-rec-1')).toBeInTheDocument()
    expect(screen.getByText('job-rec-2')).toBeInTheDocument()

    expect(screen.getByText(/\+5 more recent/i)).toBeInTheDocument()
  })

  it('implements roving tabindex: ArrowDown and ArrowUp move focus and activeElement', () => {
    const onSelectJob = vi.fn()
    render(
      <JobFeed
        activeJobs={activeJobs}
        recentJobs={recentJobs}
        moreRecent={0}
        selectedJobId="job-act-1"
        onSelectJob={onSelectJob}
      />
    )

    const items = screen.getAllByRole('button', { name: /job-/i })
    expect(items[0]).toHaveAttribute('tabindex', '0')
    expect(items[1]).toHaveAttribute('tabindex', '-1')

    items[0].focus()
    expect(document.activeElement).toBe(items[0])

    fireEvent.keyDown(items[0], { key: 'ArrowDown' })
    expect(document.activeElement).toBe(items[1])
    expect(items[1]).toHaveAttribute('tabindex', '0')
    expect(items[0]).toHaveAttribute('tabindex', '-1')

    fireEvent.keyDown(items[1], { key: 'ArrowUp' })
    expect(document.activeElement).toBe(items[0])
    expect(items[0]).toHaveAttribute('tabindex', '0')
    expect(items[1]).toHaveAttribute('tabindex', '-1')

    fireEvent.keyDown(items[0], { key: ' ' })
    expect(onSelectJob).toHaveBeenCalledWith('job-act-1')
  })

  it('supports "follow newest running job" toggle', () => {
    const onToggleFollowNewest = vi.fn()
    render(
      <JobFeed
        activeJobs={activeJobs}
        recentJobs={recentJobs}
        moreRecent={0}
        selectedJobId="job-act-1"
        onSelectJob={() => {}}
        followNewestRunning={false}
        onToggleFollowNewest={onToggleFollowNewest}
      />
    )

    const toggle = screen.getByRole('checkbox', { name: /follow newest running job/i })
    expect(toggle).not.toBeChecked()

    fireEvent.click(toggle)
    expect(onToggleFollowNewest).toHaveBeenCalledWith(true)
  })

  it('clamps roving focused index when job list changes or selected job disappears', () => {
    const jobs = [
      { id: 'job-1', state: 'running' },
      { id: 'job-2', state: 'succeeded' },
      { id: 'job-3', state: 'failed' },
    ]

    const { rerender } = render(
      <JobFeed
        activeJobs={[jobs[0]]}
        recentJobs={[jobs[1], jobs[2]]}
        selectedJobId="job-3"
      />
    )

    expect(screen.getByRole('button', { name: /job job-3/i })).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('button', { name: /job job-1/i })).toHaveAttribute('tabindex', '-1')

    const remainingJobs = [jobs[0], jobs[1]]
    rerender(
      <JobFeed
        activeJobs={[remainingJobs[0]]}
        recentJobs={[remainingJobs[1]]}
        selectedJobId="job-3"
      />
    )

    expect(screen.getByRole('button', { name: /job job-1/i })).toHaveAttribute('tabindex', '0')
    expect(screen.getByRole('button', { name: /job job-2/i })).toHaveAttribute('tabindex', '-1')
  })
})
