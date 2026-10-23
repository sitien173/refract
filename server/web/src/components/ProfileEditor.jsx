import { useEffect, useRef, useState } from 'react'
import {
  createConfigurationProfile,
  updateConfigurationProfile,
  createProjectProfileOverride,
  updateProjectProfileOverride,
} from '../api'
import Alert from './Alert'
import Modal from './Modal'
import { useConfigEditor } from '../hooks/useConfigEditor'

const EMPTY_LIST = []

export default function ProfileEditor({
  isOpen,
  mode = 'create',
  scope = 'global',
  projectId = '',
  profile = null,
  revision = '',
  availableTargets = EMPTY_LIST,
  availableProfiles = EMPTY_LIST,
  workflows = EMPTY_LIST,
  onClose,
  onSaved,
  onAnnounce,
  onReloadRequired,
}) {
  const [formData, setFormData] = useState(() => getInitialFormData(profile, availableTargets))
  const {
    isDirtyRef, inFlightRef, currentRevision, setCurrentRevision,
    saveStatus, setSaveStatus, error, setError, conflictData, setConflictData,
    handleClose, submit, reload,
  } = useConfigEditor({ revision, onClose, onSaved, onAnnounce })
  const [validationErrors, setValidationErrors] = useState({})

  function getInitialFormData(prof, targetsList) {
    const defaultTarget = targetsList && targetsList.length > 0 ? targetsList[0] : ''
    const workflowsState = {}

    workflows.forEach((wf) => {
      const declaredWf = prof?.declared?.[wf] || prof?.workflows?.[wf]
      if (declaredWf && Array.isArray(declaredWf.targets) && declaredWf.targets.length > 0) {
        workflowsState[wf] = {
          declared: true,
          targets: [...declaredWf.targets],
          timeout_s: declaredWf.timeout_s ?? 0,
        }
      } else {
        const inheritedWf = prof?.inherited?.[wf]
        workflowsState[wf] = {
          declared: false,
          targets: inheritedWf?.targets ? [...inheritedWf.targets] : (defaultTarget ? [defaultTarget] : []),
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

  const prevIsOpenRef = useRef(false)

  useEffect(() => {
    if (!isOpen) {
      prevIsOpenRef.current = false
      isDirtyRef.current = false
      setError(null)
      setValidationErrors({})
      setConflictData(null)
      setSaveStatus('')
      return
    }

    const wasOpen = prevIsOpenRef.current
    prevIsOpenRef.current = true

    if (!wasOpen || (!isDirtyRef.current && !inFlightRef.current && !conflictData)) {
      setCurrentRevision(revision)
      setFormData(getInitialFormData(profile, availableTargets))
      setError(null)
      setValidationErrors({})
      setConflictData(null)
      setSaveStatus('')
    }
  }, [isOpen, mode, profile, revision, availableTargets, workflows])

  function handleFieldChange(field, value) {
    isDirtyRef.current = true
    setError(null)
    setFormData((prev) => ({ ...prev, [field]: value }))
  }

  function handleWorkflowToggle(wf, declared) {
    isDirtyRef.current = true
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
            timeout_s: currentWf.timeout_s ?? 0,
          },
        },
      }
    })
  }

  function handleAddTarget(wf) {
    isDirtyRef.current = true
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
    if (inFlightRef.current || conflictData || !currentRevision || workflows.length === 0) return
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
    workflows.forEach((wf) => {
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

    const workflowsPayload = {}
    workflows.forEach((wf) => {
      const wfState = formData.workflows[wf]
      if (wfState?.declared) {
        workflowsPayload[wf] = {
          targets: wfState.targets,
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

    return submit({
      entity: 'profile',
      savingMessage: 'Saving profile…',
      successMessage: (result) => {
        const entityLabel = scope === 'project' ? 'Profile override' : 'Profile'
        const savedId = result.override?.id || result.profile?.id || profileId
        return `${entityLabel} "${savedId}" saved and active.`
      },
      save: (revision) => {
        if (scope === 'project') {
          return mode === 'create'
            ? createProjectProfileOverride(projectId, payload, revision)
            : updateProjectProfileOverride(projectId, profileId, payload, revision)
        }
        return mode === 'create'
          ? createConfigurationProfile(payload, revision)
          : updateConfigurationProfile(profileId, payload, revision)
      },
    })
  }

  function handleReloadConfiguration() {
    return reload({
      load: onReloadRequired,
      select: (payload) => payload?.profile || payload?.override ||
        (mode === 'create' ? (payload?.profiles || payload?.overrides)?.find((p) => p.id === formData.id) : null),
      apply: (item) => setFormData(getInitialFormData(item, availableTargets)),
      mode,
      entity: scope === 'project' ? 'Profile override' : 'Profile',
    })
  }

  const isProject = scope === 'project'
  const dialogTitle = isProject
    ? (mode === 'create' ? 'Create profile override' : `Edit profile override: ${formData.id}`)
    : (mode === 'create' ? 'Create profile' : `Edit profile: ${formData.id}`)
  const isSubmitting = saveStatus === 'saving' || saveStatus === 'reloading'

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
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
                onClick={handleReloadConfiguration}
                disabled={isSubmitting}
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
            {workflows.map((wf) => {
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
                        <span className="form-label" style={{ fontSize: 'var(--type-text-xs-size)' }}>
                          Failover targets (evaluated in order)
                        </span>
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
                            (timeout: {inheritedWf.timeout_s ? `${inheritedWf.timeout_s}s` : 'none'})
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
            onClick={handleClose}
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <div className="modal-actions-right">
            <button
              type="submit"
              className="button button-primary"
              disabled={isSubmitting || Boolean(conflictData) || !currentRevision || workflows.length === 0}
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
