import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import ProjectDetail from './ProjectDetail'

vi.mock('../api', () => {
  class MockDashboardApiError extends Error {
    constructor(message, status, payload) {
      super(message)
      this.name = 'DashboardApiError'
      this.status = status
      this.payload = payload
    }
  }

  return {
    getProject: vi.fn(),
    getProjectJobs: vi.fn(),
    getTaskGuide: vi.fn(),
    getConfiguration: vi.fn().mockResolvedValue({ valid: true }),
    getProjectProfileOverrides: vi.fn(),
    getProjectProfileOverride: vi.fn(),
    createProjectProfileOverride: vi.fn(),
    updateProjectProfileOverride: vi.fn(),
    deleteProjectProfileOverride: vi.fn(),
    getConfigurationProfile: vi.fn(),
    DashboardApiError: MockDashboardApiError,
  }
})

describe('ProjectDetail screen', () => {
  beforeEach(() => {
    vi.mocked(api.getConfiguration).mockResolvedValue({ valid: true })
    vi.mocked(api.getProjectProfileOverrides).mockResolvedValue({
      revision: 'rev-proj-001',
      source_path: '/home/user/workspace/demo/.openmcp/config.toml',
      global_default_profile: 'default',
      project_default_profile: 'custom-profile',
      available_targets: ['worker-1', 'worker-2'],
      overrides: [
        {
          id: 'custom-profile',
          extends: 'base-profile',
          declared: {
            implement: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
          },
          inherited: {
            consult: { targets: ['opus-consult'], max_attempts: 1, timeout_s: 60 },
          },
          effective: {
            consult: { targets: ['opus-consult'], max_attempts: 1, timeout_s: 60 },
            implement: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
          },
          sources: {
            consult: 'global',
            implement: 'project',
          },
        },
      ],
    })
    vi.mocked(api.getConfigurationProfile).mockResolvedValue({
      revision: 'rev-global-001',
      default_profile: 'default',
      available_targets: ['worker-1', 'worker-2'],
      profile: {
        id: 'custom-profile',
        extends: 'base-profile',
        declared: {},
        inherited: {},
        effective: {
          consult: { targets: ['global-consult'], max_attempts: 1, timeout_s: 30 },
          implement: { targets: ['global-worker'], max_attempts: 1, timeout_s: 60 },
        },
        sources: {
          consult: 'global',
          implement: 'global',
        },
      },
    })
  })
  const mockProjectData = {
    project: {
      id: 'proj-demo',
      alias: 'Demo Workspace',
      root: '/home/user/workspace/demo',
      created_at: '2026-09-04T12:00:00Z',
    },
    configuration: {
      global_default_profile: 'default',
      project_default_profile: 'custom-profile',
      profiles: [
        {
          id: 'custom-profile',
          parent: { value: 'base-profile', source: 'project' },
          declared: {
            implement: {
              selection: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
              source: 'project',
            },
          },
          inherited: {
            consult: { targets: ['opus-consult'], max_attempts: 1, timeout_s: 60 },
          },
          effective: {
            consult: { targets: ['opus-consult'], max_attempts: 1, timeout_s: 60 },
            implement: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
          },
          sources: {
            consult: 'global',
            implement: 'project',
          },
        },
        {
          id: 'root-profile',
          parent: { value: null, source: 'global' },
          declared: {},
          inherited: {},
          effective: {
            review: { targets: ['reviewer-target'], max_attempts: 1, timeout_s: 90 },
          },
          sources: {
            review: 'global',
          },
        },
      ],
    },
  }

  it('renders effective workflows without duplication and maps source names', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '/path/guide.json' })

    render(<ProjectDetail projectId="proj-demo" />)

    expect(await screen.findByText('Demo Workspace')).toBeInTheDocument()
    expect(screen.getByText('/home/user/workspace/demo')).toBeInTheDocument()

    // Check effective workflows (consult and implement)
    expect(screen.getByText('consult')).toBeInTheDocument()
    expect(screen.getByText('implement')).toBeInTheDocument()

    // Check source chips
    expect(screen.getByText('Repository')).toBeInTheDocument()
    expect(screen.getByText('Global')).toBeInTheDocument()

    // Ensure rows match effective list and not duplicates
    const consultWorkflowHeadings = screen.getAllByText('consult')
    expect(consultWorkflowHeadings.length).toBe(1)
  })

  it('suppresses source chip when parent profile is null in profile resolution tab', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })

    render(<ProjectDetail projectId="proj-demo" />)

    // Switch to profile resolution tab
    const profileTab = await screen.findByRole('tab', { name: /Profile resolution/i })
    fireEvent.click(profileTab)

    // For custom-profile, parent is base-profile (source project -> Repository)
    expect(screen.getByText('base-profile')).toBeInTheDocument()
    expect(screen.getAllByText('Repository').length).toBeGreaterThan(0)

    // Switch active profile to root-profile (parent is null)
    const select = screen.getByLabelText(/Select profile/i)
    fireEvent.change(select, { target: { value: 'root-profile' } })

    expect(screen.getByText('No parent')).toBeInTheDocument()
  })

  it('opens docked inspector on workflow row click', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })

    render(<ProjectDetail projectId="proj-demo" />)

    expect(await screen.findByText('consult')).toBeInTheDocument()

    const consultRow = screen.getByText('consult').closest('tr')
    fireEvent.click(consultRow)

    // Inspector should open
    expect(screen.getByRole('complementary', { name: /Inspector: Workflow: consult/i })).toBeInTheDocument()
    expect(screen.getByText('60 seconds')).toBeInTheDocument()
  })

  it('uses server inherited classification for overlapping self-extension rows', async () => {
    vi.mocked(api.getProject).mockResolvedValue({
      ...mockProjectData,
      configuration: {
        ...mockProjectData.configuration,
        profiles: [{
          ...mockProjectData.configuration.profiles[0],
          declared: {
            implement: mockProjectData.configuration.profiles[0].declared.implement,
          },
          inherited: {
            implement: { targets: ['opus-worker'], max_attempts: 1, timeout_s: 60 },
          },
          effective: {
            implement: { targets: ['opus-worker'], max_attempts: 1, timeout_s: 60 },
          },
          sources: { implement: 'global' },
        }],
      },
    })
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })

    render(<ProjectDetail projectId="proj-demo" />)
    const row = await screen.findByText('implement')
    fireEvent.click(row.closest('tr'))

    expect(screen.getByText('Inherited')).toBeInTheDocument()
  })

  it('displays error alert on project configuration load failure', async () => {
    const error = new Error('Invalid project configuration TOML')
    error.payload = { source_path: '/path/to/.openmcp/config.toml' }
    vi.mocked(api.getProject).mockRejectedValue(error)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })

    render(<ProjectDetail projectId="proj-demo" />)

    expect(await screen.findByText('Configuration error')).toBeInTheDocument()
    expect(screen.getByText('Invalid project configuration TOML')).toBeInTheDocument()
    expect(screen.getByText('/path/to/.openmcp/config.toml')).toBeInTheDocument()
  })

  it('renders invalid configuration health banner and last-known-good revision while project details remain visible', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })
    vi.mocked(api.getConfiguration).mockResolvedValue({
      valid: false,
      last_known_good_revision: 'rev-detail-lkg-004',
    })

    render(<ProjectDetail projectId="proj-demo" />)

    expect(await screen.findByText('Configuration invalid — showing last-known-good values')).toBeInTheDocument()
    expect(screen.getByText('rev-detail-lkg-004')).toBeInTheDocument()
    expect(screen.getByText('Demo Workspace')).toBeInTheDocument()
    expect(screen.getByText('/home/user/workspace/demo')).toBeInTheDocument()
    expect(screen.getByText('consult')).toBeInTheDocument()
    expect(screen.getByText('implement')).toBeInTheDocument()
  })

  it('displays override controls in Profile resolution tab and identifies project overrides vs global profiles', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })

    render(<ProjectDetail projectId="proj-demo" />)

    const profileTab = await screen.findByRole('tab', { name: /Profile resolution/i })
    fireEvent.click(profileTab)

    expect(screen.getByRole('button', { name: /^Create override$/i })).toBeInTheDocument()

    // For custom-profile (an override):
    expect(screen.getByText('Project override')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Edit override: custom-profile/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Remove override: custom-profile/i })).toBeInTheDocument()

    // Switch to root-profile (not overridden):
    const select = screen.getByLabelText(/Select profile/i)
    fireEvent.change(select, { target: { value: 'root-profile' } })

    expect(screen.getByText('Global profile')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Override profile: root-profile/i })).toBeInTheDocument()
  })

  it('opens profile editor to create a project override and submits payload with project revision', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })
    vi.mocked(api.createProjectProfileOverride).mockResolvedValue({
      revision: 'rev-proj-002',
      source_path: '/path/to/.openmcp/config.toml',
      override: { id: 'new-override', extends: 'base-profile' },
    })

    render(<ProjectDetail projectId="proj-demo" />)

    const profileTab = await screen.findByRole('tab', { name: /Profile resolution/i })
    fireEvent.click(profileTab)

    const createBtn = screen.getByRole('button', { name: /^Create override$/i })
    fireEvent.click(createBtn)

    const dialog = await screen.findByRole('dialog', { name: /Create profile override/i })
    expect(dialog).toBeInTheDocument()

    const idInput = screen.getByLabelText(/Profile identifier/i)
    fireEvent.change(idInput, { target: { value: 'new-override' } })

    const consultCheckbox = screen.getByRole('checkbox', { name: /Declare custom policy for consult workflow/i })
    fireEvent.click(consultCheckbox)

    const submitBtn = within(dialog).getByRole('button', { name: /^Create override$/i })
    fireEvent.click(submitBtn)

    expect(api.createProjectProfileOverride).toHaveBeenCalledWith(
      'proj-demo',
      expect.objectContaining({
        id: 'new-override',
        workflows: expect.objectContaining({
          consult: expect.objectContaining({
            targets: expect.any(Array),
          }),
        }),
      }),
      'rev-proj-001'
    )
  })

  it('opens profile editor to edit an existing project override with prefilled data', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })
    vi.mocked(api.getProjectProfileOverride).mockResolvedValue({
      revision: 'rev-proj-001',
      source_path: '/path/to/.openmcp/config.toml',
      override: {
        id: 'custom-profile',
        extends: 'base-profile',
        declared: {
          implement: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
        },
        inherited: {},
        effective: {
          implement: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
        },
        sources: { implement: 'project' },
      },
    })
    vi.mocked(api.updateProjectProfileOverride).mockResolvedValue({
      revision: 'rev-proj-003',
      source_path: '/path/to/.openmcp/config.toml',
      override: { id: 'custom-profile' },
    })

    render(<ProjectDetail projectId="proj-demo" />)

    const profileTab = await screen.findByRole('tab', { name: /Profile resolution/i })
    fireEvent.click(profileTab)

    const editBtn = screen.getByRole('button', { name: /Edit override: custom-profile/i })
    fireEvent.click(editBtn)

    const dialog = await screen.findByRole('dialog', { name: /Edit profile override: custom-profile/i })
    expect(dialog).toBeInTheDocument()

    const idInput = screen.getByLabelText(/Profile identifier/i)
    expect(idInput).toBeDisabled()

    const submitBtn = within(dialog).getByRole('button', { name: /^Save override$/i })
    fireEvent.click(submitBtn)

    expect(api.updateProjectProfileOverride).toHaveBeenCalledWith(
      'proj-demo',
      'custom-profile',
      expect.objectContaining({ id: 'custom-profile' }),
      'rev-proj-001'
    )
  })

  it('shows remove override dialog with server-resolved global fallback preview and confirms removal with "Remove override" button', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })
    vi.mocked(api.deleteProjectProfileOverride).mockResolvedValue({
      revision: 'rev-proj-004',
      source_path: '/path/to/.openmcp/config.toml',
      deleted: 'custom-profile',
      fallback: { id: 'custom-profile' },
    })

    render(<ProjectDetail projectId="proj-demo" />)

    const profileTab = await screen.findByRole('tab', { name: /Profile resolution/i })
    fireEvent.click(profileTab)

    const removeBtn = screen.getByRole('button', { name: /Remove override: custom-profile/i })
    fireEvent.click(removeBtn)

    const dialog = await screen.findByRole('dialog', { name: /Remove override: custom-profile/i })
    expect(dialog).toBeInTheDocument()

    // Preview shows server-resolved fallback
    expect(screen.getByText('Resulting global fallback policy')).toBeInTheDocument()
    expect(screen.getByText('global-consult')).toBeInTheDocument()
    expect(screen.getByText('global-worker')).toBeInTheDocument()

    // Confirm checkbox and button labeled "Remove override"
    const confirmCheckbox = screen.getByRole('checkbox', {
      name: /I confirm removing override for profile custom-profile/i,
    })
    fireEvent.click(confirmCheckbox)

    const confirmRemoveBtn = screen.getByRole('button', { name: /^Remove override$/i })
    fireEvent.click(confirmRemoveBtn)

    expect(api.deleteProjectProfileOverride).toHaveBeenCalledWith(
      'proj-demo',
      'custom-profile',
      'rev-proj-001'
    )
  })

  it('handles referenced rejection when removing project override by displaying blocking references', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })
    const refError = new api.DashboardApiError('Project override is referenced', 409, {
      code: 'referenced',
      references: [
        { scope: 'project', profile_id: 'dependent-profile', relationship: 'extends' },
      ],
    })
    vi.mocked(api.deleteProjectProfileOverride).mockRejectedValue(refError)

    render(<ProjectDetail projectId="proj-demo" />)

    const profileTab = await screen.findByRole('tab', { name: /Profile resolution/i })
    fireEvent.click(profileTab)

    const removeBtn = screen.getByRole('button', { name: /Remove override: custom-profile/i })
    fireEvent.click(removeBtn)

    const confirmCheckbox = await screen.findByRole('checkbox', {
      name: /I confirm removing override for profile custom-profile/i,
    })
    fireEvent.click(confirmCheckbox)

    const confirmRemoveBtn = screen.getByRole('button', { name: /^Remove override$/i })
    fireEvent.click(confirmRemoveBtn)

    expect(await screen.findByText('Profile override is currently referenced')).toBeInTheDocument()
    expect(screen.getByText('dependent-profile')).toBeInTheDocument()
  })

  it('preserves dirty draft in profile editor across project polling updates', async () => {
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })

    render(<ProjectDetail projectId="proj-demo" />)

    const profileTab = await screen.findByRole('tab', { name: /Profile resolution/i })
    fireEvent.click(profileTab)

    const createBtn = screen.getByRole('button', { name: /^Create override$/i })
    fireEvent.click(createBtn)

    const idInput = await screen.findByLabelText(/Profile identifier/i)
    fireEvent.change(idInput, { target: { value: 'dirty-draft-id' } })

    // Input holds dirty draft
    expect(idInput.value).toBe('dirty-draft-id')
  })

  it('does not advance revision on conflict and prevents stale draft overwrite after reload', async () => {
    vi.mocked(api.updateProjectProfileOverride).mockClear()
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })
    vi.mocked(api.getProjectProfileOverride).mockResolvedValue({
      revision: 'rev-proj-001',
      source_path: '/path/to/.openmcp/config.toml',
      override: {
        id: 'custom-profile',
        extends: 'base-profile',
        declared: {
          implement: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
        },
        inherited: {},
        effective: {
          implement: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
        },
        sources: { implement: 'project' },
      },
    })
    vi.mocked(api.updateProjectProfileOverride).mockRejectedValueOnce(
      new api.DashboardApiError('Conflict', 409, {
        code: 'conflict',
        message: 'Conflict occurred',
        current: 'rev-proj-002',
      })
    )

    render(<ProjectDetail projectId="proj-demo" />)

    const profileTab = await screen.findByRole('tab', { name: /Profile resolution/i })
    fireEvent.click(profileTab)

    const editBtn = screen.getByRole('button', { name: /Edit override: custom-profile/i })
    fireEvent.click(editBtn)

    const dialog = await screen.findByRole('dialog', { name: /Edit profile override: custom-profile/i })
    expect(dialog).toBeInTheDocument()

    const timeoutInput = within(dialog).getByLabelText(/implement timeout in seconds/i)
    expect(timeoutInput.value).toBe('120')

    // Dirty the draft
    fireEvent.change(timeoutInput, { target: { value: '999' } })

    const submitBtn = within(dialog).getByRole('button', { name: /^Save override$/i })
    fireEvent.click(submitBtn)

    expect(await within(dialog).findByText(/Configuration conflict detected/i)).toBeInTheDocument()
    expect(submitBtn).toBeDisabled()

    // Submitting stale draft during conflict is blocked
    const form = dialog.querySelector('form')
    fireEvent.submit(form)
    expect(api.updateProjectProfileOverride).toHaveBeenCalledTimes(1)

    // Simulate external reload
    vi.mocked(api.getProjectProfileOverrides).mockResolvedValueOnce({
      revision: 'rev-proj-002',
      source_path: '/path/to/.openmcp/config.toml',
      global_default_profile: 'default',
      project_default_profile: 'custom-profile',
      available_targets: ['worker-1', 'worker-2', 'worker-external-v2'],
      overrides: [
        {
          id: 'custom-profile',
          extends: '',
          declared: {
            implement: { targets: ['worker-external-v2'], max_attempts: 3, timeout_s: 180 },
          },
          inherited: {
            consult: { targets: ['opus-consult'], max_attempts: 1, timeout_s: 60 },
          },
          effective: {
            consult: { targets: ['opus-consult'], max_attempts: 1, timeout_s: 60 },
            implement: { targets: ['worker-external-v2'], max_attempts: 3, timeout_s: 180 },
          },
          sources: {
            consult: 'global',
            implement: 'project',
          },
        },
      ],
    })

    const reloadBtn = within(dialog).getByRole('button', { name: /Reload current configuration/i })
    fireEvent.click(reloadBtn)

    await vi.waitFor(() => {
      expect(within(dialog).queryByText(/Configuration conflict detected/i)).not.toBeInTheDocument()
    })

    // Stale draft replaced by reloaded server data
    expect(within(dialog).getByLabelText(/implement timeout in seconds/i).value).toBe('180')
    expect(submitBtn).not.toBeDisabled()

    vi.mocked(api.updateProjectProfileOverride).mockResolvedValueOnce({
      revision: 'rev-proj-003',
      source_path: '/path/to/.openmcp/config.toml',
      override: { id: 'custom-profile' },
    })

    fireEvent.click(submitBtn)

    await vi.waitFor(() => {
      expect(api.updateProjectProfileOverride).toHaveBeenCalledTimes(2)
      expect(api.updateProjectProfileOverride).toHaveBeenLastCalledWith(
        'proj-demo',
        'custom-profile',
        expect.objectContaining({
          id: 'custom-profile',
          workflows: expect.objectContaining({
            implement: expect.objectContaining({
              targets: ['worker-external-v2'],
              timeout_s: 180,
            }),
          }),
        }),
        'rev-proj-002'
      )
    })
    expect(api.updateProjectProfileOverride).not.toHaveBeenLastCalledWith(
      'proj-demo',
      'custom-profile',
      expect.objectContaining({
        workflows: expect.objectContaining({
          implement: expect.objectContaining({
            timeout_s: 999,
          }),
        }),
      }),
      expect.anything()
    )
  })

  it('preserves conflict block and prevents save when project override reload returns missing entity, missing revision, or fails', async () => {
    vi.mocked(api.updateProjectProfileOverride).mockClear()
    vi.mocked(api.getProject).mockResolvedValue(mockProjectData)
    vi.mocked(api.getProjectJobs).mockResolvedValue([])
    vi.mocked(api.getTaskGuide).mockResolvedValue({ guide: {}, source_path: '' })
    vi.mocked(api.getProjectProfileOverride).mockResolvedValue({
      revision: 'rev-proj-001',
      source_path: '/path/to/.openmcp/config.toml',
      override: {
        id: 'custom-profile',
        extends: 'base-profile',
        declared: {
          implement: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
        },
        inherited: {},
        effective: {
          implement: { targets: ['worker-1', 'worker-2'], max_attempts: 2, timeout_s: 120 },
        },
        sources: { implement: 'project' },
      },
    })
    vi.mocked(api.updateProjectProfileOverride).mockRejectedValueOnce(
      new api.DashboardApiError('Conflict', 409, {
        code: 'conflict',
        message: 'Conflict occurred',
        current: 'rev-proj-002',
      })
    )

    render(<ProjectDetail projectId="proj-demo" />)

    const profileTab = await screen.findByRole('tab', { name: /Profile resolution/i })
    fireEvent.click(profileTab)

    const editBtn = screen.getByRole('button', { name: /Edit override: custom-profile/i })
    fireEvent.click(editBtn)

    const dialog = await screen.findByRole('dialog', { name: /Edit profile override: custom-profile/i })
    expect(dialog).toBeInTheDocument()

    const timeoutInput = within(dialog).getByLabelText(/implement timeout in seconds/i)
    fireEvent.change(timeoutInput, { target: { value: '999' } })

    const submitBtn = within(dialog).getByRole('button', { name: /^Save override$/i })
    fireEvent.click(submitBtn)

    expect(await within(dialog).findByText(/Configuration conflict detected/i)).toBeInTheDocument()
    expect(submitBtn).toBeDisabled()

    const form = dialog.querySelector('form')
    const reloadBtn = within(dialog).getByRole('button', { name: /Reload current configuration/i })

    // 1. Reload returns missing entity (e.g. override was deleted on server)
    vi.mocked(api.getProjectProfileOverrides).mockResolvedValueOnce({
      revision: 'rev-proj-002',
      source_path: '/path/to/.openmcp/config.toml',
      overrides: [],
    })
    fireEvent.click(reloadBtn)

    await vi.waitFor(() => {
      expect(within(dialog).getAllByText(/Profile override no longer exists or could not be reloaded/i).length).toBeGreaterThan(0)
    })
    expect(within(dialog).getByText(/Configuration conflict detected/i)).toBeInTheDocument()
    expect(submitBtn).toBeDisabled()

    // Submit remains blocked
    fireEvent.submit(form)
    expect(api.updateProjectProfileOverride).toHaveBeenCalledTimes(1)

    // 2. Reload returns missing revision
    vi.mocked(api.getProjectProfileOverrides).mockResolvedValueOnce({
      revision: '',
      overrides: [
        {
          id: 'custom-profile',
          extends: 'base-profile',
          declared: {
            implement: { targets: ['worker-1'], max_attempts: 1, timeout_s: 60 },
          },
        },
      ],
    })
    fireEvent.click(reloadBtn)

    await vi.waitFor(() => {
      expect(within(dialog).getAllByText(/Reload response missing configuration revision/i).length).toBeGreaterThan(0)
    })
    expect(within(dialog).getByText(/Configuration conflict detected/i)).toBeInTheDocument()
    expect(submitBtn).toBeDisabled()

    // Submit remains blocked
    fireEvent.submit(form)
    expect(api.updateProjectProfileOverride).toHaveBeenCalledTimes(1)

    // 3. Reload fails when API throws error
    vi.mocked(api.getProjectProfileOverrides).mockRejectedValueOnce(new Error('Network error on reload'))
    fireEvent.click(reloadBtn)

    await vi.waitFor(() => {
      expect(within(dialog).getAllByText(/Profile override no longer exists or could not be reloaded/i).length).toBeGreaterThan(0)
    })
    expect(within(dialog).getByText(/Configuration conflict detected/i)).toBeInTheDocument()
    expect(submitBtn).toBeDisabled()

    // Submit remains blocked
    fireEvent.submit(form)
    expect(api.updateProjectProfileOverride).toHaveBeenCalledTimes(1)
  })
})
