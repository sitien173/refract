import { useState, useEffect } from 'react'
import Alert from './Alert'
import Modal from './Modal'

function referenceWorkflow(ref) {
  if (ref.relationship === 'default_profile') return 'Default profile'
  if (ref.relationship === 'extends') return 'Parent profile (extends)'
  return ref.workflow || ref.relationship || 'reference'
}

function referenceScope(ref) {
  if (ref.scope !== 'project') return 'Global'
  return ref.project_id ? `Project (${ref.project_id})` : 'Project'
}

function confirmationLabel(action, isSubmitting) {
  if (action === 'remove') return isSubmitting ? 'Removing override…' : 'Remove override'
  return isSubmitting ? 'Deleting…' : 'Confirm delete'
}

export default function ConfigurationMutationDialog({
  isOpen,
  title,
  targetId = '',
  entity = 'target',
  action = 'delete',
  children,
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
  const entityTitle = entity[0].toUpperCase() + entity.slice(1)
  const defaultTitle = targetId ? `Delete ${entity}: ${targetId}` : 'Confirm deletion'
  const dialogTitle = hasReferences ? `Cannot delete ${entity}: ${targetId}` : (title || defaultTitle)
  const ariaLabel = hasReferences ? `Blocking references for ${entity} ${targetId}` : dialogTitle
  const confirmation = action === 'remove' ? `removing override for profile ${targetId}` : `deleting ${entity} ${targetId}`

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      closeDisabled={isSubmitting}
      title={dialogTitle}
      role="dialog"
      ariaLabel={ariaLabel}
    >
      {hasReferences ? (
        <div className="mutation-dialog-referenced">
          <Alert tone="warning" title={`${entityTitle} is currently referenced`}>
            {entityTitle} <strong>{targetId}</strong> cannot be deleted because it is referenced by:
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
                          {referenceScope(ref)}
                        </span>
                      </td>
                      <td>
                        <strong>{ref.profile_id || '(daemon default)'}</strong>
                      </td>
                      <td>
                        <code>{referenceWorkflow(ref)}</code>
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
            Are you sure you want to {action} {entity} <strong>{targetId}</strong>? This action modifies the active configuration file.
          </p>

          {children}

          <div className="confirmation-group" style={{ marginBottom: 'var(--space-md)' }}>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={isConfirmed}
                onChange={(e) => setIsConfirmed(e.target.checked)}
                disabled={isSubmitting}
                aria-label={`I confirm ${confirmation}`}
              />
              <span>I confirm {confirmation}.</span>
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
                {confirmationLabel(action, isSubmitting)}
              </button>
            </div>
          </div>
        </form>
      )}
    </Modal>
  )
}
