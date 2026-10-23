import { useRef, useState } from 'react'
import { DashboardApiError } from '../api'

export function useConfigEditor({ revision, onClose, onSaved, onAnnounce }) {
  const isDirtyRef = useRef(false)
  const inFlightRef = useRef(false)
  const [currentRevision, setCurrentRevision] = useState(revision)
  const [saveStatus, setSaveStatus] = useState('')
  const [error, setError] = useState(null)
  const [conflictData, setConflictData] = useState(null)

  function handleClose() {
    if (inFlightRef.current) return
    if (!isDirtyRef.current || window.confirm('You have unsaved changes. Discard them?')) {
      onClose?.()
    }
  }

  function begin(status) {
    if (inFlightRef.current || (status === 'saving' && (!currentRevision || conflictData))) return false
    inFlightRef.current = true
    setSaveStatus(status)
    setError(null)
    return true
  }

  function finish() {
    inFlightRef.current = false
    setSaveStatus('')
  }

  function handleSaveError(err, entity) {
    if (err instanceof DashboardApiError && err.status === 409) {
      const payload = err.payload || {}
      setConflictData({
        unchanged: payload.unchanged || 'The configuration file changed on the server.',
        recovery: payload.recovery || 'Reload current configuration and retry.',
        current: payload.current || '',
      })
      onAnnounce?.('Configuration conflict detected: source changed after editor loading.')
    } else {
      setError(err.payload?.error || err.message || `Failed to save ${entity}.`)
      onAnnounce?.(`Failed to save ${entity}: ${err.message || 'error'}`)
    }
  }

  async function submit({ save, entity, savingMessage, successMessage }) {
    if (!begin('saving')) return
    try {
      onAnnounce?.(savingMessage)
      const result = await save(currentRevision)
      setSaveStatus('active')
      onAnnounce?.(successMessage(result))
      isDirtyRef.current = false
      onSaved?.(result)
      onClose?.()
    } catch (err) {
      handleSaveError(err, entity)
    } finally {
      finish()
    }
  }

  async function reload({ load, select, apply, mode, entity }) {
    if (!begin('reloading')) return
    try {
      const payload = await load?.()
      const item = select(payload)
      if (mode === 'edit' && !item) throw new Error(`${entity} no longer exists or could not be reloaded.`)
      if (!payload?.revision) throw new Error('Reload response missing configuration revision.')
      if (item) apply(item)
      setCurrentRevision(payload.revision)
      isDirtyRef.current = false
      setConflictData(null)
      onAnnounce?.('Current configuration reloaded from server. Draft replaced.')
    } catch (err) {
      setError(err?.message || 'Failed to reload configuration.')
      onAnnounce?.(`Failed to reload configuration: ${err?.message || 'error'}`)
    } finally {
      finish()
    }
  }

  return {
    isDirtyRef, inFlightRef, currentRevision, setCurrentRevision,
    saveStatus, setSaveStatus, error, setError, conflictData, setConflictData,
    handleClose, submit, reload,
  }
}
