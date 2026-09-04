import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import Overview from './Overview'

vi.mock('../api', () => ({
  getOverview: vi.fn(),
}))

describe('Overview screen', () => {
  it('renders overview metrics and links to filtered views', async () => {
    vi.mocked(api.getOverview).mockResolvedValue({
      daemon: { status: 'running', workers: 2, active_jobs: 3, queued_jobs: 1 },
      configuration: { valid: true, revision: 'rev-abc-123' },
      projects: 5,
      unhealthy_targets: 1,
    })

    const onNavigate = vi.fn()
    render(<Overview onNavigate={onNavigate} />)

    expect(await screen.findByText('Daemon running')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('rev-abc-123')).toBeInTheDocument()

    // Test project link
    const projectsLink = screen.getByText('5').closest('a')
    expect(projectsLink).toHaveAttribute('href', '/dashboard/projects')
    fireEvent.click(projectsLink)
    expect(onNavigate).toHaveBeenCalledWith('/dashboard/projects')

    // Test targets attention link
    const targetsLink = screen.getByText('1').closest('a')
    expect(targetsLink).toHaveAttribute('href', '/dashboard/targets?status=attention')
    fireEvent.click(targetsLink)
    expect(onNavigate).toHaveBeenCalledWith('/dashboard/targets?status=attention')
  })

  it('displays persistent alert when configuration is invalid', async () => {
    vi.mocked(api.getOverview).mockResolvedValue({
      daemon: { status: 'running', workers: 1, active_jobs: 0, queued_jobs: 0 },
      configuration: { valid: false, revision: 'rev-invalid' },
      projects: 2,
      unhealthy_targets: 0,
    })

    render(<Overview />)

    expect(await screen.findByText(/New job submissions are blocked until the configuration is valid/i)).toBeInTheDocument()
    expect(screen.getByText('Configuration invalid')).toBeInTheDocument()
  })

  it('preserves previously loaded data and displays warning when background refresh fails', async () => {
    let callCount = 0
    vi.mocked(api.getOverview).mockImplementation(async () => {
      callCount += 1
      if (callCount === 1) {
        return {
          daemon: { status: 'running', workers: 1, active_jobs: 4, queued_jobs: 0 },
          configuration: { valid: true, revision: 'rev-xyz' },
          projects: 3,
          unhealthy_targets: 0,
        }
      }
      throw new Error('Network connection timeout')
    })

    render(<Overview />)

    expect(await screen.findByText('4')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()

    // Click refresh button to trigger error
    const refreshBtn = screen.getByRole('button', { name: /Refresh/i })
    fireEvent.click(refreshBtn)

    expect(await screen.findByText(/Stale data: background refresh failed/i)).toBeInTheDocument()
    // Previously loaded data remains on screen
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
  })
})
