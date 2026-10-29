import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import ProfileEditor from './ProfileEditor'
import TargetEditor from './TargetEditor'

vi.mock('../api', async (importOriginal) => ({
  ...await importOriginal(),
  updateConfigurationTarget: vi.fn(),
  updateConfigurationProfile: vi.fn(),
}))

const workflows = ['custom-workflow']
const cases = [
  ['target', TargetEditor, 'updateConfigurationTarget', { target: { id: 'demo', backend: 'codex' } }],
  ['profile', ProfileEditor, 'updateConfigurationProfile', { profile: { id: 'demo' }, workflows }],
]

describe('editor control labels', () => {
  it('keeps arguments named without an unassociated collection label', () => {
    render(<TargetEditor isOpen mode="edit" revision="rev" target={{ id: 'demo', args: ['--flag'] }} />)
    expect(screen.getByRole('textbox', { name: 'Argument 1' })).toHaveValue('--flag')
    expect(screen.getByText('Command arguments').closest('label')).toBeNull()
  })

  it('keeps failover targets named without an unassociated collection label', () => {
    render(<ProfileEditor isOpen mode="edit" revision="rev" workflows={workflows} availableTargets={['worker']} profile={{
      id: 'demo', declared: { 'custom-workflow': { targets: ['worker'] } },
    }} />)
    expect(screen.getByRole('combobox', { name: 'custom-workflow target 1' })).toHaveValue('worker')
    expect(screen.getByText('Failover targets (evaluated in order)').closest('label')).toBeNull()
  })

  it('associates context capacity input with visible label and help description', () => {
    render(<TargetEditor isOpen mode="edit" revision="rev" target={{ id: 'demo' }} />)
    const input = screen.getByLabelText(/context.*capacity|context.*window/i)
    expect(input).toBeInTheDocument()
    expect(input).toHaveAttribute('type', 'number')
    expect(input).toHaveAttribute('min', '1')
    expect(input).toHaveAttribute('step', '1')
    const helpId = input.getAttribute('aria-describedby')
    expect(helpId).toBeTruthy()
    expect(document.getElementById(helpId)).toHaveTextContent(/blank to clear/i)
  })
})

describe.each(cases)('%s editor safety', (name, Editor, method, props) => {
  it('blocks every close path during save and retains a late conflict', async () => {
    let reject
    api[method].mockReturnValueOnce(new Promise((_, fail) => { reject = fail }))
    const onClose = vi.fn()
    const common = { ...props, isOpen: true, mode: 'edit', revision: 'original', onClose }
    const { rerender } = render(<Editor {...common} />)
    fireEvent.submit(screen.getByRole('dialog').querySelector('form'))
    expect(api[method]).toHaveBeenLastCalledWith('demo', expect.any(Object), 'original')

    // A background revision update must not replace an in-flight draft.
    rerender(<Editor {...common} revision="newer" />)
    fireEvent.keyDown(document, { key: 'Escape' })
    fireEvent.click(screen.getByTestId('modal-scrim'))
    fireEvent.click(screen.getByRole('button', { name: 'Close dialog' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    fireEvent.submit(screen.getByRole('dialog').querySelector('form'))
    expect(onClose).not.toHaveBeenCalled()
    expect(api[method]).toHaveBeenCalledTimes(1)

    await act(async () => reject(new api.DashboardApiError('Conflict', 409, { current: 'newer' })))
    expect(await screen.findByText(/configuration file changed on the server/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: new RegExp(`Save ${name}`, 'i') })).toBeDisabled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it.each(['Cancel', 'Close dialog', 'Escape', 'scrim'])('guards dirty close through %s', async (path) => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const onClose = vi.fn()
    render(<Editor {...props} isOpen revision="rev" onClose={onClose} />)
    const label = name === 'target' ? /Identifier/ : /Profile identifier/
    fireEvent.change(screen.getByLabelText(label), { target: { value: 'draft' } })
    if (path === 'Escape') fireEvent.keyDown(document, { key: 'Escape' })
    else if (path === 'scrim') fireEvent.click(screen.getByTestId('modal-scrim'))
    else fireEvent.click(screen.getByRole('button', { name: path }))
    expect(confirm).toHaveBeenCalledOnce()
    expect(onClose).not.toHaveBeenCalled()
    expect(screen.getByLabelText(label)).toHaveValue('draft')
    confirm.mockRestore()
  })

  it('blocks forced submission without a revision', async () => {
    const save = api[method]
    save.mockClear()
    render(<Editor {...props} isOpen mode="edit" revision="" />)
    expect(screen.getByRole('button', { name: new RegExp(`Save ${name}`, 'i') })).toBeDisabled()
    fireEvent.submit(screen.getByRole('dialog').querySelector('form'))
    await waitFor(() => expect(save).not.toHaveBeenCalled())
  })
})
