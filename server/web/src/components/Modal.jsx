import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  role = 'dialog',
  ariaLabel,
  ariaLabelledBy,
  initialFocusRef,
}) {
  const dialogRef = useRef(null)
  const previousActiveElementRef = useRef(null)

  useEffect(() => {
    if (!isOpen) return

    previousActiveElementRef.current = document.activeElement

    const timer = setTimeout(() => {
      if (initialFocusRef?.current) {
        initialFocusRef.current.focus()
      } else if (dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
        if (focusable.length > 0) {
          focusable[0].focus()
        } else {
          dialogRef.current.focus()
        }
      }
    }, 0)

    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        onClose?.()
        return
      }

      if (e.key === 'Tab' && dialogRef.current) {
        const focusables = Array.from(
          dialogRef.current.querySelectorAll(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
          )
        )
        if (focusables.length === 0) {
          e.preventDefault()
          return
        }

        const first = focusables[0]
        const last = focusables[focusables.length - 1]

        if (e.shiftKey) {
          if (document.activeElement === first || !dialogRef.current.contains(document.activeElement)) {
            e.preventDefault()
            last.focus()
          }
        } else {
          if (document.activeElement === last || !dialogRef.current.contains(document.activeElement)) {
            e.preventDefault()
            first.focus()
          }
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown)

    return () => {
      clearTimeout(timer)
      document.removeEventListener('keydown', handleKeyDown)
      if (previousActiveElementRef.current && typeof previousActiveElementRef.current.focus === 'function') {
        previousActiveElementRef.current.focus()
      }
    }
  }, [isOpen, onClose, initialFocusRef])

  if (!isOpen) return null

  const titleId = title ? 'modal-title' : undefined
  const labelledBy = ariaLabelledBy || (title ? titleId : undefined)

  function handleScrimClick(e) {
    if (e.target === e.currentTarget) {
      onClose?.()
    }
  }

  return createPortal(
    <div className="modal-scrim" onClick={handleScrimClick} data-testid="modal-scrim">
      <div
        ref={dialogRef}
        role={role}
        aria-modal="true"
        aria-label={ariaLabel}
        aria-labelledby={ariaLabel ? undefined : labelledBy}
        tabIndex={-1}
        className="modal-dialog"
      >
        <div className="modal-header">
          {title && <h2 id={titleId} className="modal-title">{title}</h2>}
          <button
            type="button"
            className="button button-ghost button-sm modal-close-btn"
            aria-label="Close dialog"
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        <div className="modal-body">
          {children}
        </div>
      </div>
    </div>,
    document.body
  )
}
