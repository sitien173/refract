import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import StatusBadge from './components/StatusBadge'
const appStyles = readFileSync(resolve(process.cwd(), 'src/styles/app.css'), 'utf8')
const flowforgeTokens = readFileSync(resolve(process.cwd(), 'src/styles/colors_and_type.css'), 'utf8')

vi.mock('./api', () => ({
  getSettings: vi.fn().mockResolvedValue({
    source_path: '/tmp/config.toml', revision: 'settings-revision',
    daemon: { host: '127.0.0.1', port: 8765, max_project_readers: 1, max_jobs: 2 },
    effective: { max_project_readers: 1 }, logging: {},
  }),
  getConfiguration: vi.fn().mockResolvedValue({ valid: true }),
  mutateWithCsrf: vi.fn(),
  updateMaxProjectReaders: vi.fn(),
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

describe('runtime settings reader capacity form', () => {
  it('submits a strict numeric reader count with the current revision and reports restart-required save', async () => {
    window.history.replaceState({}, '', '/dashboard/settings')
    const { updateMaxProjectReaders } = await import('./api')
    vi.mocked(updateMaxProjectReaders).mockResolvedValue({
      source_path: '/tmp/config.toml', revision: 'next-revision',
      daemon: { max_project_readers: 4 }, effective: { max_project_readers: 1 },
      logging: {},
    })
    render(<App />)

    const input = await screen.findByLabelText(/Maximum project readers/i)
    await waitFor(() => expect(input).toHaveValue(1))
    expect(input).toHaveAttribute('type', 'number')
    expect(input).toHaveAttribute('min', '1')
    expect(input).toHaveAttribute('step', '1')
    expect(input).toBeRequired()
    fireEvent.change(input, { target: { value: '4.5' } })
    fireEvent.submit(input.closest('form'))
    expect(updateMaxProjectReaders).not.toHaveBeenCalled()
    expect(screen.getByText(/positive whole number/i)).toBeInTheDocument()
    fireEvent.change(input, { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: /Save reader capacity/i }))

    await waitFor(() => expect(updateMaxProjectReaders).toHaveBeenCalledWith(4, 'settings-revision'))
    expect(await screen.findByText(/Saved; restart required/i)).toBeInTheDocument()
  })

  it('keeps dirty reader drafts through refresh and requires explicit reload after conflict', async () => {
    window.history.replaceState({}, '', '/dashboard/settings')
    const { getSettings, updateMaxProjectReaders } = await import('./api')
    const setting = (value, revision) => ({
      source_path: '/tmp/config.toml', revision,
      daemon: { max_project_readers: value, max_jobs: 2 },
      effective: { max_project_readers: 1 }, logging: {},
    })
    vi.mocked(getSettings).mockClear()
    vi.mocked(updateMaxProjectReaders).mockClear()
    vi.mocked(getSettings)
      .mockResolvedValueOnce(setting(1, 'initial-rev'))
      .mockResolvedValueOnce(setting(2, 'background-rev'))
      .mockResolvedValueOnce(setting(3, 'reload-rev'))
      .mockResolvedValueOnce(setting(3, 'reload-rev'))
    vi.mocked(updateMaxProjectReaders)
      .mockRejectedValueOnce(Object.assign(
        new Error('Configuration conflict'),
        { status: 409, payload: { code: 'configuration_conflict' } },
      ))
      .mockResolvedValueOnce(setting(3, 'saved-rev'))
    render(<App />)

    const input = await screen.findByLabelText(/Maximum project readers/i)
    await waitFor(() => expect(input).toHaveValue(1))
    fireEvent.change(input, { target: { value: '5' } })
    fireEvent.click(screen.getByRole('button', { name: /^Refresh$/i }))
    await waitFor(() => expect(getSettings).toHaveBeenCalledTimes(2))
    expect(await screen.findByText(/Configured: 2 \(pending\)/)).toBeInTheDocument()
    expect(input).toHaveValue(5)

    fireEvent.click(screen.getByRole('button', { name: /Save reader capacity/i }))
    await waitFor(() => expect(updateMaxProjectReaders).toHaveBeenCalledWith(5, 'initial-rev'))
    expect(await screen.findByText(/Reload current settings before retrying/i)).toBeInTheDocument()
    expect(input).toHaveValue(5)
    expect(screen.getByRole('button', { name: /Save reader capacity/i })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /Reload current settings/i }))
    await waitFor(() => expect(input).toHaveValue(3))
    expect(screen.queryByText(/Reload current settings before retrying/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save reader capacity/i })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: /Save reader capacity/i }))
    await waitFor(() => expect(updateMaxProjectReaders).toHaveBeenLastCalledWith(3, 'reload-rev'))
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
