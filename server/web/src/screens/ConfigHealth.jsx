import { getConfiguration, getStatus } from '../api'
import Alert from '../components/Alert'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import { useDashboardQuery } from '../hooks/useDashboardQuery'

export default function ConfigHealth() {
  const {
    data: health,
    error: healthError,
    isLoading: isHealthLoading,
    refresh: refreshHealth,
  } = useDashboardQuery(getConfiguration, { pollInterval: 5000 })

  const {
    data: daemonStatus,
    isLoading: isDaemonLoading,
    refresh: refreshDaemon,
  } = useDashboardQuery(getStatus, { pollInterval: 5000 })

  const isLoading = isHealthLoading || isDaemonLoading
  const isConfigValid = health ? Boolean(health.valid) : true
  const latestError = health?.latest_error || ''
  const lastKnownGoodRevision = health?.last_known_good_revision || ''

  return (
    <div className="page">
      <PageHeader
        title="Configuration health"
        description="Source revisions, reload evidence, and daemon availability diagnostics."
        lastKnownGood={!isConfigValid && lastKnownGoodRevision ? lastKnownGoodRevision : undefined}
        actions={
          <button
            type="button"
            className="button button-ghost button-sm"
            onClick={() => {
              refreshHealth()
              refreshDaemon()
            }}
            disabled={isLoading}
          >
            {isLoading ? 'Loading…' : 'Refresh'}
          </button>
        }
      />

      {healthError && !health && (
        <Alert tone="error" title="Unable to load configuration health">
          {healthError.message || 'Failed to inspect configuration status.'}
        </Alert>
      )}
      {healthError && health && (
        <Alert tone="warning" title="Showing previously loaded configuration health">
          Background refresh failed. The health evidence remains unchanged; retry when the daemon is available.
        </Alert>
      )}

      {!isConfigValid && (
        <Alert tone="error" title="Configuration file is invalid">
          <p>
            The daemon detected errors in the global configuration file. New job submissions are blocked until the configuration is corrected.
          </p>
          {latestError && (
            <div className="alert-error-detail">
              <strong>Error details:</strong>
              <pre className="code-block error-block">{latestError}</pre>
            </div>
          )}
        </Alert>
      )}

      {isConfigValid && health && (
        <Alert tone="info" title="Configuration is healthy">
          <p>Global configuration is valid and actively serving job submissions.</p>
        </Alert>
      )}

      <div className="status-grid">
        <section className="metric-panel">
          <span className="eyebrow">Daemon runtime</span>
          <StatusBadge
            status={daemonStatus?.status || 'running'}
            label={`Daemon ${daemonStatus?.status || 'running'}`}
          />
          <strong>{daemonStatus?.active_jobs ?? 0} active</strong>
          <span>{daemonStatus?.workers ?? 1} worker process{daemonStatus?.workers === 1 ? '' : 'es'} running</span>
        </section>

        <section className="metric-panel">
          <span className="eyebrow">Configuration validity</span>
          <StatusBadge
            status={isConfigValid ? 'healthy' : 'invalid'}
            label={isConfigValid ? 'Configuration valid' : 'Configuration invalid'}
          />
          <strong>{isConfigValid ? 'Valid' : 'Invalid'}</strong>
          <span>{isConfigValid ? 'Accepting new jobs' : 'New jobs blocked'}</span>
        </section>

        <section className="metric-panel">
          <span className="eyebrow">Operation status</span>
          <StatusBadge
            status={isConfigValid ? 'healthy' : 'invalid'}
            label={isConfigValid ? 'Submissions open' : 'Submissions blocked'}
          />
          <strong>{isConfigValid ? 'Normal' : 'Blocked'}</strong>
          <span>In-flight jobs continue unaffected</span>
        </section>
      </div>

      <section className="panel health-details-panel">
        <div className="health-section-header">
          <h3>Load Evidence & Revisions</h3>
        </div>

        <div className="health-grid">
          <div className="health-row">
            <span className="health-label">Configuration file</span>
            <code className="cell-code">{health?.source_path || 'config.toml'}</code>
          </div>

          <div className="health-row">
            <span className="health-label">Current revision hash</span>
            <code className="cell-code">{health?.revision || 'Revision unavailable'}</code>
          </div>

          <div className="health-row">
            <span className="health-label">Last-known-good revision</span>
            <code className="cell-code">{lastKnownGoodRevision || 'None'}</code>
          </div>

          <div className="health-row">
            <span className="health-label">Last attempted reload</span>
            <span>{health?.attempted_at || health?.last_attempted_at || '—'}</span>
          </div>

          <div className="health-row">
            <span className="health-label">Last successful reload</span>
            <span>{health?.successful_at || health?.last_successful_at || '—'}</span>
          </div>

          <div className="health-row">
            <span className="health-label">File modification time</span>
            <span>{health?.modification_time || health?.mtime || '—'}</span>
          </div>
        </div>
      </section>

      {!isConfigValid && (
        <section className="panel recovery-panel">
          <div className="panel-header">
            <h3>Recovery Guidance</h3>
          </div>
          <ol className="recovery-steps">
            <li>
              Open the configuration file at <code>{health?.source_path || 'config.toml'}</code> in your editor.
            </li>
            <li>
              Review the error diagnostic above and fix any TOML syntax or structural errors (e.g., duplicate keys, invalid profile references, missing target definitions).
            </li>
            <li>
              Save the file. The OpenMCP daemon will automatically attempt reload on the next job submission or when you click <strong>Refresh</strong> above.
            </li>
          </ol>
        </section>
      )}
    </div>
  )
}
