import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { getDiagnostics } from './api'
import StatusBadge from './components/StatusBadge'
const appStyles = readFileSync(resolve(process.cwd(), 'src/styles/app.css'), 'utf8')
const flowforgeTokens = readFileSync(resolve(process.cwd(), 'src/styles/colors_and_type.css'), 'utf8')

vi.mock('./api', () => ({
  getSettings: vi.fn().mockResolvedValue({
    source_path: '/tmp/config.toml', revision: 'settings-revision',
    daemon: { host: '127.0.0.1', port: 8765, max_jobs: 2 },
    effective: {}, logging: {},
  }),
  getConfiguration: vi.fn().mockResolvedValue({ valid: true }),
  mutateWithCsrf: vi.fn(),
  getOverview: vi.fn().mockResolvedValue({
    daemon: { status: 'running', workers: 1, active_jobs: 0, queued_jobs: 0 },
    configuration: { valid: true, revision: '' },
    projects: 0,
    unhealthy_targets: 0,
  }),
  getDiagnostics: vi.fn().mockResolvedValue({ reports: [], next_before: null }),
  getProjects: vi.fn().mockResolvedValue([]),
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

  it('navigates to Diagnostics view and updates route', async () => {
    window.history.pushState({}, '', '/dashboard/')
    render(<App />)

    const diagButton = await screen.findByRole('button', { name: /^Diagnostics$/i })
    expect(diagButton).toBeInTheDocument()
    fireEvent.click(diagButton)

    expect(await screen.findByRole('heading', { level: 2, name: 'Diagnostics' })).toBeInTheDocument()
    expect(diagButton).toHaveAttribute('aria-current', 'page')
  })

  it('resets filtered diagnostics, handles delayed stale response, and resets pagination on sidebar navigation', async () => {
    let resolveFiltered
    const delayedFilteredPromise = new Promise((resolve) => {
      resolveFiltered = resolve
    })

    const cleanReportsPage1 = [
      {
        id: 'clean-901',
        job_id: 'job-clean',
        project_id: 'proj-clean',
        category: 'system',
        severity: 'info',
        source: 'worker',
        code: 'CLEAN_OBSERVATION',
        message: 'Clean diagnostics report',
        created_at: 1710000000,
      },
    ]

    const filteredReports = [
      {
        id: 'filtered-101',
        job_id: 'job-filtered',
        project_id: 'proj-filtered',
        category: 'protocol',
        severity: 'error',
        source: 'worker',
        code: 'STALE_FILTERED',
        message: 'Stale filtered report',
        created_at: 1710000005,
      },
    ]

    getDiagnostics.mockImplementation(({ jobId }) => {
      if (jobId === 'job-filtered') {
        return delayedFilteredPromise
      }
      return Promise.resolve({ reports: cleanReportsPage1, next_before: null })
    })

    window.history.pushState({}, '', '/dashboard/diagnostics?job_id=job-filtered')
    render(<App />)

    expect(await screen.findByRole('heading', { level: 2, name: 'Diagnostics' })).toBeInTheDocument()
    const jobInput = screen.getByLabelText('Filter by job')
    expect(jobInput.value).toBe('job-filtered')

    const diagButton = screen.getByRole('button', { name: /^Diagnostics$/i })
    fireEvent.click(diagButton)

    expect(window.location.pathname).toBe('/dashboard/diagnostics')
    expect(window.location.search).toBe('')
    expect(jobInput.value).toBe('')

    resolveFiltered({ reports: filteredReports, next_before: null })

    expect(await screen.findByText('clean-901')).toBeInTheDocument()
    expect(screen.queryByText('filtered-101')).not.toBeInTheDocument()
    expect(screen.queryByText('Stale filtered report')).not.toBeInTheDocument()
    expect(screen.getByText('Page 1')).toBeInTheDocument()
  })

  it('clears query and resets filters on repeat sidebar navigation after local filter edits', async () => {
    const cleanReports = [
      {
        id: 'clean-902',
        job_id: 'job-clean-2',
        project_id: 'proj-clean-2',
        category: 'system',
        severity: 'info',
        source: 'worker',
        code: 'CLEAN_2',
        message: 'Clean report 2',
        created_at: 1710000010,
      },
    ]

    const editedReports = [
      {
        id: 'edited-202',
        job_id: 'job-edited',
        project_id: 'proj-edited',
        category: 'protocol',
        severity: 'warn',
        source: 'worker',
        code: 'EDITED_JOB',
        message: 'Edited job report',
        created_at: 1710000020,
      },
    ]

    getDiagnostics.mockImplementation(({ jobId }) => {
      if (jobId === 'job-edited') {
        return Promise.resolve({ reports: editedReports, next_before: null })
      }
      return Promise.resolve({ reports: cleanReports, next_before: null })
    })

    window.history.pushState({}, '', '/dashboard/diagnostics')
    render(<App />)

    expect(await screen.findByText('clean-902')).toBeInTheDocument()

    const jobInput = screen.getByLabelText('Filter by job')
    fireEvent.change(jobInput, { target: { value: 'job-edited' } })
    expect(jobInput.value).toBe('job-edited')
    expect(await screen.findByText('edited-202')).toBeInTheDocument()
    expect(window.location.search).toContain('job_id=job-edited')

    const diagButton = screen.getByRole('button', { name: /^Diagnostics$/i })
    fireEvent.click(diagButton)

    expect(window.location.pathname).toBe('/dashboard/diagnostics')
    expect(window.location.search).toBe('')
    expect(jobInput.value).toBe('')
    expect(await screen.findByText('clean-902')).toBeInTheDocument()
    expect(screen.queryByText('edited-202')).not.toBeInTheDocument()
  })
})

describe('dashboard API boundary', () => {
  it('bootstraps CSRF and retries exactly once after a forbidden mutation', async () => {
    vi.resetModules()
    const { updateConfigurationTarget } = await vi.importActual('./api')
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
    expect(fetchMock.mock.calls[1][1].headers['X-Refract-CSRF']).toBe('first-token')
    expect(fetchMock.mock.calls[3][1].headers['X-Refract-CSRF']).toBe('second-token')
    expect(fetchMock.mock.calls[4]).toBeUndefined()
    expect(fetchMock.mock.calls[1][1].credentials).toBeUndefined()
  })
})
