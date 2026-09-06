import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import StatusBadge from './components/StatusBadge'
const appStyles = readFileSync(resolve(process.cwd(), 'src/styles/app.css'), 'utf8')
const flowforgeTokens = readFileSync(resolve(process.cwd(), 'src/styles/colors_and_type.css'), 'utf8')

vi.mock('./api', () => ({
  getOverview: vi.fn().mockResolvedValue({
    daemon: { status: 'running', workers: 1, active_jobs: 0, queued_jobs: 0 },
    configuration: { valid: true, revision: '' },
    projects: 0,
    unhealthy_targets: 0,
  }),
}))

describe('dashboard shell', () => {
  it('renders the FlowForge product shell and overview status', async () => {
    render(<App />)

    expect(screen.getByRole('complementary')).toBeInTheDocument()
    expect(screen.getByRole('banner')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(await screen.findByText('Daemon running')).toBeInTheDocument()
  })

  it('uses token dimensions for the product shell', () => {
    expect(flowforgeTokens).toContain('--layout-sidebar-width: 200px')
    expect(flowforgeTokens).toContain('--space-4xl: 64px')
    expect(appStyles).toContain('grid-template-columns: var(--layout-sidebar-width) 1fr')
    expect(appStyles).toContain('grid-template-rows: var(--space-4xl) 1fr')
    expect(appStyles).not.toMatch(/#[0-9a-f]{3,8}/i)
  })

  it('pairs status text with a non-color status marker', () => {
    render(<StatusBadge status="healthy" label="Healthy" />)

    expect(screen.getByText('Healthy')).toBeInTheDocument()
    expect(screen.getByText('Healthy').closest('.status-badge').querySelector('.status-icon')).toBeInTheDocument()
  })

  it('does not use gradients in application styles', () => {
    expect(appStyles.toLowerCase()).not.toContain('gradient')
  })
})

describe('dashboard API boundary', () => {
  it('bootstraps CSRF and retries exactly once after a forbidden mutation', async () => {
    const { clearCsrfToken, updateConfigurationTarget } = await vi.importActual('./api')
    clearCsrfToken()
    const response = (status, payload) => ({
      ok: status >= 200 && status < 300,
      status,
      json: async () => payload,
    })
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(200, { csrf_token: 'first-token' }))
      .mockResolvedValueOnce(response(403, { error: 'Forbidden', code: 'forbidden' }))
      .mockResolvedValueOnce(response(200, { csrf_token: 'second-token' }))
      .mockResolvedValueOnce(response(200, { id: 'updated' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateConfigurationTarget('target', { backend: 'codex' }, 'rev')).resolves.toEqual({ id: 'updated' })

    expect(fetchMock).toHaveBeenCalledTimes(4)
    expect(fetchMock.mock.calls[1][1].headers['X-OpenMCP-CSRF']).toBe('first-token')
    expect(fetchMock.mock.calls[3][1].headers['X-OpenMCP-CSRF']).toBe('second-token')
    expect(fetchMock.mock.calls[4]).toBeUndefined()
    expect(fetchMock.mock.calls[1][1].credentials).toBeUndefined()
  })
})
