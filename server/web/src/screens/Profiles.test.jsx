import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import Profiles from './Profiles'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    getProfiles: vi.fn(),
    getConfiguration: vi.fn().mockResolvedValue({ valid: true }),
    getConfigurationProfiles: vi.fn(),
    getConfigurationProfile: vi.fn(),
    createConfigurationProfile: vi.fn(),
    updateConfigurationProfile: vi.fn(),
    deleteConfigurationProfile: vi.fn(),
  }
})

describe('Profiles screen', () => {
  const mockProfiles = {
    default: 'default',
    available: ['default', 'strict-review', 'fast-dev'],
  }

  const mockProfilesConfig = {
    revision: 'rev-prof-001',
    source_path: '/etc/openmcp/config.toml',
    default_profile: 'default',
    available_targets: ['target-a', 'target-b', 'target-c'],
    profiles: [
      {
        id: 'default',
        extends: null,
        declared: {
          consult: { targets: ['target-a'], max_attempts: 1, timeout_s: 30 },
          implement: { targets: ['target-a', 'target-b'], max_attempts: 2, timeout_s: 60 },
          review: { targets: ['target-c'], max_attempts: 1, timeout_s: 0 },
          other: { targets: ['target-a'], max_attempts: 1, timeout_s: 0 },
        },
        inherited: {},
        effective: {
          consult: { targets: ['target-a'], max_attempts: 1, timeout_s: 30 },
          implement: { targets: ['target-a', 'target-b'], max_attempts: 2, timeout_s: 60 },
          review: { targets: ['target-c'], max_attempts: 1, timeout_s: 0 },
          other: { targets: ['target-a'], max_attempts: 1, timeout_s: 0 },
        },
        sources: { consult: 'default', implement: 'default', review: 'default', other: 'default' },
      },
      {
        id: 'fast-dev',
        extends: 'default',
        declared: {
          consult: { targets: ['target-b'], max_attempts: 1, timeout_s: 15 },
        },
        inherited: {
          implement: { targets: ['target-a', 'target-b'], max_attempts: 2, timeout_s: 60 },
          review: { targets: ['target-c'], max_attempts: 1, timeout_s: 0 },
          other: { targets: ['target-a'], max_attempts: 1, timeout_s: 0 },
        },
        effective: {
          consult: { targets: ['target-b'], max_attempts: 1, timeout_s: 15 },
          implement: { targets: ['target-a', 'target-b'], max_attempts: 2, timeout_s: 60 },
          review: { targets: ['target-c'], max_attempts: 1, timeout_s: 0 },
          other: { targets: ['target-a'], max_attempts: 1, timeout_s: 0 },
        },
        sources: { consult: 'fast-dev', implement: 'default', review: 'default', other: 'default' },
      },
    ],
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.getConfiguration).mockResolvedValue({ valid: true })
    vi.mocked(api.getProfiles).mockResolvedValue(mockProfiles)
    vi.mocked(api.getConfigurationProfiles).mockResolvedValue(mockProfilesConfig)
    vi.mocked(api.getConfigurationProfile).mockImplementation(async (id) => {
      const match = mockProfilesConfig.profiles.find((p) => p.id === id)
      return {
        revision: mockProfilesConfig.revision,
        source_path: mockProfilesConfig.source_path,
        default_profile: mockProfilesConfig.default_profile,
        available_targets: mockProfilesConfig.available_targets,
        profile: match || {
          id,
          extends: null,
          declared: {},
          inherited: {},
          effective: {},
          sources: {},
        },
      }
    })
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

  it('opens profile editor in create mode and submits new profile with declared workflows and targets', async () => {
    vi.mocked(api.createConfigurationProfile).mockResolvedValue({
      revision: 'rev-prof-002',
      source_path: '/etc/openmcp/config.toml',
      default_profile: 'default',
      available_targets: ['target-a', 'target-b', 'target-c'],
      profile: {
        id: 'custom-profile',
        extends: 'default',
        declared: {
          consult: { targets: ['target-b', 'target-a'], max_attempts: 2, timeout_s: 45 },
        },
        inherited: {},
        effective: {},
        sources: {},
      },
    })

    render(<Profiles />)
    expect(await screen.findByText('default')).toBeInTheDocument()

    const createBtn = screen.getByRole('button', { name: /^Create profile$/i })
    fireEvent.click(createBtn)

    const dialog = await screen.findByRole('dialog', { name: /Create profile/i })
    expect(dialog).toBeInTheDocument()

    // Fill profile id and parent extends
    fireEvent.change(within(dialog).getByLabelText(/Profile identifier/i), { target: { value: 'custom-profile' } })
    fireEvent.change(within(dialog).getByLabelText(/Inherits from/i), { target: { value: 'default' } })

    // Declare consult workflow
    const consultToggle = within(dialog).getByRole('checkbox', { name: /Declare custom policy for consult workflow/i })
    fireEvent.click(consultToggle)

    // Add a second target to consult
    const addTargetBtn = within(dialog).getByRole('button', { name: /Add target to consult workflow/i })
    fireEvent.click(addTargetBtn)

    // Select target-b for target 2
    const target2Select = within(dialog).getByRole('combobox', { name: /^consult target 2$/i })
    fireEvent.change(target2Select, { target: { value: 'target-b' } })

    // Move target 2 up to be first
    const moveUpBtn = within(dialog).getByRole('button', { name: /Move consult target 2 up/i })
    fireEvent.click(moveUpBtn)

    // Set max attempts and timeout
    const maxAttemptsInput = within(dialog).getByRole('spinbutton', { name: /^consult max attempts$/i })
    fireEvent.change(maxAttemptsInput, { target: { value: '2' } })

    const timeoutInput = within(dialog).getByRole('spinbutton', { name: /^consult timeout in seconds$/i })
    fireEvent.change(timeoutInput, { target: { value: '45' } })

    // Submit form
    const submitBtn = within(dialog).getByRole('button', { name: /^Create profile$/i })
    fireEvent.click(submitBtn)

    await vi.waitFor(() => {
      expect(api.createConfigurationProfile).toHaveBeenCalledWith(
        {
          id: 'custom-profile',
          extends: 'default',
          workflows: {
            consult: {
              targets: ['target-b', 'target-a'],
              max_attempts: 2,
              timeout_s: 45,
            },
            implement: null,
            review: null,
            other: null,
          },
        },
        'rev-prof-001'
      )
    })

    await vi.waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('opens profile editor in edit mode with immutable identifier and preserves inherited policies', async () => {
    vi.mocked(api.updateConfigurationProfile).mockResolvedValue({
      revision: 'rev-prof-003',
      source_path: '/etc/openmcp/config.toml',
      default_profile: 'default',
      available_targets: ['target-a', 'target-b', 'target-c'],
      profile: {
        id: 'fast-dev',
        extends: null,
        declared: {},
        inherited: {},
        effective: {},
        sources: {},
      },
    })

    render(<Profiles />)
    expect(await screen.findByText('fast-dev')).toBeInTheDocument()

    // Click row to select and open Inspector
    const fastDevRow = screen.getByText('fast-dev').closest('tr')
    fireEvent.click(fastDevRow)

    const editBtn = await screen.findByRole('button', { name: /^Edit profile$/i })
    fireEvent.click(editBtn)

    const dialog = await screen.findByRole('dialog', { name: /Edit profile: fast-dev/i })
    expect(dialog).toBeInTheDocument()

    // Profile identifier is immutable
    const idInput = within(dialog).getByLabelText(/Profile identifier/i)
    expect(idInput).toBeDisabled()
    expect(idInput.value).toBe('fast-dev')

    // Consult is declared, implement is inherited
    const consultToggle = within(dialog).getByRole('checkbox', { name: /Declare custom policy for consult workflow/i })
    expect(consultToggle).toBeChecked()

    const implementToggle = within(dialog).getByRole('checkbox', { name: /Declare custom policy for implement workflow/i })
    expect(implementToggle).not.toBeChecked()
    expect(within(dialog).getByText(/target-a, target-b/)).toBeInTheDocument()

    // Change parent to None
    const extendsSelect = within(dialog).getByLabelText(/Inherits from/i)
    fireEvent.change(extendsSelect, { target: { value: '' } })

    const saveBtn = within(dialog).getByRole('button', { name: /^Save profile$/i })
    fireEvent.click(saveBtn)

    await vi.waitFor(() => {
      expect(api.updateConfigurationProfile).toHaveBeenCalledWith(
        'fast-dev',
        expect.objectContaining({
          id: 'fast-dev',
          extends: null,
          workflows: expect.objectContaining({
            consult: expect.objectContaining({ targets: ['target-b'] }),
            implement: null,
          }),
        }),
        'rev-prof-001'
      )
    })

    await vi.waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
  })

  it('validates that declared workflows have at least one target before submitting', async () => {
    render(<Profiles />)
    expect(await screen.findByText('default')).toBeInTheDocument()

    const createBtn = screen.getByRole('button', { name: /^Create profile$/i })
    fireEvent.click(createBtn)

    const dialog = await screen.findByRole('dialog', { name: /Create profile/i })
    expect(dialog).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText(/Profile identifier/i), { target: { value: 'invalid-profile' } })

    // Declare review workflow
    const reviewToggle = within(dialog).getByRole('checkbox', { name: /Declare custom policy for review workflow/i })
    fireEvent.click(reviewToggle)

    // Remove the target
    const removeBtn = within(dialog).getByRole('button', { name: /Remove review target 1/i })
    fireEvent.click(removeBtn)

    // Submit
    const submitBtn = within(dialog).getByRole('button', { name: /^Create profile$/i })
    fireEvent.click(submitBtn)

    expect(await within(dialog).findByText(/review workflow requires at least one target/i)).toBeInTheDocument()
    expect(api.createConfigurationProfile).not.toHaveBeenCalled()
  })

  it('preserves dirty draft when background polling refreshes profiles', async () => {
    render(<Profiles />)
    expect(await screen.findByText('default')).toBeInTheDocument()

    const createBtn = screen.getByRole('button', { name: /^Create profile$/i })
    fireEvent.click(createBtn)

    const dialog = await screen.findByRole('dialog', { name: /Create profile/i })
    const idInput = within(dialog).getByLabelText(/Profile identifier/i)
    fireEvent.change(idInput, { target: { value: 'my-unsaved-draft' } })

    // Simulate background polling refresh
    vi.mocked(api.getProfiles).mockResolvedValue({
      default: 'default',
      available: ['default', 'strict-review', 'fast-dev', 'polled-profile'],
    })

    // Advance timers / fire another render
    expect(idInput.value).toBe('my-unsaved-draft')
  })

  it('handles configuration conflict by preserving draft and offering reload', async () => {
    vi.mocked(api.updateConfigurationProfile).mockRejectedValueOnce(
      new api.DashboardApiError('Configuration conflict', 409, {
        code: 'configuration_conflict',
        unchanged: 'Configuration file changed on the server.',
        recovery: 'Reload current configuration and retry.',
        current: 'rev-prof-999',
      })
    )

    render(<Profiles />)
    expect(await screen.findByText('fast-dev')).toBeInTheDocument()

    fireEvent.click(screen.getByText('fast-dev').closest('tr'))
    const editBtn = await screen.findByRole('button', { name: /^Edit profile$/i })
    fireEvent.click(editBtn)

    const dialog = await screen.findByRole('dialog', { name: /Edit profile: fast-dev/i })
    const saveBtn = within(dialog).getByRole('button', { name: /^Save profile$/i })
    fireEvent.click(saveBtn)

    expect(await within(dialog).findByText(/Configuration conflict detected/i)).toBeInTheDocument()
    expect(within(dialog).getByText(/Configuration file changed on the server/i)).toBeInTheDocument()

    // Draft is preserved
    expect(within(dialog).getByLabelText(/Profile identifier/i).value).toBe('fast-dev')

    // Click Reload current configuration
    const reloadBtn = within(dialog).getByRole('button', { name: /Reload current configuration/i })
    fireEvent.click(reloadBtn)

    await vi.waitFor(() => {
      expect(api.getConfigurationProfile).toHaveBeenCalledWith('fast-dev')
    })
  })

  it('handles deletion: unreferenced requires confirmation, referenced displays blocking references', async () => {
    vi.mocked(api.deleteConfigurationProfile).mockResolvedValueOnce({
      deleted: 'fast-dev',
      revision: 'rev-prof-002',
    })

    render(<Profiles />)
    expect(await screen.findByText('fast-dev')).toBeInTheDocument()

    // 1. Unreferenced deletion
    fireEvent.click(screen.getByText('fast-dev').closest('tr'))
    const deleteBtn = await screen.findByRole('button', { name: /^Delete profile$/i })
    fireEvent.click(deleteBtn)

    const dialog = await screen.findByRole('dialog', { name: /Delete profile: fast-dev/i })
    expect(dialog).toBeInTheDocument()

    const confirmBtn = within(dialog).getByRole('button', { name: /^Confirm delete$/i })
    expect(confirmBtn).toBeDisabled()

    const checkbox = within(dialog).getByLabelText(/I confirm deleting profile fast-dev/i)
    fireEvent.click(checkbox)
    expect(confirmBtn).not.toBeDisabled()

    fireEvent.click(confirmBtn)

    await vi.waitFor(() => {
      expect(api.deleteConfigurationProfile).toHaveBeenCalledWith('fast-dev', 'rev-prof-001')
    })

    await vi.waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    // 2. Referenced deletion
    vi.mocked(api.deleteConfigurationProfile).mockRejectedValueOnce(
      new api.DashboardApiError('Profile is referenced', 409, {
        code: 'referenced',
        references: [
          { scope: 'global', relationship: 'default_profile' },
          { scope: 'project', project_id: 'proj-1', relationship: 'extends', profile_id: 'custom' },
        ],
      })
    )

    fireEvent.click(screen.getByText('default').closest('tr'))
    const deleteBtn2 = await screen.findByRole('button', { name: /^Delete profile$/i })
    fireEvent.click(deleteBtn2)

    const dialog2 = await screen.findByRole('dialog', { name: /Delete profile: default/i })
    const checkbox2 = within(dialog2).getByLabelText(/I confirm deleting profile default/i)
    fireEvent.click(checkbox2)
    fireEvent.click(within(dialog2).getByRole('button', { name: /^Confirm delete$/i }))

    expect(await screen.findByRole('dialog', { name: /Blocking references for profile default/i })).toBeInTheDocument()
    expect(screen.getByText('Profile is currently referenced')).toBeInTheDocument()
    expect(screen.getByText('Default profile')).toBeInTheDocument()
    expect(screen.getByText('Project (proj-1)')).toBeInTheDocument()
    expect(screen.getByText('Parent profile (extends)')).toBeInTheDocument()
  }, 15000)
})
