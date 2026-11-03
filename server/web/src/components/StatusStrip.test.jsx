import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusStrip } from './StatusStrip.jsx'

describe('StatusStrip component', () => {
  it('renders daemon status, active, queued, unhealthy targets, and config revision', () => {
    const overview = {
      daemon: { status: 'running', workers: 4, active_jobs: 2, queued_jobs: 1 },
      configuration: { valid: true, revision: 'rev-abc1234' },
      projects: 3,
      unhealthy_targets: 1,
    }

    render(<StatusStrip overview={overview} isStale={false} error={null} />)

    expect(screen.getByText(/running/i)).toBeInTheDocument()
    expect(screen.getByText(/2 active/i)).toBeInTheDocument()
    expect(screen.getByText(/1 queued/i)).toBeInTheDocument()
    expect(screen.getByText(/1 unhealthy target/i)).toBeInTheDocument()
    expect(screen.getByText(/rev-abc1234/i)).toBeInTheDocument()
  })

  it('renders disconnected state when error is present', () => {
    render(<StatusStrip overview={null} isStale={false} error={new Error('Connection failed')} />)

    expect(screen.getByText(/disconnected/i)).toBeInTheDocument()
  })

  it('renders stale state indicator when data is marked stale', () => {
    const overview = {
      daemon: { status: 'running', workers: 4, active_jobs: 0, queued_jobs: 0 },
      configuration: { valid: true, revision: 'rev-1' },
      projects: 1,
      unhealthy_targets: 0,
    }

    render(<StatusStrip overview={overview} isStale={true} error={null} />)

    expect(screen.getByText(/stale/i)).toBeInTheDocument()
  })
})
