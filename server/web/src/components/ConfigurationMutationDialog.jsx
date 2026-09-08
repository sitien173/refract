import { useState, useEffect } from 'react'
import Alert from './Alert'
import Modal from './Modal'

export default function ConfigurationMutationDialog({
  isOpen,
  title,
  targetId = '',
  references = null,
  error = null,
  isSubmitting = false,
  onClose,
  onConfirm,
}) {
  const [isConfirmed, setIsConfirmed] = useState(false)

  useEffect(() => {
    if (!isOpen) {
      setIsConfirmed(false)
    }
  }, [isOpen])

  const hasReferences = Array.isArray(references) && references.length > 0
  const defaultTitle = targetId ? `Delete target: ${targetId}` : 'Confirm deletion'
  const dialogTitle = hasReferences ? `Cannot delete target: ${targetId}` : (title || defaultTitle)
  const ariaLabel = hasReferences ? `Blocking references for target ${targetId}` : dialogTitle

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={dialogTitle}
      role="dialog"
      ariaLabel={ariaLabel}
    >
      {hasReferences ? (
        <div className="mutation-dialog-referenced">
          <Alert tone="warning" title="Target is currently referenced">
            Target <strong>{targetId}</strong> cannot be deleted because it is referenced by the following profile workflows:
          </Alert>

          <div className="mutation-references-list" style={{ marginTop: 'var(--space-md)' }}>
            <div className="data-grid-container" tabIndex={0} role="region" aria-label="Referencing profile workflows">
              <table className="data-grid-table data-table" style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th scope="col">Scope</th>
                    <th scope="col">Profile</th>
                    <th scope="col">Workflow</th>
                  </tr>
                </thead>
                <tbody>
                  {references.map((ref, idx) => (
                    <tr key={idx}>
                      <td>
                        <span className={`source-chip ${ref.scope === 'project' ? 'source-repository' : 'source-global'}`}>
                          {ref.scope === 'project' ? (ref.project_id ? `Project (${ref.project_id})` : 'Project') : 'Global'}
                        </span>
                      </td>
                      <td>
                        <strong>{ref.profile_id || '(daemon default)'}</strong>
                      </td>
                      <td>
                        <code>{ref.workflow || ref.relationship || 'reference'}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <p className="caption" style={{ marginTop: 'var(--space-md)' }}>
            Update or remove these workflow references in the configuration before deleting this target.
          </p>

          <div className="modal-actions" style={{ justifyContent: 'flex-end', marginTop: 'var(--space-lg)' }}>
            <button
              type="button"
              className="button button-secondary"
              onClick={onClose}
            >
              Close
            </button>
          </div>
        </div>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (isConfirmed && !isSubmitting) {
              onConfirm?.()
            }
          }}
          className="mutation-dialog-confirm"
        >
          {error && (
            <div style={{ marginBottom: 'var(--space-md)' }}>
              <Alert tone="error" title="Action failed">
                {typeof error === 'string' ? error : error.message || 'Operation failed'}
              </Alert>
            </div>
          )}

          <p style={{ margin: '0 0 var(--space-md) 0' }}>
            Are you sure you want to delete target <strong>{targetId}</strong>? This action modifies the active configuration file.
          </p>

          <div className="confirmation-group" style={{ marginBottom: 'var(--space-md)' }}>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={isConfirmed}
                onChange={(e) => setIsConfirmed(e.target.checked)}
                disabled={isSubmitting}
                aria-label={`I confirm deleting target ${targetId}`}
              />
              <span>I confirm deleting target <strong>{targetId}</strong>.</span>
            </label>
          </div>

          <div className="modal-actions">
            <button
              type="button"
              className="button button-secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <div className="modal-actions-right">
              <button
                type="submit"
                className="button button-destructive-outline"
                disabled={!isConfirmed || isSubmitting}
              >
                {isSubmitting ? 'Deleting…' : 'Confirm delete'}
              </button>
            </div>
          </div>
        </form>
      )}
    </Modal>
  )
}
