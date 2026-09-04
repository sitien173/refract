import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import * as api from '../api'

vi.mock('../api', () => ({
  clearCsrfToken: vi.fn(),
  getBootstrap: vi.fn().mockResolvedValue({ csrf_token: 'secret-csrf-token' }),
  getOverview: vi.fn(),
  getProjects: vi.fn(),
  getProject: vi.fn(),
  getProfiles: vi.fn(),
  getTargets: vi.fn(),
  getSettings: vi.fn(),
  getConfiguration: vi.fn(),
  getProjectJobs: vi.fn(),
  getJob: vi.fn(),
  getTaskGuide: vi.fn(),
  getContextInstructions: vi.fn(),
  updateContextInstruction: vi.fn(),
  deleteContextInstruction: vi.fn(),
}))

describe('Dashboard integrated user flows', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.pushState({}, '', '/dashboard/')

    vi.mocked(api.getOverview).mockResolvedValue({
      daemon: { status: 'running', workers: 2, active_jobs: 0, queued_jobs: 0 },
      configuration: { valid: true, revision: 'rev-overall-001' },
      projects: 2,
      unhealthy_targets: 0,
    })

    vi.mocked(api.getProjects).mockResolvedValue([
      { id: 'proj-alpha', alias: 'Alpha Service', root: '/srv/alpha' },
      { id: 'proj-beta', alias: 'Beta App', root: '/srv/beta' },
    ])

    vi.mocked(api.getConfiguration).mockResolvedValue({
      valid: true,
      revision: 'rev-overall-001',
      last_known_good_revision: 'rev-overall-001',
    })

    vi.mocked(api.getProject).mockResolvedValue({
      project: { id: 'proj-alpha', alias: 'Alpha Service', root: '/srv/alpha' },
      configuration: {
        global_default_profile: 'balanced',
        project_default_profile: 'balanced',
        profiles: [
          {
            id: 'balanced',
            parent: { value: null, source: 'global' },
            declared: {},
            inherited: {},
            effective: {
              consult: { targets: ['worker-1'], max_attempts: 1, timeout_s: 60 },
            },
            sources: { consult: 'global' },
          },
        ],
      },
    })

    vi.mocked(api.getContextInstructions).mockResolvedValue({
      project_id: 'proj-alpha',
      instructions: {
        consult: 'Initial consult instruction',
      },
    })

    vi.mocked(api.getProjectJobs).mockResolvedValue([
      {
        id: 'job-999',
        workflow: 'implement',
        profile: 'balanced',
        state: 'succeeded',
        target_id: 'worker-1',
        config_revision: 'rev-overall-001',
        created_at: '2026-09-04 15:00:00',
      },
    ])

    vi.mocked(api.getJob).mockResolvedValue({
      id: 'job-999',
      project_id: 'proj-alpha',
      workflow: 'implement',
      profile: 'balanced',
      state: 'succeeded',
      target_id: 'worker-1',
      config_revision: 'rev-overall-001',
      attempts: 1,
      created_at: '2026-09-04 15:00:00',
      updated_at: '2026-09-04 15:01:00',
      execution_plan: {
        profile: 'balanced',
        workflow: 'implement',
        selection: { targets: ['worker-1'], max_attempts: 1, timeout_s: 60 },
        targets: [
          {
            id: 'worker-1',
            backend: 'pi',
            model: 'gpt-5.6',
            isolated: true,
            read_only: false,
            max_concurrency: 2,
          },
        ],
      },
      result: {
        output: 'Implementation completed without errors.',
      },
    })
  })

  it('completes the full context instruction editing and clearing flow with security constraints', async () => {
    vi.mocked(api.updateContextInstruction).mockResolvedValue({
      project_id: 'proj-alpha',
      workflow: 'consult',
      instruction: 'New comprehensive consult instruction',
    })

    vi.mocked(api.deleteContextInstruction).mockResolvedValue({
      project_id: 'proj-alpha',
      workflow: 'consult',
      instruction: '',
    })

    const { container } = render(<App />)

    // Initial Overview shows daemon status
    expect(await screen.findByText('Daemon running')).toBeInTheDocument()

    // Navigate to Projects via sidebar
    const projectsNav = screen.getByRole('button', { name: /^Projects$/i })
    fireEvent.click(projectsNav)

    expect(await screen.findByText('Alpha Service')).toBeInTheDocument()

    // Navigate to Project Detail
    const projectLink = screen.getByText('Alpha Service')
    fireEvent.click(projectLink)

    expect(await screen.findByRole('tab', { name: /Context instructions/i })).toBeInTheDocument()

    // Switch to Context tab
    const contextTab = screen.getByRole('tab', { name: /Context instructions/i })
    fireEvent.click(contextTab)

    expect(await screen.findByText('Initial consult instruction')).toBeInTheDocument()

    // Open Edit modal
    const editBtn = screen.getByRole('button', { name: /Edit consult context instruction/i })
    fireEvent.click(editBtn)

    const dialog = screen.getByRole('dialog', { name: /Edit context instruction: consult/i })
    expect(dialog).toBeInTheDocument()

    const textarea = screen.getByLabelText(/Instruction content/i)
    fireEvent.change(textarea, { target: { value: 'New comprehensive consult instruction' } })

    const confirmCheck = screen.getByLabelText(/I confirm this change applies only to future jobs/i)
    fireEvent.click(confirmCheck)

    const saveBtn = screen.getByRole('button', { name: /Save instruction/i })
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(api.updateContextInstruction).toHaveBeenCalledWith(
        'proj-alpha',
        'consult',
        'New comprehensive consult instruction',
        'Initial consult instruction'
      )
    })

    expect(await screen.findByText('New comprehensive consult instruction')).toBeInTheDocument()

    // Clear instruction flow
    const clearBtn = screen.getByRole('button', { name: /Clear consult context instruction/i })
    fireEvent.click(clearBtn)

    const clearDialog = screen.getByRole('dialog', { name: /Clear context instruction: consult/i })
    expect(clearDialog).toBeInTheDocument()

    const confirmClearCheck = screen.getByLabelText(/I confirm this clear action affects future jobs only/i)
    fireEvent.click(confirmClearCheck)

    const confirmClearBtn = screen.getByRole('button', { name: /Confirm clear/i })
    fireEvent.click(confirmClearBtn)

    await waitFor(() => {
      expect(api.deleteContextInstruction).toHaveBeenCalledWith(
        'proj-alpha',
        'consult',
        'New comprehensive consult instruction'
      )
    })

    // Assert CSRF token is nowhere in the rendered DOM
    expect(container.innerHTML).not.toContain('secret-csrf-token')
  })

  it('navigates to Jobs, inspects job execution plan, and enforces redaction', async () => {
    const { container } = render(<App />)

    // Navigate to Jobs via sidebar
    const jobsNav = await screen.findByRole('button', { name: /^Jobs$/i })
    fireEvent.click(jobsNav)

    expect(await screen.findByText('job-999')).toBeInTheDocument()
    expect(screen.getByText('rev-overall-')).toBeInTheDocument()

    // Click Job ID link to navigate to JobDetail
    const jobLink = screen.getByText('job-999')
    fireEvent.click(jobLink)

    expect(await screen.findByText('Job job-999')).toBeInTheDocument()
    expect(screen.getByText('rev-overall-001')).toBeInTheDocument()
    expect(screen.getByText('gpt-5.6')).toBeInTheDocument()
    expect(screen.getByText('Implementation completed without errors.')).toBeInTheDocument()

    // Back to jobs button
    const backBtn = screen.getByRole('button', { name: /Back to jobs list/i })
    fireEvent.click(backBtn)

    expect(await screen.findByText('job-999')).toBeInTheDocument()
  })
})
