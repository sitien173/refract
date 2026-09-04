import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import Targets from './Targets'

vi.mock('../api', () => ({
  getTargets: vi.fn(),
}))

describe('Targets screen', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/dashboard/targets')
  })
  const mockTargets = [
    {
      id: 'target-healthy',
      backend: 'claude',
      model: 'claude-3-7-sonnet',
      isolated: true,
      read_only: false,
      max_concurrency: 4,
      active: 1,
      healthy: true,
      circuit_open_until: '',
    },
    {
      id: 'target-circuit',
      backend: 'gemini',
      model: 'gemini-2.5-pro',
      isolated: false,
      read_only: true,
      max_concurrency: 2,
      active: 0,
      healthy: true,
      circuit_open_until: '2026-09-04T13:00:00Z',
    },
    {
      id: 'target-down',
      backend: 'local',
      model: 'llama-3',
      isolated: true,
      read_only: false,
      max_concurrency: 1,
      active: 0,
      healthy: false,
      circuit_open_until: '',
    },
  ]

  it('renders targets with distinct health status markers and counts', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)

    render(<Targets />)

    expect(await screen.findByText('target-healthy')).toBeInTheDocument()
    expect(screen.getByText('target-circuit')).toBeInTheDocument()
    expect(screen.getByText('target-down')).toBeInTheDocument()

    expect(screen.getAllByText('Healthy').length).toBeGreaterThan(0)
    expect(screen.getByText('Circuit open')).toBeInTheDocument()
    expect(screen.getByText('Unhealthy')).toBeInTheDocument()
  })

  it('filters targets by status button and search query', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)

    render(<Targets />)

    expect(await screen.findByText('target-healthy')).toBeInTheDocument()

    // Filter by needing attention (circuit-open and down)
    const attentionBtn = screen.getByRole('button', { name: /Needing attention/i })
    fireEvent.click(attentionBtn)

    expect(screen.queryByText('target-healthy')).not.toBeInTheDocument()
    expect(screen.getByText('target-circuit')).toBeInTheDocument()
    expect(screen.getByText('target-down')).toBeInTheDocument()
  })

  it('opens docked inspector on row click with target details', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)

    render(<Targets />)

    expect(await screen.findByText('target-healthy')).toBeInTheDocument()

    const healthyRow = screen.getByText('target-healthy').closest('tr')
    fireEvent.click(healthyRow)

    expect(screen.getByRole('complementary', { name: /Inspector: Target: target-healthy/i })).toBeInTheDocument()
    expect(screen.getByText('4 concurrent jobs')).toBeInTheDocument()
  })
})
