import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { RuntimeView } from './RuntimeView.jsx'
import * as api from '../api.js'

describe('RuntimeView', () => {
  const mockValidOverview = {
    configuration: {
      valid: true,
      revision: 'rev-456',
      source_path: '/home/user/.refract/config.toml',
      latest_error: '',
      last_known_good_revision: '',
    },
  }

  const mockInvalidOverview = {
    configuration: {
      valid: false,
      revision: 'rev-error',
      source_path: '/home/user/.refract/config.toml',
      latest_error: 'Invalid TOML syntax: unexpected token at line 14',
      last_known_good_revision: 'rev-455',
    },
  }

  const mockSettings = {
    source_path: '/home/user/.refract/config.toml',
    revision: 'rev-456',
    daemon: {
      host: '127.0.0.1',
      port: 9000,
      max_jobs: 4,
      history_turns: 8,
      history_bytes: 1048576,
      default_profile: 'default',
    },
    logging: {
      level: 'INFO',
      format: 'text',
      file: '/var/log/refract.log',
      console: true,
      max_bytes: 5242880,
      backup_count: 3,
      capture_warnings: true,
    },
  }

  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renders loading state when fetching settings', async () => {
    vi.spyOn(api, 'fetchSettings').mockImplementation(() => new Promise(() => {}))
    vi.spyOn(api, 'fetchOverview').mockImplementation(() => new Promise(() => {}))
    render(<RuntimeView />)
    expect(screen.getByText(/loading runtime settings/i)).toBeInTheDocument()
  })

  it('renders empty state when settings are null', async () => {
    vi.spyOn(api, 'fetchSettings').mockResolvedValue(null)
    vi.spyOn(api, 'fetchOverview').mockResolvedValue(mockValidOverview)
    render(<RuntimeView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText(/no runtime settings available/i)).toBeInTheDocument()
  })

  it('renders error state when fetchSettings fails', async () => {
    vi.spyOn(api, 'fetchSettings').mockRejectedValue(new Error('Failed to read settings'))
    vi.spyOn(api, 'fetchOverview').mockResolvedValue(mockValidOverview)
    render(<RuntimeView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/failed to read settings/i)).toBeInTheDocument()
  })

  it('renders valid configuration health and daemon/logging settings', async () => {
    vi.spyOn(api, 'fetchSettings').mockResolvedValue(mockSettings)
    vi.spyOn(api, 'fetchOverview').mockResolvedValue(mockValidOverview)
    render(<RuntimeView />)

    await act(async () => {
      await Promise.resolve()
    })

    // Config health
    expect(screen.getByRole('heading', { name: /configuration health/i })).toBeInTheDocument()
    expect(screen.getByText('Valid')).toBeInTheDocument()
    expect(screen.getAllByText('rev-456').length).toBeGreaterThanOrEqual(1)

    // Daemon settings
    expect(screen.getByText(/daemon settings/i)).toBeInTheDocument()
    expect(screen.getByText('127.0.0.1')).toBeInTheDocument()
    expect(screen.getByText('9000')).toBeInTheDocument()
    expect(screen.getByText('1048576')).toBeInTheDocument()

    // Logging settings
    expect(screen.getByText(/logging settings/i)).toBeInTheDocument()
    expect(screen.getByText('INFO')).toBeInTheDocument()
    expect(screen.getByText('/var/log/refract.log')).toBeInTheDocument()
    expect(screen.getByText('5242880')).toBeInTheDocument()
  })

  it('renders invalid configuration health with latest_error and last_known_good_revision', async () => {
    vi.spyOn(api, 'fetchSettings').mockResolvedValue(mockSettings)
    vi.spyOn(api, 'fetchOverview').mockResolvedValue(mockInvalidOverview)
    render(<RuntimeView />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByText('Invalid')).toBeInTheDocument()
    expect(screen.getByText(/Invalid TOML syntax: unexpected token at line 14/i)).toBeInTheDocument()
    expect(screen.getByText('rev-455')).toBeInTheDocument()
  })

  it('STRICT INVARIANT: contains no form, no non-filter input, and no mutating button', async () => {
    vi.spyOn(api, 'fetchSettings').mockResolvedValue(mockSettings)
    vi.spyOn(api, 'fetchOverview').mockResolvedValue(mockValidOverview)
    const { container } = render(<RuntimeView />)

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
