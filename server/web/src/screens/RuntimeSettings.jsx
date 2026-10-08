import { getConfiguration, getSettings, updateMaxProjectReaders } from '../api'
import Alert from '../components/Alert'
import DataGrid from '../components/DataGrid'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import { useDashboardQuery } from '../hooks/useDashboardQuery'
import { useEffect, useRef, useState } from 'react'

export default function RuntimeSettings() {
  const [readerDraft, setReaderDraft] = useState('')
  const [readerDirty, setReaderDirty] = useState(false)
  const readerDirtyRef = useRef(false)
  const [readerSaving, setReaderSaving] = useState(false)
  const [readerReloading, setReaderReloading] = useState(false)
  const [readerConflict, setReaderConflict] = useState(false)
  const [readerError, setReaderError] = useState('')
  const [readerSaved, setReaderSaved] = useState(false)
  const {
    data: settings,
    error: settingsError,
    isLoading: isSettingsLoading,
    refresh: refreshSettings,
  } = useDashboardQuery(getSettings)

  const {
    data: configHealth,
    error: healthError,
    isLoading: isHealthLoading,
    refresh: refreshHealth,
  } = useDashboardQuery(getConfiguration)

  const isLoading = isSettingsLoading || isHealthLoading
  const isConfigValid = configHealth ? Boolean(configHealth.valid) : true
  const lastKnownGoodRevision = configHealth?.last_known_good_revision || ''

  const daemon = settings?.daemon || {}
  const logging = settings?.logging || {}

  useEffect(() => {
    if (settings && !readerDirtyRef.current) {
      setReaderDraft(String(settings.daemon?.max_project_readers ?? ''))
    }
  }, [settings, readerDirty])

  async function saveReaderCapacity(event) {
    event.preventDefault()
    const value = Number(readerDraft)
    if (!Number.isSafeInteger(value) || value < 1) {
      setReaderError('Enter a positive whole number of project readers.')
      setReaderSaved(false)
      return
    }
    if (readerConflict) return
    setReaderSaving(true)
    setReaderError('')
    setReaderSaved(false)
    try {
      const updated = await updateMaxProjectReaders(value, settings?.revision)
      setReaderDraft(String(updated.daemon.max_project_readers))
      readerDirtyRef.current = false
      setReaderDirty(false)
      setReaderConflict(false)
      setReaderSaved(true)
      await refreshSettings()
    } catch (err) {
      if (err.status === 409 || err.payload?.code === 'configuration_conflict') {
        setReaderConflict(true)
        setReaderError('Configuration changed. Reload current settings before retrying.')
      } else {
        setReaderError(err.message || 'Unable to save reader capacity.')
      }
    } finally {
      setReaderSaving(false)
    }
  }

  async function reloadReaderCapacity() {
    setReaderReloading(true)
    try {
      const latest = await getSettings()
      await refreshSettings()
      setReaderDraft(String(latest.daemon.max_project_readers))
      readerDirtyRef.current = false
      setReaderDirty(false)
      setReaderConflict(false)
      setReaderError('')
      setReaderSaved(false)
    } catch (err) {
      setReaderError(err.message || 'Unable to reload settings.')
    } finally {
      setReaderReloading(false)
    }
  }

  const liveRows = [
    {
      id: 'targets',
      setting: 'Targets',
      value: 'Execution target definitions & models',
      behavior: 'Live',
      details: 'Reloaded before each job submission',
    },
    {
      id: 'profiles',
      setting: 'Profiles',
      value: 'Workflow profiles & inheritance hierarchy',
      behavior: 'Live',
      details: 'Reloaded before each job submission',
    },
    {
      id: 'default_profile',
      setting: 'Default profile',
      value: daemon.default_profile || 'default',
      behavior: 'Live',
      details: 'Active fallback profile for new jobs',
    },
  ]

  const restartRows = [
    {
      id: 'host',
      setting: 'Host',
      value: daemon.host ?? '127.0.0.1',
      behavior: 'Restart required',
      details: 'Daemon listening interface',
    },
    {
      id: 'port',
      setting: 'Port',
      value: daemon.port ?? 8000,
      behavior: 'Restart required',
      details: 'Daemon listening port',
    },
    {
      id: 'project_readers',
      setting: 'Project reader capacity',
      value: `Configured ${daemon.max_project_readers ?? 1}; effective ${settings?.effective?.max_project_readers ?? 1}`,
      behavior: 'Restart required',
      details: 'Configured capacity is pending until daemon restart; active scheduler capacity remains unchanged',
    },
    {
      id: 'workers',
      setting: 'Worker count (max jobs)',
      value: daemon.max_jobs ?? 1,
      behavior: 'Restart required',
      details: 'Maximum concurrent job execution workers',
    },
    {
      id: 'history_turns',
      setting: 'History turns',
      value: daemon.history_turns ?? 50,
      behavior: 'Restart required',
      details: 'Retained context history turn limit',
    },
    {
      id: 'history_bytes',
      setting: 'History bytes',
      value: daemon.history_bytes ?? 1048576,
      behavior: 'Restart required',
      details: 'Retained context byte limit',
    },
    {
      id: 'logging_level',
      setting: 'Logging level',
      value: logging.level ?? 'INFO',
      behavior: 'Restart required',
      details: 'Minimum log severity threshold',
    },
    {
      id: 'logging_format',
      setting: 'Logging format',
      value: logging.format ?? 'text',
      behavior: 'Restart required',
      details: 'Log output structure format',
    },
    {
      id: 'logging_destination',
      setting: 'Logging destination',
      value: logging.file === false ? 'Console only' : (logging.file || 'Console only'),
      behavior: 'Restart required',
      details: 'Log file destination path',
    },
    {
      id: 'logging_console',
      setting: 'Console logging',
      value: logging.console ? 'Enabled' : 'Disabled',
      behavior: 'Restart required',
      details: 'Standard output stream logging',
    },
    {
      id: 'logging_max_bytes',
      setting: 'Log rotation max bytes',
      value: logging.max_bytes ?? 10485760,
      behavior: 'Restart required',
      details: 'File rotation size threshold',
    },
    {
      id: 'logging_backup_count',
      setting: 'Log backup count',
      value: logging.backup_count ?? 5,
      behavior: 'Restart required',
      details: 'Retained rotated log files',
    },
    {
      id: 'logging_warnings',
      setting: 'Capture warnings',
      value: logging.capture_warnings ? 'Enabled' : 'Disabled',
      behavior: 'Restart required',
      details: 'Route Python warnings to loggers',
    },
  ]

  // Identify any unclassified top-level or child keys
  const knownDaemonKeys = new Set(['host', 'port', 'max_jobs', 'max_project_readers', 'history_turns', 'history_bytes', 'default_profile'])
  const knownLoggingKeys = new Set(['level', 'format', 'file', 'console', 'max_bytes', 'backup_count', 'capture_warnings'])
  const unclassifiedRows = []

  Object.entries(daemon).forEach(([key, val]) => {
    if (!knownDaemonKeys.has(key)) {
      unclassifiedRows.push({
        id: `daemon_${key}`,
        setting: `daemon.${key}`,
        value: String(val),
        behavior: 'Unclassified',
        details: 'Custom or unmapped daemon setting',
      })
    }
  })

  Object.entries(logging).forEach(([key, val]) => {
    if (!knownLoggingKeys.has(key)) {
      unclassifiedRows.push({
        id: `logging_${key}`,
        setting: `logging.${key}`,
        value: String(val),
        behavior: 'Unclassified',
        details: 'Custom or unmapped logging setting',
      })
    }
  })

  const columns = [
    {
      key: 'setting',
      header: 'Setting',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.setting,
      width: '240px',
      minWidth: '160px',
      render: (row) => <strong>{row.setting}</strong>,
    },
    {
      key: 'value',
      header: 'Configured value',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => String(row.value ?? ''),
      width: '280px',
      minWidth: '140px',
      wrap: true,
      render: (row) => <code className="cell-code">{String(row.value)}</code>,
    },
    {
      key: 'behavior',
      header: 'Reload behavior',
      priority: 'secondary',
      sortable: true,
      sortAccessor: (row) => row.behavior || '',
      width: '160px',
      minWidth: '120px',
      render: (row) => {
        const isLive = row.behavior === 'Live'
        const isRestart = row.behavior === 'Restart required'
        return (
          <span
            className={`behavior-badge ${
              isLive ? 'behavior-live' : isRestart ? 'behavior-restart' : 'behavior-unclassified'
            }`}
          >
            {row.behavior}
          </span>
        )
      },
    },
    {
      key: 'details',
      header: 'Details',
      priority: 'tertiary',
      sortable: true,
      sortAccessor: (row) => row.details || '',
      width: '320px',
      minWidth: '180px',
      wrap: true,
      render: (row) => <span className="caption">{row.details}</span>,
    },
  ]

  return (
    <div className="page">
      <PageHeader
        title="Runtime settings"
        description="Configuration classification and daemon reload characteristics."
        lastKnownGood={!isConfigValid && lastKnownGoodRevision ? lastKnownGoodRevision : undefined}
        actions={
          <button
            type="button"
            className="button button-ghost button-sm"
            onClick={() => {
              refreshSettings()
              refreshHealth()
            }}
            disabled={isLoading}
          >
            {isLoading ? 'Loading…' : 'Refresh'}
          </button>
        }
      />

      {!isConfigValid && (
        <Alert tone="warning" title="Running on last-known-good catalog">
          <span>
            The configuration file has errors. Settings below reflect the active catalog snapshot.
          </span>
        </Alert>
      )}

      {settingsError && !settings && (
        <Alert tone="error" title="Unable to load settings">
          {settingsError.message || 'Failed to fetch runtime settings.'}
        </Alert>
      )}
      {settingsError && settings && (
        <Alert tone="warning" title="Showing previously loaded settings">
          Background refresh failed. The settings table remains unchanged; retry when the daemon is available.
        </Alert>
      )}

      <div className="settings-summary-panel panel">
        <div className="settings-summary-item">
          <span className="eyebrow">Source file</span>
          <code>{settings?.source_path || 'config.toml'}</code>
        </div>
        <div className="settings-summary-item">
          <span className="eyebrow">Configuration revision</span>
          <code>{settings?.revision || 'Revision unavailable'}</code>
        </div>
        <div className="settings-summary-item">
          <span className="eyebrow">Status</span>
          <StatusBadge
            status={isConfigValid ? 'valid' : 'invalid'}
            label={isConfigValid ? 'Active catalog valid' : 'File invalid (snapshot preserved)'}
          />
        </div>
      </div>

      <section className="settings-section">
        <div className="section-header">
          <h3>Project reader capacity</h3>
          <p className="caption">
            Configured: {daemon.max_project_readers ?? '—'} (pending); effective scheduler capacity: {settings?.effective?.max_project_readers ?? '—'}. Restart required to apply a saved change.
          </p>
        </div>
        <form className="reader-capacity-form" onSubmit={saveReaderCapacity}>
          <label htmlFor="max-project-readers">Maximum project readers</label>
          <input
            id="max-project-readers"
            name="max_project_readers"
            type="number"
            min="1"
            step="1"
            required
            value={readerDraft}
            onChange={(event) => {
              setReaderDraft(event.target.value)
              readerDirtyRef.current = true
              setReaderDirty(true)
              setReaderSaved(false)
            }}
          />
          <button type="submit" className="button button-primary" disabled={readerSaving || readerConflict || !settings}>
            {readerSaving ? 'Saving…' : 'Save reader capacity'}
          </button>
          {readerSaved && <span role="status">Saved; restart required.</span>}
          {readerError && (
            <Alert tone="error" title={readerConflict ? 'Configuration conflict' : 'Unable to save reader capacity'}>
              {readerError}
              {readerConflict && (
                <button type="button" className="button button-secondary button-sm" onClick={reloadReaderCapacity} disabled={readerReloading}>
                  {readerReloading ? 'Reloading…' : 'Reload current settings'}
                </button>
              )}
            </Alert>
          )}
        </form>
      </section>

      <section className="settings-section">
        <div className="section-header">
          <h3>Live Configuration</h3>
          <p className="caption">
            Changes to these settings take effect immediately on next job submission without restarting the daemon.
          </p>
        </div>
        <DataGrid
          columns={columns}
          rows={liveRows}
          rowKey={(r) => r.id}
          ariaLabel="Live configuration settings table"
          isLoading={isLoading}
        />
      </section>

      <section className="settings-section">
        <div className="section-header">
          <h3>Restart Required</h3>
          <p className="caption">
            Changes to these settings require a full daemon restart to be applied.
          </p>
        </div>
        <DataGrid
          columns={columns}
          rows={restartRows}
          rowKey={(r) => r.id}
          ariaLabel="Restart required settings table"
          isLoading={isLoading}
        />
      </section>

      {unclassifiedRows.length > 0 && (
        <section className="settings-section">
          <div className="section-header">
            <h3>Unclassified</h3>
            <p className="caption">Unmapped settings or custom configuration values.</p>
          </div>
          <DataGrid
            columns={columns}
            rows={unclassifiedRows}
            rowKey={(r) => r.id}
            ariaLabel="Unclassified settings table"
            isLoading={isLoading}
          />
        </section>
      )}
    </div>
  )
}
