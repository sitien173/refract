import { getOverview } from '../api'
import Alert from '../components/Alert'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import { useDashboardQuery } from '../hooks/useDashboardQuery'

export default function Overview({ onNavigate }) {
  const { data: overview, error, isLoading, isRefreshing, refresh } = useDashboardQuery(getOverview, {
    pollInterval: 5000,
  })

  function handleLink(e, path) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    e.preventDefault()
    if (onNavigate) {
      onNavigate(path)
    } else {
      window.history.pushState({}, '', path)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }
  }

  if (isLoading && !overview) {
    return (
      <div className="page">
        <div className="loading" aria-busy="true">Loading dashboard…</div>
      </div>
    )
  }

  if (error && !overview) {
    return (
      <div className="page">
        <PageHeader title="Overview" description="A live view of the local OpenMCP daemon." />
        <Alert tone="error" title="Dashboard unavailable">
          {error.message || 'Unable to load dashboard data.'}
        </Alert>
        <div className="panel recovery-panel">
          <p>Verify that the OpenMCP daemon is running locally on the configured port.</p>
          <button type="button" className="button button-secondary" onClick={() => refresh()}>
            Retry connection
          </button>
        </div>
      </div>
    )
  }

  const daemon = overview?.daemon || {}
  const configuration = overview?.configuration || {}
  const isConfigValid = Boolean(configuration.valid)

  return (
    <div className="page">
      <PageHeader
        title="Overview"
        description="A live view of the local OpenMCP daemon."
        actions={
          <button
            type="button"
            className="button button-ghost button-sm"
            onClick={() => refresh()}
            disabled={isRefreshing}
          >
            {isRefreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        }
      />

      {error && overview && (
        <Alert tone="warning" title="Stale data: background refresh failed">
          Showing previously loaded state. {error.message || 'Network error'}.
          <button type="button" className="button-inline-link" onClick={() => refresh()}>
            Retry
          </button>
        </Alert>
      )}

      <div className="status-grid">
        <section className="metric-panel">
          <span className="eyebrow">Daemon</span>
          <StatusBadge status={daemon.status} label={`Daemon ${daemon.status || 'unknown'}`} />
          <strong>{daemon.active_jobs ?? 0}</strong>
          <span>active jobs ({daemon.queued_jobs ?? 0} queued)</span>
        </section>

        <section className="metric-panel">
          <span className="eyebrow">Projects</span>
          <a
            href="/dashboard/projects"
            className="metric-link"
            onClick={(e) => handleLink(e, '/dashboard/projects')}
          >
            <strong>{overview?.projects ?? 0}</strong>
            <span>registered projects →</span>
          </a>
        </section>

        <section className="metric-panel">
          <span className="eyebrow">Targets</span>
          <a
            href="/dashboard/targets?status=attention"
            className="metric-link"
            onClick={(e) => handleLink(e, '/dashboard/targets?status=attention')}
          >
            <strong>{overview?.unhealthy_targets ?? 0}</strong>
            <span>needing attention →</span>
          </a>
        </section>
      </div>

      {!isConfigValid && (
        <Alert tone="error" title="Configuration needs attention">
          <span>New job submissions are blocked until the configuration is valid. </span>
          <a
            href="/dashboard/configuration"
            className="alert-link"
            onClick={(e) => handleLink(e, '/dashboard/configuration')}
          >
            View configuration health →
          </a>
        </Alert>
      )}

      <section className="panel panel-copy">
        <div>
          <span className="eyebrow">Configuration status</span>
          <div className="panel-status-row">
            <StatusBadge
              status={isConfigValid ? 'healthy' : 'invalid'}
              label={isConfigValid ? 'Configuration valid' : 'Configuration invalid'}
            />
            <a
              href="/dashboard/configuration"
              className="copy-link"
              onClick={(e) => handleLink(e, '/dashboard/configuration')}
            >
              Inspection & health →
            </a>
          </div>
          {configuration.revision && (
            <div className="revision-preview">
              <span className="caption">Current revision: </span>
              <code>{configuration.revision}</code>
            </div>
          )}
        </div>

        <div>
          <span className="eyebrow">Daemon workers</span>
          <strong>{daemon.workers ?? 1} active worker{daemon.workers === 1 ? '' : 's'}</strong>
        </div>
      </section>
    </div>
  )
}
