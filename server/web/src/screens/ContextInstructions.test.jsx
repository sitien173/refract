import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import ContextInstructions from './ContextInstructions'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    getProjects: vi.fn(),
    getContextInstructions: vi.fn(),
    updateContextInstruction: vi.fn(),
    deleteContextInstruction: vi.fn(),
  }
})

describe('ContextInstructions screen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(api.getProjects).mockResolvedValue([
      { id: 'proj-1', alias: 'Primary Project', root: '/path/1' },
      { id: 'proj-2', alias: 'Secondary Project', root: '/path/2' },
    ])
  })

  it('renders default workflows and merges custom workflow keys from nested instruction envelope', async () => {
    vi.mocked(api.getContextInstructions).mockResolvedValue({
      project_id: 'proj-1',
      instructions: {
        consult: 'Custom consult guidance',
        custom_analysis: 'Run deep scan',
      },
    })

    render(<ContextInstructions projectId="proj-1" />)

    expect(await screen.findByText('consult')).toBeInTheDocument()
    expect(screen.getByText('implement')).toBeInTheDocument()
    expect(screen.getByText('other')).toBeInTheDocument()
    expect(screen.getByText('review')).toBeInTheDocument()
    expect(screen.getByText('custom_analysis')).toBeInTheDocument()

    expect(screen.getByText('Custom consult guidance')).toBeInTheDocument()
    expect(screen.getByText('Run deep scan')).toBeInTheDocument()
  })

  it('requires explicit confirmation before saving an instruction mutation', async () => {
    vi.mocked(api.getContextInstructions).mockResolvedValue({
      project_id: 'proj-1',
      instructions: {
        implement: 'Existing instruction',
      },
    })
    vi.mocked(api.updateContextInstruction).mockResolvedValue({
      project_id: 'proj-1',
      workflow: 'implement',
      instruction: 'Updated instruction',
    })

    render(<ContextInstructions projectId="proj-1" />)

    const editButton = await screen.findByRole('button', { name: /Edit implement context instruction/i })
    fireEvent.click(editButton)

    expect(screen.getByRole('dialog', { name: /Edit context instruction: implement/i })).toBeInTheDocument()

    const textarea = screen.getByLabelText(/Instruction content/i)
    fireEvent.change(textarea, { target: { value: 'Updated instruction' } })

    const saveButton = screen.getByRole('button', { name: /Save instruction/i })
    expect(saveButton).toBeDisabled()

    const confirmCheckbox = screen.getByLabelText(/I confirm this change applies only to future jobs/i)
    fireEvent.click(confirmCheckbox)
    expect(saveButton).not.toBeDisabled()

    fireEvent.click(saveButton)

    await waitFor(() => {
      expect(api.updateContextInstruction).toHaveBeenCalledWith(
        'proj-1',
        'implement',
        'Updated instruction',
        'Existing instruction'
      )
    })

    expect(await screen.findByText('Updated instruction')).toBeInTheDocument()
    // Polite live region announcement
    expect(screen.getByText(/Context instruction for implement updated/i)).toBeInTheDocument()
  })

  it('performs DELETE clear with expected_current and outlined destructive styling', async () => {
    vi.mocked(api.getContextInstructions).mockResolvedValue({
      project_id: 'proj-1',
      instructions: {
        review: 'Strict review policy',
      },
    })
    vi.mocked(api.deleteContextInstruction).mockResolvedValue({
      project_id: 'proj-1',
      workflow: 'review',
      instruction: '',
    })

    render(<ContextInstructions projectId="proj-1" />)

    const clearButton = await screen.findByRole('button', { name: /Clear review context instruction/i })
    expect(clearButton).toHaveClass('button-destructive-outline')
    fireEvent.click(clearButton)

    expect(screen.getByRole('dialog', { name: /Clear context instruction: review/i })).toBeInTheDocument()

    const confirmClearBtn = screen.getByRole('button', { name: /Confirm clear/i })
    expect(confirmClearBtn).toBeDisabled()

    const confirmCheckbox = screen.getByLabelText(/I confirm this clear action affects future jobs only/i)
    fireEvent.click(confirmCheckbox)
    expect(confirmClearBtn).not.toBeDisabled()

    fireEvent.click(confirmClearBtn)

    await waitFor(() => {
      expect(api.deleteContextInstruction).toHaveBeenCalledWith('proj-1', 'review', 'Strict review policy')
    })

    // Dialog closed and live region announced
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText(/Context instruction for review cleared/i)).toBeInTheDocument()
  })

  it('handles 409 conflict by preserving draft and allowing retry with current server value', async () => {
    vi.mocked(api.getContextInstructions).mockResolvedValue({
      project_id: 'proj-1',
      instructions: {
        consult: 'Old server version',
      },
    })

    const conflictError = new api.DashboardApiError('Context instruction changed', 409, {
      code: 'context_conflict',
      unchanged: 'The newer context instruction remains unchanged.',
      recovery: 'Refresh the current instruction and retry.',
      current: 'Concurrent update by another user',
    })

    vi.mocked(api.updateContextInstruction)
      .mockRejectedValueOnce(conflictError)
      .mockResolvedValueOnce({
        project_id: 'proj-1',
        workflow: 'consult',
        instruction: 'My local draft',
      })

    render(<ContextInstructions projectId="proj-1" />)

    const editBtn = await screen.findByRole('button', { name: /Edit consult context instruction/i })
    fireEvent.click(editBtn)

    const textarea = screen.getByLabelText(/Instruction content/i)
    fireEvent.change(textarea, { target: { value: 'My local draft' } })

    const confirmCheckbox = screen.getByLabelText(/I confirm this change applies only to future jobs/i)
    fireEvent.click(confirmCheckbox)

    const saveBtn = screen.getByRole('button', { name: /Save instruction/i })
    fireEvent.click(saveBtn)

    // Conflict alert appears
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByText('The newer context instruction remains unchanged.')).toBeInTheDocument()
    expect(screen.getByText('Concurrent update by another user')).toBeInTheDocument()

    // Draft is preserved in textarea
    expect(textarea.value).toBe('My local draft')

    // Retry save
    const retryBtn = screen.getByRole('button', { name: /Retry save/i })
    fireEvent.click(confirmCheckbox)
    fireEvent.click(retryBtn)

    await waitFor(() => {
      expect(api.updateContextInstruction).toHaveBeenLastCalledWith(
        'proj-1',
        'consult',
        'My local draft',
        'Concurrent update by another user'
      )
    })
  })

  it('manages modal initial focus, forward and reverse tab trapping, and focus restoration', async () => {
    vi.mocked(api.getContextInstructions).mockResolvedValue({
      project_id: 'proj-1',
      instructions: {},
    })

    render(
      <div>
        <button type="button" id="outer-button">
          Outer focusable
        </button>
        <ContextInstructions projectId="proj-1" />
      </div>
    )

    const addBtn = await screen.findByRole('button', { name: /Add instruction for consult/i })
    addBtn.focus()
    expect(document.activeElement).toBe(addBtn)

    fireEvent.click(addBtn)

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toBeInTheDocument()

    // 1. Initial focus moves to the editor textarea via initialFocusRef
    const textarea = screen.getByLabelText(/Instruction content/i)
    await waitFor(() => {
      expect(document.activeElement).toBe(textarea)
    })

    // Enable the save button so it is the last focusable element in the dialog
    const confirmCheckbox = screen.getByLabelText(/I confirm this change applies only to future jobs/i)
    fireEvent.click(confirmCheckbox)

    const closeBtn = screen.getByRole('button', { name: /Close dialog/i })
    const saveBtn = screen.getByRole('button', { name: /Save instruction/i })
    expect(saveBtn).not.toBeDisabled()

    // 2. Forward Tab trapping: Tab from last focusable wraps to first focusable
    saveBtn.focus()
    expect(document.activeElement).toBe(saveBtn)
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: false })
    expect(document.activeElement).toBe(closeBtn)

    // 3. Reverse Tab trapping: Shift+Tab from first focusable wraps to last focusable
    closeBtn.focus()
    expect(document.activeElement).toBe(closeBtn)
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(saveBtn)

    // 4. Focus restoration: Dismissing via Escape restores focus to the invoking button
    fireEvent.keyDown(document, { key: 'Escape' })

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(document.activeElement).toBe(addBtn)
  })
})
