import { useEffect, useState, useRef } from 'react'
import {
  createConfigurationTarget,
  updateConfigurationTarget,
} from '../api'
import Alert from './Alert'
import Modal from './Modal'
import { useConfigEditor } from '../hooks/useConfigEditor'

export default function TargetEditor({
  isOpen,
  mode = 'create',
  target = null,
  revision = '',
  onClose,
  onSaved,
  onAnnounce,
  onReloadRequired,
}) {
  const initialForm = {
    id: '',
    backend: 'codex',
    model: '',
    backend_profile: '',
    reasoning: '',
    system_prompt: '',
    isolated: false,
    read_only: false,
    max_concurrency: 1,
    args: [],
  }

  const [formData, setFormData] = useState(initialForm)
  const {
    isDirtyRef, inFlightRef, currentRevision, setCurrentRevision,
    saveStatus, setSaveStatus, error, setError, conflictData, setConflictData,
    handleClose, submit, reload,
  } = useConfigEditor({ revision, onClose, onSaved, onAnnounce })
  const initialFocusRef = useRef(null)
  const prevIsOpenRef = useRef(false)

  // Initialize or update form only when not dirty or when opening
  useEffect(() => {
    if (!isOpen) {
      prevIsOpenRef.current = false
      isDirtyRef.current = false
      setSaveStatus('')
      setError(null)
      setConflictData(null)
      return
    }

    const wasOpen = prevIsOpenRef.current
    prevIsOpenRef.current = true

    // If form is already dirty and was already open, do NOT overwrite the draft from external props/polling
    if (wasOpen && (isDirtyRef.current || inFlightRef.current || conflictData)) {
      return
    }

    if (mode === 'edit' && target) {
      setFormData({
        id: target.id || '',
        backend: target.backend || 'codex',
        model: target.model || '',
        backend_profile: target.backend_profile || '',
        reasoning: target.reasoning || '',
        system_prompt: target.system_prompt || '',
        isolated: Boolean(target.isolated),
        read_only: Boolean(target.read_only),
        max_concurrency: target.max_concurrency || 1,
        args: Array.isArray(target.args) ? [...target.args] : [],
      })
    } else if (mode === 'create') {
      setFormData(initialForm)
    }
    setCurrentRevision(revision)
    isDirtyRef.current = false
    setSaveStatus('')
    setError(null)
    setConflictData(null)
  }, [isOpen, mode, target, revision])

  function handleFieldChange(field, value) {
    isDirtyRef.current = true
    setError(null)
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  function handleAddArg() {
    isDirtyRef.current = true
    setFormData((prev) => ({
      ...prev,
      args: [...prev.args, ''],
    }))
  }

  function handleArgChange(index, value) {
    isDirtyRef.current = true
    setFormData((prev) => {
      const newArgs = [...prev.args]
      newArgs[index] = value
      return { ...prev, args: newArgs }
    })
  }

  function handleMoveArg(index, direction) {
    isDirtyRef.current = true
    setFormData((prev) => {
      const newArgs = [...prev.args]
      const targetIndex = index + direction
      if (targetIndex < 0 || targetIndex >= newArgs.length) return prev
      const temp = newArgs[index]
      newArgs[index] = newArgs[targetIndex]
      newArgs[targetIndex] = temp
      return { ...prev, args: newArgs }
    })
  }

  function handleRemoveArg(index) {
    isDirtyRef.current = true
    setFormData((prev) => ({
      ...prev,
      args: prev.args.filter((_, i) => i !== index),
    }))
  }

  async function handleSubmit(e) {
    if (e) e.preventDefault()
    if (inFlightRef.current || conflictData || !currentRevision) return
    setError(null)
    setConflictData(null)
    const targetPayload = {
      id: formData.id.trim(),
      backend: formData.backend.trim(),
      model: formData.model.trim(),
      backend_profile: formData.backend_profile.trim(),
      reasoning: formData.reasoning.trim(),
      system_prompt: formData.system_prompt,
      isolated: formData.isolated,
      read_only: formData.read_only,
      max_concurrency: Number(formData.max_concurrency) || 1,
      args: formData.args,
    }

    return submit({
      entity: 'target',
      savingMessage: 'Saving configuration…',
      successMessage: (result) => `Target "${result.target?.id || formData.id}" saved and active.`,
      save: (revision) => mode === 'create'
        ? createConfigurationTarget(targetPayload, revision)
        : updateConfigurationTarget(formData.id, targetPayload, revision),
    })
  }

  function handleReloadConfiguration() {
    return reload({
      load: onReloadRequired,
      select: (payload) => payload?.target ||
        (mode === 'create' ? payload?.targets?.find((t) => t.id === formData.id) : null),
      apply: (item) => setFormData({
        id: item.id || '',
        backend: item.backend || 'codex',
        model: item.model || '',
        backend_profile: item.backend_profile || '',
        reasoning: item.reasoning || '',
        system_prompt: item.system_prompt || '',
        isolated: Boolean(item.isolated),
        read_only: Boolean(item.read_only),
        max_concurrency: item.max_concurrency || 1,
        args: Array.isArray(item.args) ? [...item.args] : [],
      }),
      mode,
      entity: 'Target',
    })
  }

  const isSubmitting = saveStatus === 'saving' || saveStatus === 'reloading'
  const title = mode === 'create' ? 'Create target' : `Edit target: ${target?.id || formData.id}`

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={title}
      role="dialog"
      ariaLabel={title}
      initialFocusRef={mode === 'create' ? initialFocusRef : undefined}
    >
      <form onSubmit={handleSubmit} className="target-editor-form">
        {saveStatus && (
          <div className="save-status-banner" role="status" aria-live="polite">
            {saveStatus === 'saving' && <span>Saving configuration…</span>}
            {saveStatus === 'reloading' && <span>Reloading runtime…</span>}
            {saveStatus === 'active' && <span>Saved and active.</span>}
          </div>
        )}

        {conflictData && (
          <div style={{ marginBottom: 'var(--space-md)' }}>
            <Alert tone="warning" title="Configuration conflict">
              <p>{conflictData.unchanged}</p>
              <p>{conflictData.recovery}</p>
              <div style={{ marginTop: 'var(--space-sm)' }}>
                <button
                  type="button"
                  className="button button-secondary button-sm"
                  onClick={handleReloadConfiguration}
                  disabled={isSubmitting}
                >
                  Reload current configuration
                </button>
              </div>
            </Alert>
          </div>
        )}

        {error && (
          <div style={{ marginBottom: 'var(--space-md)' }}>
            <Alert tone="error" title="Validation error">
              {error}
            </Alert>
          </div>
        )}

        <div className="form-group">
          <label htmlFor="target-id" className="form-label">
            Identifier <span className="caption">(required)</span>
          </label>
          <input
            id="target-id"
            ref={initialFocusRef}
            type="text"
            className="search-input"
            value={formData.id}
            onChange={(e) => handleFieldChange('id', e.target.value)}
            disabled={mode === 'edit' || isSubmitting}
            required
            placeholder="e.g. primary, codex-fast"
            aria-describedby={mode === 'edit' ? 'target-id-immutable' : undefined}
          />
          {mode === 'edit' && (
            <span id="target-id-immutable" className="caption">
              Target identifiers cannot be changed after creation.
            </span>
          )}
        </div>

        <div className="target-editor-grid">
          <div className="form-group">
            <label htmlFor="target-backend" className="form-label">
              Backend
            </label>
            <input
              id="target-backend"
              type="text"
              className="search-input"
              value={formData.backend}
              onChange={(e) => handleFieldChange('backend', e.target.value)}
              disabled={isSubmitting}
              required
              placeholder="e.g. codex, pi, custom"
            />
          </div>

          <div className="form-group">
            <label htmlFor="target-model" className="form-label">
              Model
            </label>
            <input
              id="target-model"
              type="text"
              className="search-input"
              value={formData.model}
              onChange={(e) => handleFieldChange('model', e.target.value)}
              disabled={isSubmitting}
              placeholder="e.g. gpt-4o, claude-3-7-sonnet"
            />
          </div>

          <div className="form-group">
            <label htmlFor="target-backend-profile" className="form-label">
              Backend profile
            </label>
            <input
              id="target-backend-profile"
              type="text"
              className="search-input"
              value={formData.backend_profile}
              onChange={(e) => handleFieldChange('backend_profile', e.target.value)}
              disabled={isSubmitting}
              placeholder="e.g. balanced, fast"
            />
          </div>

          <div className="form-group">
            <label htmlFor="target-reasoning" className="form-label">
              Reasoning effort
            </label>
            <input
              id="target-reasoning"
              type="text"
              className="search-input"
              value={formData.reasoning}
              onChange={(e) => handleFieldChange('reasoning', e.target.value)}
              disabled={isSubmitting}
              placeholder="e.g. none, low, medium, high, deep"
            />
          </div>

          <div className="form-group">
            <label htmlFor="target-max-concurrency" className="form-label">
              Max concurrency
            </label>
            <input
              id="target-max-concurrency"
              type="number"
              min="1"
              step="1"
              className="search-input"
              value={formData.max_concurrency}
              onChange={(e) => handleFieldChange('max_concurrency', e.target.value)}
              disabled={isSubmitting}
              required
            />
          </div>
        </div>

        <div className="target-editor-checkboxes">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={formData.isolated}
              onChange={(e) => handleFieldChange('isolated', e.target.checked)}
              disabled={isSubmitting}
            />
            <span>Process isolation (run job in isolated environment)</span>
          </label>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={formData.read_only}
              onChange={(e) => handleFieldChange('read_only', e.target.checked)}
              disabled={isSubmitting}
            />
            <span>Read-only access (prevent modification to workspace)</span>
          </label>
        </div>

        <div className="form-group">
          <label htmlFor="target-system-prompt" className="form-label">
            System prompt
          </label>
          <textarea
            id="target-system-prompt"
            className="form-textarea"
            rows="3"
            value={formData.system_prompt}
            onChange={(e) => handleFieldChange('system_prompt', e.target.value)}
            disabled={isSubmitting}
            placeholder="Custom instructions or system prompt for this target"
          />
        </div>

        <div className="form-group">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span className="form-label">Command arguments</span>
            <button
              type="button"
              className="button button-ghost button-sm"
              onClick={handleAddArg}
              disabled={isSubmitting}
            >
              Add argument
            </button>
          </div>

          {formData.args.length === 0 ? (
            <span className="caption" style={{ fontStyle: 'italic', padding: 'var(--space-xs) 0' }}>
              No custom arguments configured.
            </span>
          ) : (
            <div className="target-args-list">
              {formData.args.map((arg, idx) => (
                <div key={idx} className="target-arg-row">
                  <input
                    type="text"
                    className="search-input target-arg-input"
                    value={arg}
                    onChange={(e) => handleArgChange(idx, e.target.value)}
                    disabled={isSubmitting}
                    aria-label={`Argument ${idx + 1}`}
                    placeholder={`--flag or value`}
                  />
                  <div className="target-arg-actions">
                    <button
                      type="button"
                      className="button button-ghost button-sm"
                      onClick={() => handleMoveArg(idx, -1)}
                      disabled={idx === 0 || isSubmitting}
                      aria-label={`Move argument ${idx + 1} up`}
                      title="Move up"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="button button-ghost button-sm"
                      onClick={() => handleMoveArg(idx, 1)}
                      disabled={idx === formData.args.length - 1 || isSubmitting}
                      aria-label={`Move argument ${idx + 1} down`}
                      title="Move down"
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className="button button-ghost button-sm"
                      onClick={() => handleRemoveArg(idx)}
                      disabled={isSubmitting}
                      aria-label={`Remove argument ${idx + 1}`}
                      title="Remove"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="modal-actions">
          <button
            type="button"
            className="button button-secondary"
            onClick={handleClose}
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <div className="modal-actions-right">
            <button
              type="submit"
              className="button button-primary"
              disabled={isSubmitting || Boolean(conflictData) || !currentRevision || !formData.id.trim()}
            >
              {isSubmitting ? (saveStatus === 'reloading' ? 'Reloading…' : 'Saving…') : mode === 'create' ? 'Create target' : 'Save target'}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  )
}
