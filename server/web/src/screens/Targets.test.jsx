import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import Targets from './Targets'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    getTargets: vi.fn(),
    getConfiguration: vi.fn().mockResolvedValue({ valid: true }),
    getConfigurationTargets: vi.fn(),
    getConfigurationTarget: vi.fn(),
    createConfigurationTarget: vi.fn(),
    updateConfigurationTarget: vi.fn(),
    deleteConfigurationTarget: vi.fn(),
  }
})

describe('Targets screen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.history.replaceState({}, '', '/dashboard/targets')
    vi.mocked(api.getConfiguration).mockResolvedValue({ valid: true })
    vi.mocked(api.getConfigurationTargets).mockResolvedValue({ revision: 'rev-001', targets: [] })
  })
  const mockTargets = [
    {
      id: 'target-healthy',
      backend: 'claude',
      model: 'claude-3-7-sonnet',
      isolated: true,
      read_only: false,
      max_concurrency: 4,
      active: 1,
      healthy: true,
      circuit_open_until: '',
    },
    {
      id: 'target-circuit',
      backend: 'gemini',
      model: 'gemini-2.5-pro',
      isolated: false,
      read_only: true,
      max_concurrency: 2,
      active: 0,
      healthy: true,
      circuit_open_until: '2099-09-04T13:00:00Z',
    },
    {
      id: 'target-down',
      backend: 'local',
      model: 'llama-3',
      isolated: true,
      read_only: false,
      max_concurrency: 1,
      active: 0,
      healthy: false,
      circuit_open_until: '',
    },
  ]

  it('renders targets with distinct health status markers and counts', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)

    render(<Targets />)

    expect(await screen.findByText('target-healthy')).toBeInTheDocument()
    expect(screen.getByText('target-circuit')).toBeInTheDocument()
    expect(screen.getByText('target-down')).toBeInTheDocument()

    expect(screen.getAllByText('Healthy').length).toBeGreaterThan(0)
    expect(screen.getByText('Circuit open')).toBeInTheDocument()
    expect(screen.getByText('Unhealthy')).toBeInTheDocument()
  })

  it('treats an expired circuit timestamp as healthy', async () => {
    vi.mocked(api.getTargets).mockResolvedValue([{
      ...mockTargets[0],
      id: 'target-expired-circuit',
      circuit_open_until: '2020-01-01T00:00:00Z',
    }])

    render(<Targets />)

    expect(await screen.findByText('target-expired-circuit')).toBeInTheDocument()
    expect(screen.getAllByText('Healthy').length).toBeGreaterThan(0)
    expect(screen.queryByText('Circuit open')).not.toBeInTheDocument()
  })

  it('filters targets by status button and search query', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)

    render(<Targets />)

    expect(await screen.findByText('target-healthy')).toBeInTheDocument()

    // Filter by needing attention (circuit-open and down)
    const attentionBtn = screen.getByRole('button', { name: /Needing attention/i })
    fireEvent.click(attentionBtn)

    expect(screen.queryByText('target-healthy')).not.toBeInTheDocument()
    expect(screen.getByText('target-circuit')).toBeInTheDocument()
    expect(screen.getByText('target-down')).toBeInTheDocument()
  })

  it('opens docked inspector on row click with target details', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)

    render(<Targets />)

    expect(await screen.findByText('target-healthy')).toBeInTheDocument()

    const healthyRow = screen.getByText('target-healthy').closest('tr')
    fireEvent.click(healthyRow)

    expect(screen.getByRole('complementary', { name: /Inspector: Target: target-healthy/i })).toBeInTheDocument()
    expect(screen.getByText('4 concurrent jobs')).toBeInTheDocument()
  })

  it('renders invalid configuration health banner and last-known-good revision while targets remain visible', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)
    vi.mocked(api.getConfiguration).mockResolvedValue({
      valid: false,
      last_known_good_revision: 'rev-targets-lkg-002',
    })

    render(<Targets />)

    expect(await screen.findByText('Configuration invalid — showing last-known-good values')).toBeInTheDocument()
    expect(screen.getByText('rev-targets-lkg-002')).toBeInTheDocument()
    expect(screen.getByText('target-healthy')).toBeInTheDocument()
    expect(screen.getByText('target-circuit')).toBeInTheDocument()
    expect(screen.getByText('target-down')).toBeInTheDocument()
  })

  it('opens target editor in create mode and submits new target with all fields, arguments, and redaction', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)
    vi.mocked(api.getConfigurationTargets).mockResolvedValue({ revision: 'rev-001', targets: [] })
    vi.mocked(api.createConfigurationTarget).mockResolvedValue({
      revision: 'rev-002',
      target: { id: 'custom-target', backend: 'codex', model: 'gpt-4o' },
    })

    render(<Targets />)
    expect(await screen.findByText('target-healthy')).toBeInTheDocument()

    const createBtn = screen.getByRole('button', { name: /^Create target$/i })
    fireEvent.click(createBtn)

    const dialog = await screen.findByRole('dialog', { name: /Create target/i })
    expect(dialog).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText(/Identifier/i), { target: { value: 'custom-target' } })
    fireEvent.change(within(dialog).getByLabelText(/^Model$/i), { target: { value: 'gpt-4o' } })
    fireEvent.change(within(dialog).getByLabelText(/Backend profile/i), { target: { value: 'fast' } })
    fireEvent.change(within(dialog).getByLabelText(/Reasoning effort/i), { target: { value: 'high' } })
    fireEvent.change(within(dialog).getByLabelText(/System prompt/i), { target: { value: 'SECRET_OPERATOR_PROMPT_ABC' } })
    fireEvent.change(within(dialog).getByLabelText(/Max concurrency/i), { target: { value: '3' } })
    fireEvent.click(within(dialog).getByLabelText(/Process isolation/i))

    // Add and reorder arguments
    const addArgBtn = within(dialog).getByRole('button', { name: /Add argument/i })
    fireEvent.click(addArgBtn)
    fireEvent.change(within(dialog).getByRole('textbox', { name: /^Argument 1$/i }), { target: { value: '--first' } })

    fireEvent.click(addArgBtn)
    fireEvent.change(within(dialog).getByRole('textbox', { name: /^Argument 2$/i }), { target: { value: '--second' } })

    // Move second up
    const moveUpBtn = within(dialog).getByRole('button', { name: /Move argument 2 up/i })
    fireEvent.click(moveUpBtn)

    // Submit form
    const submitBtn = within(dialog).getByRole('button', { name: /^Create target$/i })
    fireEvent.click(submitBtn)

    await vi.waitFor(() => {
      expect(api.createConfigurationTarget).toHaveBeenCalledWith(
        {
          id: 'custom-target',
          backend: 'codex',
          model: 'gpt-4o',
          backend_profile: 'fast',
          reasoning: 'high',
          system_prompt: 'SECRET_OPERATOR_PROMPT_ABC',
          isolated: true,
          read_only: false,
          max_concurrency: 3,
          args: ['--second', '--first'],
        },
        'rev-001'
      )
    })

    // Assert dialog closed and sensitive system prompt does not appear in targets table or document
    await vi.waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(screen.queryByText('SECRET_OPERATOR_PROMPT_ABC')).not.toBeInTheDocument()
  })

  it('opens target editor in edit mode with immutable identifier', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)
    vi.mocked(api.getConfigurationTarget).mockResolvedValue({
      revision: 'rev-001',
      target: mockTargets[0],
    })
    vi.mocked(api.updateConfigurationTarget).mockResolvedValue({
      revision: 'rev-002',
      target: { ...mockTargets[0], model: 'claude-3-5-sonnet' },
    })

    render(<Targets />)
    expect(await screen.findByText('target-healthy')).toBeInTheDocument()

    const healthyRow = screen.getByText('target-healthy').closest('tr')
    fireEvent.click(healthyRow)

    const editBtn = await screen.findByRole('button', { name: /Edit target/i })
    fireEvent.click(editBtn)

    const dialog = await screen.findByRole('dialog', { name: /Edit target: target-healthy/i })
    expect(dialog).toBeInTheDocument()

    const idInput = within(dialog).getByLabelText(/Identifier/i)
    expect(idInput).toBeDisabled()

    const modelInput = within(dialog).getByLabelText(/^Model$/i)
    fireEvent.change(modelInput, { target: { value: 'claude-3-5-sonnet' } })

    const saveBtn = within(dialog).getByRole('button', { name: /Save target/i })
    fireEvent.click(saveBtn)

    await vi.waitFor(() => {
      expect(api.updateConfigurationTarget).toHaveBeenCalledWith(
        'target-healthy',
        expect.objectContaining({
          id: 'target-healthy',
          model: 'claude-3-5-sonnet',
        }),
        'rev-001'
      )
    })
  })

  it('preserves dirty draft when background polling refreshes targets', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)
    vi.mocked(api.getConfigurationTargets).mockResolvedValue({ revision: 'rev-001', targets: [] })

    const { rerender } = render(<Targets />)
    expect(await screen.findByText('target-healthy')).toBeInTheDocument()

    const createBtn = screen.getByRole('button', { name: /^Create target$/i })
    fireEvent.click(createBtn)

    const dialog = await screen.findByRole('dialog', { name: /Create target/i })
    const modelInput = within(dialog).getByLabelText(/^Model$/i)
    fireEvent.change(modelInput, { target: { value: 'draft-model-value' } })
    expect(modelInput.value).toBe('draft-model-value')

    // Simulate background polling updating targets data
    vi.mocked(api.getTargets).mockResolvedValue([
      ...mockTargets,
      { id: 'new-polled-target', backend: 'pi', model: 'pi-1', isolated: false, read_only: false, max_concurrency: 1, active: 0, healthy: true, circuit_open_until: '' },
    ])
    rerender(<Targets />)

    // Draft value is retained
    expect(within(dialog).getByLabelText(/^Model$/i).value).toBe('draft-model-value')
  })

  it('handles configuration conflict by preserving draft and offering reload', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)
    vi.mocked(api.getConfigurationTargets).mockResolvedValue({ revision: 'rev-001', targets: [] })
    vi.mocked(api.createConfigurationTarget).mockRejectedValueOnce(
      new api.DashboardApiError('Conflict', 409, {
        code: 'configuration_conflict',
        unchanged: 'Source changed on server.',
        recovery: 'Reload current configuration and retry.',
        current: 'rev-conflict-999',
      })
    )

    render(<Targets />)
    expect(await screen.findByText('target-healthy')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^Create target$/i }))
    const dialog = await screen.findByRole('dialog', { name: /Create target/i })
    fireEvent.change(within(dialog).getByLabelText(/Identifier/i), { target: { value: 'conflict-t' } })
    fireEvent.change(within(dialog).getByLabelText(/^Model$/i), { target: { value: 'conflict-model' } })

    fireEvent.click(within(dialog).getByRole('button', { name: /^Create target$/i }))

    expect(await screen.findByText('Configuration conflict')).toBeInTheDocument()
    expect(screen.getByText('Source changed on server.')).toBeInTheDocument()
    expect(within(dialog).getByLabelText(/^Model$/i).value).toBe('conflict-model')

    const reloadBtn = screen.getByRole('button', { name: /Reload current configuration/i })
    fireEvent.click(reloadBtn)

    expect(screen.queryByText('Configuration conflict')).not.toBeInTheDocument()
    expect(within(dialog).getByLabelText(/^Model$/i).value).toBe('conflict-model')
  })

  it('handles deletion: unreferenced requires confirmation, referenced displays blocking references', async () => {
    vi.mocked(api.getTargets).mockResolvedValue(mockTargets)
    vi.mocked(api.getConfigurationTargets).mockResolvedValue({ revision: 'rev-001', targets: [] })

    // 1. Unreferenced deletion
    vi.mocked(api.deleteConfigurationTarget).mockResolvedValueOnce({
      deleted: 'target-down',
      revision: 'rev-002',
    })

    render(<Targets />)
    expect(await screen.findByText('target-down')).toBeInTheDocument()

    fireEvent.click(screen.getByText('target-down').closest('tr'))
    const deleteBtn = await screen.findByRole('button', { name: /Delete target/i })
    fireEvent.click(deleteBtn)

    expect(await screen.findByRole('dialog', { name: /Delete target: target-down/i })).toBeInTheDocument()

    const confirmBtn = screen.getByRole('button', { name: /Confirm delete/i })
    expect(confirmBtn).toBeDisabled()

    const checkbox = screen.getByLabelText(/I confirm deleting target target-down/i)
    fireEvent.click(checkbox)
    expect(confirmBtn).not.toBeDisabled()

    fireEvent.click(confirmBtn)

    await vi.waitFor(() => {
      expect(api.deleteConfigurationTarget).toHaveBeenCalledWith('target-down', 'rev-001')
    })
    await vi.waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    // 2. Referenced deletion
    vi.mocked(api.deleteConfigurationTarget).mockRejectedValue(
      new api.DashboardApiError('Target is referenced', 409, {
        code: 'referenced',
        references: [
          { scope: 'global', profile_id: 'balanced', workflow: 'implement' },
          { scope: 'project', project_id: 'proj-1', profile_id: 'custom', workflow: 'review' },
        ],
      })
    )

    fireEvent.click(screen.getByText('target-healthy').closest('tr'))
    const deleteBtn2 = await screen.findByRole('button', { name: /Delete target/i })
    fireEvent.click(deleteBtn2)

    expect(await screen.findByRole('dialog', { name: /Delete target: target-healthy/i })).toBeInTheDocument()
    const checkbox2 = screen.getByLabelText(/I confirm deleting target target-healthy/i)
    fireEvent.click(checkbox2)
    fireEvent.click(screen.getByRole('button', { name: /Confirm delete/i }))

    expect(await screen.findByRole('dialog', { name: /Blocking references for target target-healthy/i }, { timeout: 5000 })).toBeInTheDocument()
    expect(screen.getByText('Target is currently referenced')).toBeInTheDocument()
    expect(screen.getByText('balanced')).toBeInTheDocument()
    expect(screen.getByText('implement')).toBeInTheDocument()
    expect(screen.getByText('Project (proj-1)')).toBeInTheDocument()
    expect(screen.getByText('custom')).toBeInTheDocument()
  }, 15000)
})
