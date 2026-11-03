import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ConfigInvalidBanner } from './ConfigInvalidBanner.jsx'

describe('ConfigInvalidBanner component', () => {
  it('does not render when configuration is valid', () => {
    const { container } = render(
      <ConfigInvalidBanner configuration={{ valid: true, revision: 'rev-ok' }} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders latest_error, last_known_good_revision, and directs user to toml file', () => {
    const configuration = {
      valid: false,
      latest_error: 'Invalid syntax at line 42 in config.toml',
      last_known_good_revision: 'rev-good-99',
    }

    render(<ConfigInvalidBanner configuration={configuration} />)

    expect(screen.getByText(/invalid syntax at line 42/i)).toBeInTheDocument()
    expect(screen.getByText(/rev-good-99/i)).toBeInTheDocument()
    expect(screen.getByText(/config\.toml/i)).toBeInTheDocument()
    expect(screen.getByRole('alert').className).not.toMatch(/stacked/)
    expect(screen.getByRole('alert')).toHaveClass('tds-announcement')
    expect(screen.getByRole('alert')).toHaveClass('tds-announcement--error')
  })
})
