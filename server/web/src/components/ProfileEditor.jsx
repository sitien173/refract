import { useEffect, useRef, useState } from 'react'
import {
  createConfigurationProfile,
  updateConfigurationProfile,
  createProjectProfileOverride,
  updateProjectProfileOverride,
  DashboardApiError,
} from '../api'
import Alert from './Alert'
import Modal from './Modal'

const BUILTIN_WORKFLOWS = ['consult', 'implement', 'review', 'other']

export default function ProfileEditor({
  isOpen,
  mode = 'create',
  scope = 'global',
  projectId = '',
  profile = null,
  revision = '',
  availableTargets = [],
  availableProfiles = [],
  onClose,
  onSaved,
  onAnnounce,
  onReloadRequired,
}) {
  const isDirtyRef = useRef(false)
  const [isDirty, setIsDirty] = useState(false)
  const [formData, setFormData] = useState(() => getInitialFormData(profile, availableTargets))
  const [currentRevision, setCurrentRevision] = useState(revision)
  const [saveStatus, setSaveStatus] = useState('')
  const [error, setError] = useState(null)
  const [validationErrors, setValidationErrors] = useState({})
  const [conflictData, setConflictData] = useState(null)

  function getInitialFormData(prof, targetsList) {
    const defaultTarget = targetsList && targetsList.length > 0 ? targetsList[0] : ''
    const workflowsState = {}

    BUILTIN_WORKFLOWS.forEach((wf) => {
      const declaredWf = prof?.declared?.[wf] || prof?.workflows?.[wf]
      if (declaredWf && Array.isArray(declaredWf.targets) && declaredWf.targets.length > 0) {
        workflowsState[wf] = {
          declared: true,
          targets: [...declaredWf.targets],
          max_attempts: declaredWf.max_attempts ?? Math.max(1, declaredWf.targets.length),
          timeout_s: declaredWf.timeout_s ?? 0,
        }
      } else {
        const inheritedWf = prof?.inherited?.[wf]
        workflowsState[wf] = {
          declared: false,
          targets: inheritedWf?.targets ? [...inheritedWf.targets] : (defaultTarget ? [defaultTarget] : []),
          max_attempts: inheritedWf?.max_attempts ?? 1,
          timeout_s: inheritedWf?.timeout_s ?? 0,
        }
      }
    })

    return {
      id: prof?.id || '',
      extends: prof?.extends || '',
      workflows: workflowsState,
    }
  }

  useEffect(() => {
    if (!isOpen) {
      isDirtyRef.current = false
      setIsDirty(false)
      setError(null)
      setValidationErrors({})
      setConflictData(null)
      setSaveStatus('')
      return
    }

    setCurrentRevision(revision)

    if (!isDirtyRef.current) {
      setFormData(getInitialFormData(profile, availableTargets))
      setError(null)
      setValidationErrors({})
      setConflictData(null)
      setSaveStatus('')
    }
  }, [isOpen, mode, profile, revision, availableTargets])

  function handleFieldChange(field, value) {
    isDirtyRef.current = true
    setIsDirty(true)
    setError(null)
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  function handleWorkflowToggle(wf, declared) {
    isDirtyRef.current = true
    setIsDirty(true)
    setError(null)
    setValidationErrors((prev) => {
      const next = { ...prev }
      delete next[wf]
      return next
    })

    setFormData((prev) => {
      const currentWf = prev.workflows[wf] || {}
      const fallbackTarget = availableTargets.length > 0 ? availableTargets[0] : ''
      const targets = currentWf.targets && currentWf.targets.length > 0
        ? currentWf.targets
        : (fallbackTarget ? [fallbackTarget] : [])
      return {
        ...prev,
        workflows: {
          ...prev.workflows,
          [wf]: {
            ...currentWf,
            declared,
            targets,
            max_attempts: currentWf.max_attempts || Math.max(1, targets.length),
            timeout_s: currentWf.timeout_s ?? 0,
          },
        },
      }
    })
  }

  function handleAddTarget(wf) {
    isDirtyRef.current = true
    setIsDirty(true)
    setError(null)
    setValidationErrors((prev) => {
      const next = { ...prev }
      delete next[wf]
      return next
    })

    const newTarget = availableTargets.length > 0 ? availableTargets[0] : ''
    setFormData((prev) => {
      const currentWf = prev.workflows[wf]
      return {
        ...prev,
        workflows: {
          ...prev.workflows,
          [wf]: {
            ...currentWf,
            targets: [...currentWf.targets, newTarget],
          },
        },
      }
    })
  }

  function handleTargetChange(wf, index, value) {
    isDirtyRef.current = true
    setIsDirty(true)
    setError(null)
    setValidationErrors((prev) => {
      const next = { ...prev }
      delete next[wf]
      return next
    })

    setFormData((prev) => {
      const currentWf = prev.workflows[wf]
      const newTargets = [...currentWf.targets]
      newTargets[index] = value
      return {
        ...prev,
        workflows: {
          ...prev.workflows,
          [wf]: {
            ...currentWf,
            targets: newTargets,
          },
        },
      }
    })
  }

  function handleMoveTarget(wf, index, direction) {
    isDirtyRef.current = true
    setIsDirty(true)
    setError(null)

    setFormData((prev) => {
      const currentWf = prev.workflows[wf]
      const newTargets = [...currentWf.targets]
      const targetIndex = index + direction
      if (targetIndex < 0 || targetIndex >= newTargets.length) return prev
      const temp = newTargets[index]
      newTargets[index] = newTargets[targetIndex]
      newTargets[targetIndex] = temp
      return {
        ...prev,
        workflows: {
          ...prev.workflows,
          [wf]: {
            ...currentWf,
            targets: newTargets,
          },
        },
      }
    })
  }

  function handleRemoveTarget(wf, index) {
    isDirtyRef.current = true
    setIsDirty(true)
    setError(null)

    setFormData((prev) => {
      const currentWf = prev.workflows[wf]
      return {
        ...prev,
        workflows: {
          ...prev.workflows,
          [wf]: {
            ...currentWf,
            targets: currentWf.targets.filter((_, i) => i !== index),
          },
        },
      }
    })
  }

  function handlePolicyFieldChange(wf, field, value) {
    isDirtyRef.current = true
    setIsDirty(true)
    setError(null)

    setFormData((prev) => {
      const currentWf = prev.workflows[wf]
      return {
        ...prev,
        workflows: {
          ...prev.workflows,
          [wf]: {
            ...currentWf,
            [field]: value,
          },
        },
      }
    })
  }

  async function handleSubmit(e) {
    if (e) e.preventDefault()
    setError(null)
    setValidationErrors({})
    setConflictData(null)

    // Form validation
    const profileId = formData.id.trim()
    if (!profileId) {
      setError('Profile identifier is required.')
      return
    }

    const errors = {}
    BUILTIN_WORKFLOWS.forEach((wf) => {
      const wfState = formData.workflows[wf]
      if (wfState?.declared) {
        if (!wfState.targets || wfState.targets.length === 0) {
          errors[wf] = `${wf} workflow requires at least one target.`
        }
      }
    })

    if (Object.keys(errors).length > 0) {
      setValidationErrors(errors)
      setError('Please correct the workflow configuration errors below.')
      if (onAnnounce) onAnnounce('Validation errors detected in workflow configuration.')
      return
    }

    setSaveStatus('saving')
    if (onAnnounce) onAnnounce('Saving profile…')

    const workflowsPayload = {}
    BUILTIN_WORKFLOWS.forEach((wf) => {
      const wfState = formData.workflows[wf]
      if (wfState?.declared) {
        workflowsPayload[wf] = {
          targets: wfState.targets,
          max_attempts: Number(wfState.max_attempts) || 1,
          timeout_s: Number(wfState.timeout_s) || 0,
        }
      } else {
        workflowsPayload[wf] = null
      }
    })

    const payload = {
      id: profileId,
      extends: formData.extends.trim() || null,
      workflows: workflowsPayload,
    }

    try {
      let result
      if (scope === 'project') {
        if (mode === 'create') {
          result = await createProjectProfileOverride(projectId, payload, currentRevision)
        } else {
          result = await updateProjectProfileOverride(projectId, profileId, payload, currentRevision)
        }
      } else {
        if (mode === 'create') {
          result = await createConfigurationProfile(payload, currentRevision)
        } else {
          result = await updateConfigurationProfile(profileId, payload, currentRevision)
        }
      }

      setSaveStatus('reloading')
      if (onAnnounce) onAnnounce('Reloading runtime…')

      setSaveStatus('active')
      const entityLabel = scope === 'project' ? 'Profile override' : 'Profile'
      const savedId = result.override?.id || result.profile?.id || profileId
      if (onAnnounce) onAnnounce(`${entityLabel} "${savedId}" saved and active.`)

      isDirtyRef.current = false
      setIsDirty(false)
      onSaved?.(result)
      onClose?.()
    } catch (err) {
      setSaveStatus('')
      if (err instanceof DashboardApiError && err.status === 409) {
        const payloadErr = err.payload || {}
        setConflictData({
          unchanged: payloadErr.unchanged || 'The configuration file changed on the server.',
          recovery: payloadErr.recovery || 'Reload current configuration and retry.',
          current: payloadErr.current || '',
        })
        if (onAnnounce) {
          onAnnounce('Configuration conflict detected: source changed after editor loading.')
        }
      } else {
        setError(err.payload?.error || err.message || 'Failed to save profile.')
        if (onAnnounce) {
          onAnnounce(`Failed to save profile: ${err.message || 'error'}`)
        }
      }
    }
  }

  const isProject = scope === 'project'
  const dialogTitle = isProject
    ? (mode === 'create' ? 'Create profile override' : `Edit profile override: ${formData.id}`)
    : (mode === 'create' ? 'Create profile' : `Edit profile: ${formData.id}`)
  const isSubmitting = saveStatus === 'saving' || saveStatus === 'reloading'

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={dialogTitle}
      role="dialog"
      ariaLabel={dialogTitle}
    >
      <form onSubmit={handleSubmit} className="profile-editor-form" aria-label={dialogTitle}>
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          {saveStatus === 'saving' && 'Saving profile…'}
          {saveStatus === 'reloading' && 'Reloading runtime…'}
          {saveStatus === 'active' && 'Profile saved and active.'}
          {error && `Error: ${error}`}
        </div>

        {saveStatus && (
          <div className="save-status-banner">
            <span>
              {saveStatus === 'saving' && 'Saving configuration…'}
              {saveStatus === 'reloading' && 'Reloading runtime…'}
              {saveStatus === 'active' && 'Configuration active'}
            </span>
          </div>
        )}

        {error && (
          <Alert tone="error" title="Validation failed">
            {error}
          </Alert>
        )}

        {conflictData && (
          <Alert tone="warning" title="Configuration conflict detected">
            <p className="conflict-unchanged">{conflictData.unchanged}</p>
            <p className="conflict-recovery">{conflictData.recovery}</p>
            {conflictData.current && (
              <p className="conflict-current-preview">
                Server revision: <code>{conflictData.current}</code>
              </p>
            )}
            <div style={{ marginTop: 'var(--space-sm)' }}>
              <button
                type="button"
                className="button button-secondary button-sm"
                onClick={() => onReloadRequired?.()}
              >
                Reload current configuration
              </button>
            </div>
          </Alert>
        )}

        <div className="profile-editor-grid">
          <div className="form-group">
            <label htmlFor="profile-id" className="form-label">
              Profile identifier
            </label>
            <input
              type="text"
              id="profile-id"
              className="form-input"
              value={formData.id}
              disabled={mode === 'edit' || isSubmitting}
              onChange={(e) => handleFieldChange('id', e.target.value)}
              placeholder="e.g. strict-review"
              required
            />
            {mode === 'edit' && (
              <span className="form-help">Profile identifier is immutable after creation.</span>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="profile-extends" className="form-label">
              Inherits from (Parent profile)
            </label>
            <select
              id="profile-extends"
              className="form-select"
              value={formData.extends}
              disabled={isSubmitting}
              onChange={(e) => handleFieldChange('extends', e.target.value)}
            >
              <option value="">(None - base profile)</option>
              {availableProfiles
                .filter((p) => isProject || p !== formData.id)
                .map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
            </select>
            <span className="form-help">Undeclared workflows inherit configuration from the parent profile.</span>
          </div>
        </div>

        <div className="profile-workflows-section">
          <h3 className="profile-section-title">Workflow policies</h3>
          <p className="profile-section-desc">
            Declare custom policies or inherit them from parent configuration.
          </p>

          <div className="profile-workflows-list">
            {BUILTIN_WORKFLOWS.map((wf) => {
              const wfState = formData.workflows[wf] || { declared: false, targets: [] }
              const inheritedWf = profile?.inherited?.[wf]
              const source = profile?.sources?.[wf]
              const hasInherited = Boolean(inheritedWf && inheritedWf.targets?.length)
              const wfError = validationErrors[wf]

              return (
                <div
                  key={wf}
                  className={`profile-workflow-card ${wfState.declared ? 'workflow-card-declared' : 'workflow-card-inherited'}`}
                >
                  <div className="profile-workflow-card-header">
                    <div className="workflow-card-title-group">
                      <label className="checkbox-label" style={{ fontWeight: 600, textTransform: 'capitalize' }}>
                        <input
                          type="checkbox"
                          checked={wfState.declared}
                          disabled={isSubmitting}
                          onChange={(e) => handleWorkflowToggle(wf, e.target.checked)}
                          aria-label={`Declare custom policy for ${wf} workflow`}
                        />
                        <span>{wf}</span>
                      </label>
                      <span className={`source-chip ${wfState.declared ? 'source-chip-declared' : 'source-chip-inherited'}`}>
                        {wfState.declared ? 'Declared' : (hasInherited ? `Inherited (${source || 'parent'})` : 'Undeclared')}
                      </span>
                    </div>
                  </div>

                  {wfError && (
                    <div style={{ marginTop: 'var(--space-xs)' }}>
                      <Alert tone="error" title="Workflow configuration error">
                        {wfError}
                      </Alert>
                    </div>
                  )}

                  {wfState.declared ? (
                    <div className="profile-workflow-controls">
                      <div className="form-group" style={{ marginBottom: 'var(--space-sm)' }}>
                        <label className="form-label" style={{ fontSize: 'var(--type-text-xs-size)' }}>
                          Failover targets (evaluated in order)
                        </label>
                        <div className="profile-targets-ordered-list">
                          {wfState.targets.map((tgt, idx) => (
                            <div key={idx} className="profile-target-row">
                              <span className="target-order-badge" aria-hidden="true">
                                {idx + 1}
                              </span>
                              <select
                                className="form-select profile-target-select"
                                value={tgt}
                                disabled={isSubmitting}
                                onChange={(e) => handleTargetChange(wf, idx, e.target.value)}
                                aria-label={`${wf} target ${idx + 1}`}
                              >
                                {availableTargets.map((t) => (
                                  <option key={t} value={t}>
                                    {t}
                                  </option>
                                ))}
                                {!availableTargets.includes(tgt) && tgt && (
                                  <option value={tgt}>{tgt}</option>
                                )}
                              </select>
                              <div className="target-order-actions">
                                <button
                                  type="button"
                                  className="button button-ghost button-sm"
                                  disabled={idx === 0 || isSubmitting}
                                  onClick={() => handleMoveTarget(wf, idx, -1)}
                                  aria-label={`Move ${wf} target ${idx + 1} up`}
                                >
                                  ▲
                                </button>
                                <button
                                  type="button"
                                  className="button button-ghost button-sm"
                                  disabled={idx === wfState.targets.length - 1 || isSubmitting}
                                  onClick={() => handleMoveTarget(wf, idx, 1)}
                                  aria-label={`Move ${wf} target ${idx + 1} down`}
                                >
                                  ▼
                                </button>
                                <button
                                  type="button"
                                  className="button button-ghost button-sm"
                                  disabled={isSubmitting}
                                  onClick={() => handleRemoveTarget(wf, idx)}
                                  aria-label={`Remove ${wf} target ${idx + 1}`}
                                >
                                  ✕
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                        <button
                          type="button"
                          className="button button-secondary button-sm"
                          style={{ marginTop: 'var(--space-xs)' }}
                          disabled={isSubmitting}
                          onClick={() => handleAddTarget(wf)}
                          aria-label={`Add target to ${wf} workflow`}
                        >
                          + Add target
                        </button>
                      </div>

                      <div className="profile-workflow-grid">
                        <div className="form-group">
                          <label htmlFor={`${wf}-max-attempts`} className="form-label" style={{ fontSize: 'var(--type-text-xs-size)' }}>
                            Max attempts
                          </label>
                          <input
                            type="number"
                            id={`${wf}-max-attempts`}
                            className="form-input"
                            min="1"
                            disabled={isSubmitting}
                            value={wfState.max_attempts}
                            onChange={(e) => handlePolicyFieldChange(wf, 'max_attempts', e.target.value)}
                            aria-label={`${wf} max attempts`}
                          />
                        </div>

                        <div className="form-group">
                          <label htmlFor={`${wf}-timeout`} className="form-label" style={{ fontSize: 'var(--type-text-xs-size)' }}>
                            Timeout (seconds, 0 for none)
                          </label>
                          <input
                            type="number"
                            id={`${wf}-timeout`}
                            className="form-input"
                            min="0"
                            disabled={isSubmitting}
                            value={wfState.timeout_s}
                            onChange={(e) => handlePolicyFieldChange(wf, 'timeout_s', e.target.value)}
                            aria-label={`${wf} timeout in seconds`}
                          />
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="profile-workflow-inherited-preview">
                      {hasInherited ? (
                        <div className="inherited-policy-details">
                          <span className="inherited-targets-label">Effective targets:</span>{' '}
                          <code>{inheritedWf.targets.join(', ')}</code>
                          <span className="inherited-meta">
                            (max attempts: {inheritedWf.max_attempts ?? 1}, timeout: {inheritedWf.timeout_s ? `${inheritedWf.timeout_s}s` : 'none'})
                          </span>
                        </div>
                      ) : (
                        <div className="inherited-policy-empty">
                          <span>Undeclared at this scope. Enable custom policy to configure.</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        <div className="modal-actions" style={{ marginTop: 'var(--space-lg)' }}>
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
              className="button button-primary"
              disabled={isSubmitting}
            >
              {isSubmitting
                ? 'Saving…'
                : isProject
                  ? (mode === 'create' ? 'Create override' : 'Save override')
                  : (mode === 'create' ? 'Create profile' : 'Save profile')}
            </button>
          </div>
        </div>
      </form>
    </Modal>
  )
}
