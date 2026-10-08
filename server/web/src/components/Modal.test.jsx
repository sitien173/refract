import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useRef, useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import Modal from './Modal'

function ModalWithInitialFocus({ isOpen, onClose }) {
  const customRef = useRef(null)
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Custom Focus Modal" initialFocusRef={customRef}>
      <input data-testid="first-input" />
      <button ref={customRef} data-testid="target-button">
        Target Action
      </button>
      <button data-testid="last-button">Last Action</button>
    </Modal>
  )
}

function ModalDefaultFocus({ isOpen, onClose }) {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Default Focus Modal">
      <input data-testid="first-input" />
      <button data-testid="last-button">Last Action</button>
    </Modal>
  )
}

describe('Modal component', () => {
  it('focuses element provided by initialFocusRef upon opening', async () => {
    render(<ModalWithInitialFocus isOpen={true} onClose={vi.fn()} />)
    const target = screen.getByTestId('target-button')
    await waitFor(() => {
      expect(document.activeElement).toBe(target)
    })
  })

  it('focuses the first focusable element by default when no initialFocusRef is provided', async () => {
    render(<ModalDefaultFocus isOpen={true} onClose={vi.fn()} />)
    const closeBtn = screen.getByRole('button', { name: /Close dialog/i })
    await waitFor(() => {
      expect(document.activeElement).toBe(closeBtn)
    })
  })

  it('traps focus forward and in reverse within dialog bounds', async () => {
    render(<ModalDefaultFocus isOpen={true} onClose={vi.fn()} />)
    const closeBtn = screen.getByRole('button', { name: /Close dialog/i })
    const lastBtn = screen.getByTestId('last-button')

    // Forward Tab from last element wraps to first element
    lastBtn.focus()
    expect(document.activeElement).toBe(lastBtn)
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: false })
    expect(document.activeElement).toBe(closeBtn)

    // Reverse Tab from first element wraps to last element
    closeBtn.focus()
    expect(document.activeElement).toBe(closeBtn)
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(lastBtn)
  })

  it('restores focus to previously active element on close', async () => {
    function Host() {
      const [isOpen, setIsOpen] = useState(false)
      return (
        <div>
          <button type="button" data-testid="open-modal-btn" onClick={() => setIsOpen(true)}>
            Open
          </button>
          <Modal isOpen={isOpen} onClose={() => setIsOpen(false)} title="Restoration Modal">
            <button data-testid="inside-btn">Inside</button>
          </Modal>
        </div>
      )
    }

    render(<Host />)
    const openBtn = screen.getByTestId('open-modal-btn')
    openBtn.focus()
    expect(document.activeElement).toBe(openBtn)

    fireEvent.click(openBtn)
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    // Dismiss with Escape
    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    expect(document.activeElement).toBe(openBtn)
  })
})
