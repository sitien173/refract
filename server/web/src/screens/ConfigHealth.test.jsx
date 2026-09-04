import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import ConfigHealth from './ConfigHealth'

vi.mock('../api', () => ({
  getConfiguration: vi.fn(),
  getStatus: vi.fn(),
}))

describe('ConfigHealth screen', () => {
  it('renders healthy configuration state with revision evidence', async () => {
    vi.mocked(api.getConfiguration).mockResolvedValue({
      valid: true,
      revision: 'sha256-abcdef1234567890',
      source_path: '/etc/openmcp/config.toml',
      attempted_at: '2026-09-04T12:00:00Z',
      successful_at: '2026-09-04T12:00:00Z',
      modification_time: '2026-09-04T11:55:00Z',
      latest_error: '',
      last_known_good_revision: 'sha256-abcdef1234567890',
    })
    vi.mocked(api.getStatus).mockResolvedValue({
      status: 'running',
      workers: 2,
      active_jobs: 1,
      queued_jobs: 0,
    })

    render(<ConfigHealth />)

    expect(await screen.findByText('Configuration is healthy')).toBeInTheDocument()
    expect(screen.getAllByText('sha256-abcdef1234567890').length).toBeGreaterThan(0)
    expect(screen.getByText('/etc/openmcp/config.toml')).toBeInTheDocument()
    expect(screen.getByText('Daemon running')).toBeInTheDocument()
    expect(screen.getByText('Submissions open')).toBeInTheDocument()
  })

  it('renders invalid configuration state with last-known-good revision and recovery guidance', async () => {
    vi.mocked(api.getConfiguration).mockResolvedValue({
      valid: false,
      revision: 'sha256-broken',
      source_path: '/etc/openmcp/config.toml',
      attempted_at: '2026-09-04T12:15:00Z',
      successful_at: '2026-09-04T12:00:00Z',
      modification_time: '2026-09-04T12:14:00Z',
      latest_error: 'Parse error at line 42: unexpected key "invalid_field"',
      last_known_good_revision: 'sha256-good-prev-rev',
    })
    vi.mocked(api.getStatus).mockResolvedValue({
      status: 'running',
      workers: 2,
      active_jobs: 0,
      queued_jobs: 0,
    })

    render(<ConfigHealth />)

    expect(await screen.findByText('Configuration file is invalid')).toBeInTheDocument()
    expect(screen.getByText(/unexpected key "invalid_field"/i)).toBeInTheDocument()
    expect(screen.getAllByText('sha256-good-prev-rev').length).toBeGreaterThan(0)
    expect(screen.getByText('Submissions blocked')).toBeInTheDocument()
    expect(screen.getByText('Recovery Guidance')).toBeInTheDocument()
  })
})
