import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import Profiles from './Profiles'

vi.mock('../api', () => ({
  getProfiles: vi.fn(),
  getConfiguration: vi.fn().mockResolvedValue({ valid: true }),
}))

describe('Profiles screen', () => {
  const mockProfiles = {
    default: 'default',
    available: ['default', 'strict-review', 'fast-dev'],
  }

  beforeEach(() => {
    vi.mocked(api.getConfiguration).mockResolvedValue({ valid: true })
    vi.mocked(api.getProfiles).mockResolvedValue(mockProfiles)
  })

  it('renders global profiles catalog', async () => {
    render(<Profiles />)

    expect(await screen.findByText('default')).toBeInTheDocument()
    expect(screen.getByText('Global default')).toBeInTheDocument()
    expect(screen.getByText('strict-review')).toBeInTheDocument()
    expect(screen.getByText('fast-dev')).toBeInTheDocument()
  })

  it('renders invalid configuration health banner and last-known-good revision while cached profiles remain visible', async () => {
    vi.mocked(api.getConfiguration).mockResolvedValue({
      valid: false,
      last_known_good_revision: 'rev-profiles-lkg-003',
    })

    render(<Profiles />)

    expect(await screen.findByText('Configuration invalid — showing last-known-good values')).toBeInTheDocument()
    expect(screen.getByText('rev-profiles-lkg-003')).toBeInTheDocument()
    expect(screen.getByText('default')).toBeInTheDocument()
    expect(screen.getByText('strict-review')).toBeInTheDocument()
    expect(screen.getByText('fast-dev')).toBeInTheDocument()
  })
})
