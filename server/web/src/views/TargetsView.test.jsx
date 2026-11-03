import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { TargetsView } from './TargetsView.jsx'
import * as api from '../api.js'

describe('TargetsView', () => {
  const mockTargets = [
    {
      id: 'target-pro',
      backend: 'google',
      model: 'gemini-1.5-pro',
      isolated: true,
      read_only: false,
      max_concurrency: 4,
      active: 1,
      healthy: true,
      circuit_open_until: '',
      breaker_state: 'closed',
      cooldown_s: 30,
      probing: false,
    },
    {
      id: 'target-flash',
      backend: 'google',
      model: 'gemini-1.5-flash',
      isolated: false,
      read_only: true,
      max_concurrency: 8,
      active: 0,
      healthy: false,
      circuit_open_until: '2026-11-03T12:00:00Z',
      breaker_state: 'open',
      cooldown_s: 60,
      probing: true,
    },
  ]

  const mockProfiles = {
    default: 'default-profile',
    available: ['default-profile'],
    profiles: [
      {
        id: 'default-profile',
        parent: { value: null, source: 'global' },
        effective: {
          deliberate: { targets: ['target-pro', 'target-flash'], timeout_s: 300 },
          quick: { targets: ['target-flash'], timeout_s: 45 },
        },
        sources: {
          deliberate: 'global',
          quick: 'project',
        },
        declared: {},
        inherited: {},
      },
    ],
  }

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders loading state when fetching targets or profiles', async () => {
    vi.spyOn(api, 'fetchTargets').mockImplementation(() => new Promise(() => {}))
    vi.spyOn(api, 'fetchProfiles').mockImplementation(() => new Promise(() => {}))
    render(<TargetsView />)
    expect(screen.getByText(/loading targets and profiles/i)).toBeInTheDocument()
  })

  it('renders empty state when targets and profiles are empty', async () => {
    vi.spyOn(api, 'fetchTargets').mockResolvedValue([])
    vi.spyOn(api, 'fetchProfiles').mockResolvedValue({ default: '', available: [], profiles: [] })
    render(<TargetsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText(/no targets configured/i)).toBeInTheDocument()
  })

  it('renders error state when fetch targets fails', async () => {
    vi.spyOn(api, 'fetchTargets').mockRejectedValue(new Error('Targets API failure'))
    vi.spyOn(api, 'fetchProfiles').mockResolvedValue(mockProfiles)
    render(<TargetsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/targets api failure/i)).toBeInTheDocument()
  })

  it('renders target table with backend, model, isolation, read-only flag, active over max concurrency, breaker state, cooldown, and probing', async () => {
    vi.spyOn(api, 'fetchTargets').mockResolvedValue(mockTargets)
    vi.spyOn(api, 'fetchProfiles').mockResolvedValue(mockProfiles)
    render(<TargetsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText('target-pro')).toBeInTheDocument()
    expect(screen.getByText('gemini-1.5-pro')).toBeInTheDocument()
    expect(screen.getByText('1 / 4')).toBeInTheDocument()
    expect(screen.getByText('30s')).toBeInTheDocument()
    expect(screen.getByText('closed')).toBeInTheDocument()

    expect(screen.getAllByText('target-flash').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('gemini-1.5-flash')).toBeInTheDocument()
    expect(screen.getByText('0 / 8')).toBeInTheDocument()
    expect(screen.getByText('60s')).toBeInTheDocument()
    expect(screen.getByText('open')).toBeInTheDocument()

    // Read-only and isolation indications
    expect(screen.getAllByText(/read-only/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/isolated/i).length).toBeGreaterThanOrEqual(1)
  })

  it('renders profile routing matrix with profiles by workflow, ordered target chain, and source label', async () => {
    vi.spyOn(api, 'fetchTargets').mockResolvedValue(mockTargets)
    vi.spyOn(api, 'fetchProfiles').mockResolvedValue(mockProfiles)
    render(<TargetsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText(/profile routing matrix/i)).toBeInTheDocument()
    expect(screen.getAllByText('default-profile').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('deliberate')).toBeInTheDocument()
    expect(screen.getByText('quick')).toBeInTheDocument()

    // Ordered target chains
    expect(screen.getByText(/target-pro → target-flash/i)).toBeInTheDocument()

    // Source labels
    expect(screen.getAllByText(/global/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText(/project/i).length).toBeGreaterThanOrEqual(1)
  })

  it('STRICT INVARIANT: contains no form, no non-filter input, and no mutating button', async () => {
    vi.spyOn(api, 'fetchTargets').mockResolvedValue(mockTargets)
    vi.spyOn(api, 'fetchProfiles').mockResolvedValue(mockProfiles)
    const { container } = render(<TargetsView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(container.querySelectorAll('form').length).toBe(0)
    container.querySelectorAll('input').forEach((input) => {
      expect(['checkbox', 'radio', 'search'].includes(input.getAttribute('type'))).toBe(true)
    })
    container.querySelectorAll('button').forEach((button) => {
      expect(button.getAttribute('type') || 'button').toBe('button')
    })
  })
})
