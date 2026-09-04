import { useEffect, useState } from 'react'
import { getOverview } from './api'
import Alert from './components/Alert'
import AppShell from './components/AppShell'
import StatusBadge from './components/StatusBadge'

function routeFromLocation() {
  const parts = window.location.pathname.replace(/^\/dashboard\/?/, '').split('/').filter(Boolean)
  return parts[0] || 'overview'
}

function PageHeader({ title, description }) {
  return (
    <div className="page-header">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </div>
  )
}

function Overview({ overview, error }) {
  if (error) return <div className="page"><Alert tone="error" title="Dashboard unavailable">{error}</Alert></div>
  if (!overview) return <div className="page"><p className="loading">Loading dashboard…</p></div>
  const daemon = overview.daemon || {}
  const configuration = overview.configuration || {}
  return (
    <div className="page">
      <PageHeader title="Overview" description="A live view of the local OpenMCP daemon." />
      <div className="status-grid">
        <section className="metric-panel">
          <span className="eyebrow">Daemon</span>
          <StatusBadge status={daemon.status} label={`Daemon ${daemon.status}`} />
          <strong>{daemon.active_jobs || 0}</strong>
          <span>active jobs</span>
        </section>
        <section className="metric-panel">
          <span className="eyebrow">Configuration</span>
          <StatusBadge status={configuration.valid ? 'healthy' : 'invalid'} label={configuration.valid ? 'Configuration healthy' : 'Configuration invalid'} />
          <strong>{overview.projects || 0}</strong>
          <span>registered projects</span>
        </section>
        <section className="metric-panel">
          <span className="eyebrow">Queue</span>
          <strong>{daemon.queued_jobs || 0}</strong>
          <span>queued jobs</span>
        </section>
      </div>
      {!configuration.valid && <Alert tone="error" title="Configuration needs attention">New job submissions are blocked until the configuration is valid.</Alert>}
      <section className="panel panel-copy">
        <div><span className="eyebrow">Current revision</span><code>{configuration.revision || 'Configuration revision unavailable'}</code></div>
        <div><span className="eyebrow">Targets needing attention</span><strong>{overview.unhealthy_targets || 0}</strong></div>
      </section>
    </div>
  )
}

function SimplePage({ title, description, children }) {
  return <div className="page"><PageHeader title={title} description={description} />{children || <section className="panel empty-panel">Data is available through the dashboard API.</section>}</div>
}

export default function App() {
  const [route, setRoute] = useState(routeFromLocation)
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true
    getOverview().then((value) => {
      if (mounted) setOverview(value)
    }).catch((reason) => {
      if (mounted) setError(reason.message || 'Unable to load dashboard data.')
    })
    return () => { mounted = false }
  }, [])

  function navigate(nextRoute) {
    window.history.pushState({}, '', `/dashboard/${nextRoute === 'overview' ? '' : nextRoute}`)
    setRoute(nextRoute)
  }

  let content
  if (route === 'overview') content = <Overview overview={overview} error={error} />
  else if (route === 'projects') content = <SimplePage title="Projects" description="Registered project workspaces and their effective configuration." />
  else if (route === 'targets') content = <SimplePage title="Targets" description="Configured execution targets and health." />
  else if (route === 'profiles') content = <SimplePage title="Profiles" description="Global workflow profiles and routing policy." />
  else if (route === 'configuration') content = <SimplePage title="Configuration health" description="Source revisions and load evidence." />
  else content = <SimplePage title="Not found" description="That dashboard view does not exist." />

  return <AppShell route={route} title={route === 'overview' ? 'Overview' : route[0].toUpperCase() + route.slice(1)} onNavigate={navigate}>{content}</AppShell>
}
