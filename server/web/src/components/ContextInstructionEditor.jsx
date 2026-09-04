import { useEffect, useRef, useState } from 'react'
import { DashboardApiError, deleteContextInstruction, updateContextInstruction } from '../api'
import Alert from './Alert'
import Modal from './Modal'

export default function ContextInstructionEditor({
  projectId,
  workflow,
  currentInstruction = '',
  isOpen,
  mode = 'edit',
  onClose,
  onSaved,
  onAnnounce,
}) {
  const [draft, setDraft] = useState(currentInstruction)
  const [expectedCurrent, setExpectedCurrent] = useState(currentInstruction)
  const [isConfirmed, setIsConfirmed] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [conflictData, setConflictData] = useState(null)
  const [activeMode, setActiveMode] = useState(mode)
  const textareaRef = useRef(null)

  useEffect(() => {
    if (isOpen) {
      setDraft(currentInstruction)
      setExpectedCurrent(currentInstruction)
      setIsConfirmed(false)
      setError(null)
      setConflictData(null)
      setActiveMode(mode)
    }
  }, [isOpen, currentInstruction, mode])

  async function handleSave(e) {
    if (e) e.preventDefault()
    if (!isConfirmed) {
      setError({ message: 'Explicit confirmation is required: changes affect future jobs only.' })
      return
    }

    setIsSubmitting(true)
    setError(null)
    setConflictData(null)

    try {
      const result = await updateContextInstruction(projectId, workflow, draft, expectedCurrent)
      if (onAnnounce) {
        onAnnounce(`Context instruction for ${workflow} updated. Affects future jobs only.`)
      }
      onSaved?.({ workflow, instruction: result.instruction ?? draft })
      onClose?.()
    } catch (err) {
      if (err instanceof DashboardApiError && err.status === 409) {
        const payload = err.payload || {}
        setConflictData({
          unchanged: payload.unchanged || 'The newer context instruction remains unchanged.',
          recovery: payload.recovery || 'Refresh the current instruction and retry.',
          current: payload.current ?? '',
        })
        if (payload.current !== undefined) {
          setExpectedCurrent(payload.current)
        }
        setIsConfirmed(false)
        if (onAnnounce) {
          onAnnounce('Conflict detected: the context instruction changed on the server.')
        }
      } else {
        setError({ message: err.message || 'Failed to update context instruction.' })
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleClear(e) {
    if (e) e.preventDefault()
    if (!isConfirmed) {
      setError({ message: 'Explicit confirmation is required: clearing affects future jobs only.' })
      return
    }

    setIsSubmitting(true)
    setError(null)
    setConflictData(null)

    try {
      await deleteContextInstruction(projectId, workflow, expectedCurrent)
      if (onAnnounce) {
        onAnnounce(`Context instruction for ${workflow} cleared. Affects future jobs only.`)
      }
      onSaved?.({ workflow, instruction: '' })
      onClose?.()
    } catch (err) {
      if (err instanceof DashboardApiError && err.status === 409) {
        const payload = err.payload || {}
        setConflictData({
          unchanged: payload.unchanged || 'The newer context instruction remains unchanged.',
          recovery: payload.recovery || 'Refresh the current instruction and retry.',
          current: payload.current ?? '',
        })
        if (payload.current !== undefined) {
          setExpectedCurrent(payload.current)
        }
        setIsConfirmed(false)
        if (onAnnounce) {
          onAnnounce('Conflict detected: the context instruction changed on the server.')
        }
      } else {
        setError({ message: err.message || 'Failed to clear context instruction.' })
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const isClearMode = activeMode === 'clear'
  const modalTitle = isClearMode
    ? `Clear context instruction: ${workflow}`
    : mode === 'add'
    ? `Add context instruction: ${workflow}`
    : `Edit context instruction: ${workflow}`

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={modalTitle}
      initialFocusRef={isClearMode ? undefined : textareaRef}
    >
      <div className="context-instruction-editor">
        {conflictData && (
          <Alert tone="warning" title="Context instruction conflict" role="alert">
            <p className="conflict-unchanged">{conflictData.unchanged}</p>
            <p className="conflict-recovery">{conflictData.recovery}</p>
            <div className="conflict-current-preview">
              <span className="caption">Current server value:</span>
              <code className="cell-code block-code">{conflictData.current || '(empty)'}</code>
            </div>
            <p className="caption">
              Your draft has been preserved. Confirm and retry to overwrite with your draft.
            </p>
          </Alert>
        )}

        {error && (
          <Alert tone="error" title="Action failed" role="alert">
            <p>{error.message}</p>
          </Alert>
        )}

        {isClearMode ? (
          <div className="clear-confirm-dialog">
            <p>
              Are you sure you want to clear the context instruction for <strong>{workflow}</strong>?
            </p>
            <p className="caption future-jobs-notice">
              Configuration changes affect newly submitted jobs only. Existing and queued jobs remain unchanged.
            </p>

            <div className="confirmation-group">
              <label className="checkbox-label" htmlFor="confirm-clear-checkbox">
                <input
                  type="checkbox"
                  id="confirm-clear-checkbox"
                  checked={isConfirmed}
                  onChange={(e) => setIsConfirmed(e.target.checked)}
                />
                <span>I confirm this clear action affects future jobs only</span>
              </label>
            </div>

            <div className="modal-actions">
              <button
                type="button"
                className="button button-secondary"
                onClick={() => {
                  if (mode === 'clear') {
                    onClose()
                  } else {
                    setActiveMode('edit')
                    setIsConfirmed(false)
                    setError(null)
                  }
                }}
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="button button-destructive-outline"
                onClick={handleClear}
                disabled={!isConfirmed || isSubmitting}
              >
                {isSubmitting ? 'Clearing…' : 'Confirm clear'}
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSave} className="editor-form">
            <div className="form-group">
              <label htmlFor="context-instruction-text" className="form-label">
                Instruction content
              </label>
              <textarea
                id="context-instruction-text"
                ref={textareaRef}
                className="form-textarea"
                rows={6}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Enter persistent instructions for agents running this workflow…"
                disabled={isSubmitting}
                required
              />
            </div>

            <p className="caption future-jobs-notice">
              Configuration changes affect newly submitted jobs only. Existing and queued jobs remain unchanged.
            </p>

            <div className="confirmation-group">
              <label className="checkbox-label" htmlFor="confirm-edit-checkbox">
                <input
                  type="checkbox"
                  id="confirm-edit-checkbox"
                  checked={isConfirmed}
                  onChange={(e) => setIsConfirmed(e.target.checked)}
                />
                <span>I confirm this change applies only to future jobs</span>
              </label>
            </div>

            <div className="modal-actions">
              {currentInstruction && (
                <button
                  type="button"
                  className="button button-destructive-outline clear-switch-btn"
                  onClick={() => {
                    setActiveMode('clear')
                    setIsConfirmed(false)
                    setError(null)
                  }}
                  disabled={isSubmitting}
                >
                  Clear instruction…
                </button>
              )}
              <div className="modal-actions-right">
                <button
                  type="button"
                  className="button button-secondary"
                  onClick={onClose}
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="button button-primary"
                  disabled={!isConfirmed || isSubmitting}
                >
                  {isSubmitting ? 'Saving…' : conflictData ? 'Retry save' : 'Save instruction'}
                </button>
              </div>
            </div>
          </form>
        )}
      </div>
    </Modal>
  )
}
