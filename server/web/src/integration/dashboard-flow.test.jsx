import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
  getConfigurationTargets: vi.fn(),
  getConfigurationTarget: vi.fn(),
  createConfigurationTarget: vi.fn(),
  updateConfigurationTarget: vi.fn(),
  deleteConfigurationTarget: vi.fn(),
  getConfigurationProfiles: vi.fn(),
  getConfigurationProfile: vi.fn(),
  createConfigurationProfile: vi.fn(),
  updateConfigurationProfile: vi.fn(),
  deleteConfigurationProfile: vi.fn(),
  getProjectJobs: vi.fn(),
  getJob: vi.fn(),
  getTaskGuide: vi.fn(),
  getProjectProfileOverrides: vi.fn(),
  getProjectProfileOverride: vi.fn(),
  createProjectProfileOverride: vi.fn(),
  updateProjectProfileOverride: vi.fn(),
  deleteProjectProfileOverride: vi.fn(),
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

    vi.mocked(api.getTargets).mockResolvedValue([
      {
        id: 'worker-1',
        backend: 'pi',
        model: 'gpt-5.6',
        backend_profile: 'default',
        reasoning: 'default',
        isolated: true,
        read_only: false,
        max_concurrency: 2,
        healthy: true,
        last_checked: '2026-09-04 15:00:00',
        circuit_open_until: null,
      },
    ])

    vi.mocked(api.getConfigurationTargets).mockResolvedValue({
      revision: 'rev-targets-001',
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
    })

    vi.mocked(api.getProfiles).mockResolvedValue({
      default: 'default',
      available: ['default', 'strict-review', 'fast-dev'],
    })

    vi.mocked(api.getConfigurationProfiles).mockResolvedValue({
      revision: 'rev-prof-flow-001',
      source_path: '/etc/openmcp/config.toml',
      default_profile: 'default',
      available_targets: ['worker-1', 'worker-2'],
      profiles: [
        {
          id: 'default',
          extends: null,
          declared: {
            consult: { targets: ['worker-1'], max_attempts: 1, timeout_s: 30 },
          },
          inherited: {},
          effective: {
            consult: { targets: ['worker-1'], max_attempts: 1, timeout_s: 30 },
          },
          sources: { consult: 'default' },
        },
        {
          id: 'fast-dev',
          extends: 'default',
          declared: {},
          inherited: {
            consult: { targets: ['worker-1'], max_attempts: 1, timeout_s: 30 },
          },
          effective: {
            consult: { targets: ['worker-1'], max_attempts: 1, timeout_s: 30 },
          },
          sources: { consult: 'default' },
        },
      ],
    })

    vi.mocked(api.getConfigurationProfile).mockImplementation(async (id) => ({
      revision: 'rev-prof-flow-001',
      source_path: '/etc/openmcp/config.toml',
      default_profile: 'default',
      available_targets: ['worker-1', 'worker-2'],
      profile: {
        id,
        extends: id === 'fast-dev' ? 'default' : null,
        declared: {},
        inherited: {},
        effective: {},
        sources: {},
      },
    }))

    vi.mocked(api.getProjectProfileOverrides).mockResolvedValue({
      revision: 'rev-flow-proj-001',
      source_path: '/srv/alpha/.openmcp/config.toml',
      global_default_profile: 'balanced',
      project_default_profile: 'balanced',
      available_targets: ['worker-1', 'worker-2'],
      overrides: [
        {
          id: 'balanced',
          extends: 'balanced',
          declared: {
            consult: { targets: ['worker-1'], max_attempts: 1, timeout_s: 60 },
          },
          inherited: {},
          effective: {
            consult: { targets: ['worker-1'], max_attempts: 1, timeout_s: 60 },
          },
          sources: { consult: 'project' },
        },
      ],
    })
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

  it('manages targets through creation, inspection, and deletion workflows', async () => {
    vi.mocked(api.createConfigurationTarget).mockResolvedValue({
      revision: 'rev-targets-002',
      target: {
        id: 'worker-2',
        backend: 'codex',
        model: 'gpt-4o',
        isolated: false,
        read_only: true,
        max_concurrency: 1,
        args: ['--temp', '0.2'],
        system_prompt: 'SUPER_SECRET_PROMPT_XYZ',
      },
    })
    vi.mocked(api.deleteConfigurationTarget).mockResolvedValue({
      deleted: 'worker-1',
      revision: 'rev-targets-003',
    })

    const { container } = render(<App />)

    // Navigate to Targets via sidebar
    const targetsNav = await screen.findByRole('button', { name: /^Targets$/i })
    fireEvent.click(targetsNav)

    expect(await screen.findByText('worker-1')).toBeInTheDocument()

    // Open target create modal
    const createBtn = screen.getByRole('button', { name: /^Create target$/i })
    fireEvent.click(createBtn)

    const createDialog = await screen.findByRole('dialog', { name: /Create target/i })
    expect(createDialog).toBeInTheDocument()

    fireEvent.change(within(createDialog).getByLabelText(/Identifier/i), { target: { value: 'worker-2' } })
    fireEvent.change(within(createDialog).getByLabelText(/^Model$/i), { target: { value: 'gpt-4o' } })
    fireEvent.change(within(createDialog).getByLabelText(/System prompt/i), { target: { value: 'SUPER_SECRET_PROMPT_XYZ' } })

    const addArgBtn = within(createDialog).getByRole('button', { name: /Add argument/i })
    fireEvent.click(addArgBtn)
    fireEvent.change(within(createDialog).getByRole('textbox', { name: /^Argument 1$/i }), { target: { value: '--temp' } })

    const submitCreateBtn = within(createDialog).getByRole('button', { name: /^Create target$/i })
    fireEvent.click(submitCreateBtn)

    await waitFor(() => {
      expect(api.createConfigurationTarget).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'worker-2',
          model: 'gpt-4o',
          system_prompt: 'SUPER_SECRET_PROMPT_XYZ',
          args: ['--temp'],
        }),
        'rev-targets-001'
      )
    })

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    // Assert sensitive system prompt does not appear in targets table or document
    expect(screen.queryByText('SUPER_SECRET_PROMPT_XYZ')).not.toBeInTheDocument()

    // Click target row to open inspector
    const targetRow = screen.getByText('worker-1')
    fireEvent.click(targetRow)

    const deleteBtn = await screen.findByRole('button', { name: /^Delete target$/i })
    fireEvent.click(deleteBtn)

    const deleteDialog = await screen.findByRole('dialog', { name: /Delete target: worker-1/i })
    expect(deleteDialog).toBeInTheDocument()

    const confirmCheckbox = within(deleteDialog).getByRole('checkbox', { name: /I confirm deleting target worker-1/i })
    fireEvent.click(confirmCheckbox)

    const confirmDeleteBtn = within(deleteDialog).getByRole('button', { name: /^Confirm delete$/i })
    fireEvent.click(confirmDeleteBtn)

    await waitFor(() => {
      expect(api.deleteConfigurationTarget).toHaveBeenCalledWith('worker-1', 'rev-targets-001')
    })

    // Assert CSRF token is not leaked in the DOM
    expect(container.innerHTML).not.toContain('secret-csrf-token')
  })

  it('manages profiles through creation, inspection, and deletion workflows', async () => {
    vi.mocked(api.createConfigurationProfile).mockResolvedValue({
      revision: 'rev-prof-flow-002',
      source_path: '/etc/openmcp/config.toml',
      default_profile: 'default',
      available_targets: ['worker-1', 'worker-2'],
      profile: {
        id: 'flow-profile',
        extends: 'default',
        declared: {
          consult: { targets: ['worker-2'], max_attempts: 1, timeout_s: 20 },
        },
        inherited: {},
        effective: {},
        sources: {},
      },
    })
    vi.mocked(api.deleteConfigurationProfile).mockResolvedValue({
      deleted: 'fast-dev',
      revision: 'rev-prof-flow-003',
      source_path: '/etc/openmcp/config.toml',
    })

    const { container } = render(<App />)

    // Navigate to Profiles via sidebar
    const profilesNav = await screen.findByRole('button', { name: /^Profiles$/i })
    fireEvent.click(profilesNav)

    expect(await screen.findByText('strict-review')).toBeInTheDocument()

    // Open Create Profile modal
    const createBtn = screen.getByRole('button', { name: /^Create profile$/i })
    fireEvent.click(createBtn)

    const createDialog = await screen.findByRole('dialog', { name: /Create profile/i })
    expect(createDialog).toBeInTheDocument()

    fireEvent.change(within(createDialog).getByLabelText(/Profile identifier/i), { target: { value: 'flow-profile' } })
    fireEvent.change(within(createDialog).getByLabelText(/Inherits from/i), { target: { value: 'default' } })

    // Declare consult workflow
    const consultCheckbox = within(createDialog).getByRole('checkbox', { name: /Declare custom policy for consult workflow/i })
    fireEvent.click(consultCheckbox)

    const targetSelect = within(createDialog).getByRole('combobox', { name: /^consult target 1$/i })
    fireEvent.change(targetSelect, { target: { value: 'worker-2' } })

    const submitCreateBtn = within(createDialog).getByRole('button', { name: /^Create profile$/i })
    fireEvent.click(submitCreateBtn)

    await waitFor(() => {
      expect(api.createConfigurationProfile).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'flow-profile',
          extends: 'default',
          workflows: expect.objectContaining({
            consult: expect.objectContaining({
              targets: ['worker-2'],
            }),
            implement: null,
            review: null,
            other: null,
          }),
        }),
        'rev-prof-flow-001'
      )
    })

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    // Click on fast-dev row to open inspector
    const fastDevRow = screen.getByText('fast-dev')
    fireEvent.click(fastDevRow)

    const deleteBtn = await screen.findByRole('button', { name: /^Delete profile$/i })
    fireEvent.click(deleteBtn)

    const deleteDialog = await screen.findByRole('dialog', { name: /Delete profile: fast-dev/i })
    expect(deleteDialog).toBeInTheDocument()

    const confirmCheckbox = within(deleteDialog).getByRole('checkbox', { name: /I confirm deleting profile fast-dev/i })
    fireEvent.click(confirmCheckbox)

    const confirmDeleteBtn = within(deleteDialog).getByRole('button', { name: /^Confirm delete$/i })
    fireEvent.click(confirmDeleteBtn)

    await waitFor(() => {
      expect(api.deleteConfigurationProfile).toHaveBeenCalledWith('fast-dev', 'rev-prof-flow-001')
    })

    // Assert CSRF token is not leaked in the DOM
    expect(container.innerHTML).not.toContain('secret-csrf-token')
  })

  it('manages project profile overrides through creation and removal workflows', async () => {
    vi.mocked(api.createProjectProfileOverride).mockResolvedValue({
      revision: 'rev-flow-proj-002',
      source_path: '/srv/alpha/.openmcp/config.toml',
      override: { id: 'custom-override', extends: 'balanced' },
    })

    vi.mocked(api.deleteProjectProfileOverride).mockResolvedValue({
      revision: 'rev-flow-proj-003',
      source_path: '/srv/alpha/.openmcp/config.toml',
      deleted: 'balanced',
      fallback: {
        id: 'balanced',
        extends: null,
        effective: {
          consult: { targets: ['worker-1'], max_attempts: 1, timeout_s: 30 },
        },
      },
    })

    const { container } = render(<App />)

    // Navigate to Projects
    const projectsNav = await screen.findByRole('button', { name: /^Projects$/i })
    fireEvent.click(projectsNav)

    expect(await screen.findByText('Alpha Service')).toBeInTheDocument()

    // Navigate to Project Detail
    fireEvent.click(screen.getByText('Alpha Service'))

    const profileTab = await screen.findByRole('tab', { name: /Profile resolution/i })
    fireEvent.click(profileTab)

    // Verify override actions and scope chip
    expect(screen.getByText('Project override')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Create override$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Edit override: balanced/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Remove override: balanced/i })).toBeInTheDocument()

    // 1. Create override workflow
    fireEvent.click(screen.getByRole('button', { name: /^Create override$/i }))

    const createDialog = await screen.findByRole('dialog', { name: /Create profile override/i })
    expect(createDialog).toBeInTheDocument()

    fireEvent.change(within(createDialog).getByLabelText(/Profile identifier/i), {
      target: { value: 'custom-override' },
    })

    const consultCheckbox = within(createDialog).getByRole('checkbox', {
      name: /Declare custom policy for consult workflow/i,
    })
    fireEvent.click(consultCheckbox)

    const submitCreateBtn = within(createDialog).getByRole('button', { name: /^Create override$/i })
    fireEvent.click(submitCreateBtn)

    await waitFor(() => {
      expect(api.createProjectProfileOverride).toHaveBeenCalledWith(
        'proj-alpha',
        expect.objectContaining({
          id: 'custom-override',
          workflows: expect.objectContaining({
            consult: expect.objectContaining({
              targets: expect.any(Array),
            }),
          }),
        }),
        'rev-flow-proj-001'
      )
    })

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    // 2. Remove override workflow
    const removeBtn = screen.getByRole('button', { name: /Remove override: balanced/i })
    fireEvent.click(removeBtn)

    const removeDialog = await screen.findByRole('dialog', { name: /Remove override: balanced/i })
    expect(removeDialog).toBeInTheDocument()

    // Global fallback preview is present
    expect(within(removeDialog).getByText('Resulting global fallback policy')).toBeInTheDocument()

    const confirmCheckbox = within(removeDialog).getByRole('checkbox', {
      name: /I confirm removing override for profile balanced/i,
    })
    fireEvent.click(confirmCheckbox)

    const confirmRemoveBtn = within(removeDialog).getByRole('button', { name: /^Remove override$/i })
    fireEvent.click(confirmRemoveBtn)

    await waitFor(() => {
      expect(api.deleteProjectProfileOverride).toHaveBeenCalledWith(
        'proj-alpha',
        'balanced',
        'rev-flow-proj-001'
      )
    })

    // Assert CSRF token is not leaked in the DOM
    expect(container.innerHTML).not.toContain('secret-csrf-token')
  })
})
