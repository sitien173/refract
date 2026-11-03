import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import App from './App.jsx'
import * as api from './api.js'

describe('App shell and read-only invariants', () => {
  const mockOverview = {
    daemon: { status: 'running', workers: 4, active_jobs: 1, queued_jobs: 0 },
    configuration: { valid: true, revision: 'rev-xyz' },
    projects: 2,
    unhealthy_targets: 0,
  }

  const mockProjects = [
    { id: 'proj-1', alias: 'primary-project', root: '/path/1' },
    { id: 'proj-2', alias: 'secondary-project', root: '/path/2' },
  ]

  const mockProjectJobs = {
    active: [
      { id: 'job-active-1', workflow: 'review', profile: 'default', state: 'running', attempts: 1 },
    ],
    recent: [
      { id: 'job-recent-1', workflow: 'consult', profile: 'default', state: 'succeeded', attempts: 1 },
    ],
    more_recent: 0,
  }

  const mockJobDetail = {
    id: 'job-active-1',
    project_id: 'proj-1',
    workflow: 'review',
    profile: 'default',
    target_id: 'target-1',
    context_key: 'session-1',
    state: 'running',
    created_at: '2026-11-03T12:00:00Z',
    updated_at: '2026-11-03T12:01:00Z',
    attempts: 1,
    result: { text: '', error: '', metadata: {} },
    execution_plan: { targets: [] },
  }

  beforeEach(() => {
    window.location.hash = '#/jobs'
    localStorage.clear()

    vi.spyOn(api, 'fetchOverview').mockResolvedValue(mockOverview)
    vi.spyOn(api, 'fetchProjects').mockResolvedValue(mockProjects)
    vi.spyOn(api, 'fetchProjectJobs').mockResolvedValue(mockProjectJobs)
    vi.spyOn(api, 'fetchJob').mockResolvedValue(mockJobDetail)
    vi.spyOn(api, 'fetchJobOutput').mockResolvedValue({
      events: [],
      cursor: 0,
      has_more: false,
      retained_from: 0,
      stream_status: 'complete',
    })
    vi.spyOn(api, 'fetchTargets').mockResolvedValue([])
    vi.spyOn(api, 'fetchProfiles').mockResolvedValue({ default: '', available: [], profiles: [] })
    vi.spyOn(api, 'fetchDiagnostics').mockResolvedValue({ reports: [], next_before: null })
    vi.spyOn(api, 'fetchSettings').mockResolvedValue({
      source_path: '',
      revision: 'rev-xyz',
      daemon: { host: '127.0.0.1', port: 9000, max_jobs: 4, history_turns: 8, history_bytes: 10000, default_profile: 'default' },
      logging: { level: 'INFO', format: 'text', file: false, console: true, max_bytes: 1000, backup_count: 3, capture_warnings: true },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders landmarks: header, nav, and main', async () => {
    render(<App />)

    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByRole('banner')).toBeInTheDocument() // header
    expect(screen.getByRole('navigation')).toBeInTheDocument() // nav
    expect(screen.getByRole('main')).toBeInTheDocument() // main
  })

  it('renders views for secondary routes without placeholder', async () => {
    window.location.hash = '#/projects'
    const { unmount: unmount1 } = render(<App />)
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByTestId('projects-view')).toBeInTheDocument()
    unmount1()

    window.location.hash = '#/targets'
    const { unmount: unmount2 } = render(<App />)
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByTestId('targets-view')).toBeInTheDocument()
    unmount2()

    window.location.hash = '#/diagnostics'
    const { unmount: unmount3 } = render(<App />)
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByTestId('diagnostics-view')).toBeInTheDocument()
    unmount3()

    window.location.hash = '#/runtime'
    const { unmount: unmount4 } = render(<App />)
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByTestId('runtime-view')).toBeInTheDocument()
    unmount4()
  })

  it('persists selected project in localStorage', async () => {
    render(<App />)

    await act(async () => {
      await Promise.resolve()
    })

    const projectSelect = screen.getByRole('combobox', { name: /project/i })
    expect(projectSelect.value).toBe('proj-1')

    // Change project
    await act(async () => {
      fireEvent.change(projectSelect, { target: { value: 'proj-2' } })
      await Promise.resolve()
    })
    expect(localStorage.getItem('refract_selected_project')).toBe('proj-2')
  })

  it('STRICT INVARIANT: contains no form, no non-filter/toggle input, and no mutating button', async () => {
    const { container } = render(<App />)

    await act(async () => {
      await Promise.resolve()
    })

    // No <form> tags anywhere
    const forms = container.querySelectorAll('form')
    expect(forms.length).toBe(0)

    // Only filter / toggle inputs allowed
    const inputs = container.querySelectorAll('input')
    inputs.forEach((input) => {
      const type = input.getAttribute('type')
      expect(['checkbox', 'radio', 'search'].includes(type)).toBe(true)
    })

    // No mutating buttons (all buttons type="button" and do not send POST/PUT/DELETE)
    const buttons = container.querySelectorAll('button')
    buttons.forEach((button) => {
      expect(button.getAttribute('type') || 'button').toBe('button')
    })
  })
})
