import { useEffect, useState } from 'react'
import { getConfiguration, getProject, getProjectJobs, getProjects } from '../api'
import Alert from '../components/Alert'
import ConfigurationHealthBanner from '../components/ConfigurationHealthBanner'
import DataGrid from '../components/DataGrid'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import { useDashboardQuery } from '../hooks/useDashboardQuery'

async function mapConcurrent(items, limit, fn) {
  const results = new Array(items.length)
  let index = 0
  async function worker() {
    while (index < items.length) {
      const i = index
      index += 1
      results[i] = await fn(items[i], i)
    }
  }
  const workers = Array.from({ length: Math.min(limit, items.length) }, () => worker())
  await Promise.all(workers)
  return results
}

export default function Projects({ onNavigate }) {
  const { data: rawProjects, error, isLoading, refresh } = useDashboardQuery(getProjects)
  const { data: configurationHealth, refresh: refreshConfigurationHealth } = useDashboardQuery(getConfiguration, { pollInterval: 5000 })
  const [hydratedProjects, setHydratedProjects] = useState([])
  const [isHydrating, setIsHydrating] = useState(false)
  const [filterText, setFilterText] = useState('')

  useEffect(() => {
    let mounted = true
    if (!rawProjects || rawProjects.length === 0) {
      setHydratedProjects([])
      return
    }

    setIsHydrating(true)
    mapConcurrent(rawProjects, 3, async (p) => {
      let profile = 'default'
      let health = 'healthy'
      let activity = 'Idle'

      try {
        const detail = await getProject(p.id)
        const cfg = detail.configuration || {}
        profile = cfg.project_default_profile || cfg.global_default_profile || 'default'
      } catch (err) {
        health = 'invalid'
        profile = 'error'
      }

      try {
        const jobs = await getProjectJobs(p.id)
        if (Array.isArray(jobs)) {
          const activeCount = jobs.filter((j) => j.state === 'running' || j.state === 'queued').length
          activity = activeCount > 0 ? `${activeCount} active` : 'Idle'
        }
      } catch {
        // Leave activity as Idle if jobs call fails
      }

      return {
        ...p,
        profile,
        health,
        activity,
      }
    }).then((results) => {
      if (mounted) {
        setHydratedProjects(results)
        setIsHydrating(false)
      }
    })

    return () => {
      mounted = false
    }
  }, [rawProjects])

  function navigateToProject(projectId) {
    const path = `/dashboard/projects/${encodeURIComponent(projectId)}`
    if (onNavigate) {
      onNavigate(path)
    } else {
      window.history.pushState({}, '', path)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }
  }

  const displayedProjects = (hydratedProjects.length > 0 ? hydratedProjects : rawProjects || []).filter((p) => {
    if (!filterText) return true
    const term = filterText.toLowerCase()
    return (
      (p.alias && p.alias.toLowerCase().includes(term)) ||
      (p.id && p.id.toLowerCase().includes(term)) ||
      (p.root && p.root.toLowerCase().includes(term))
    )
  })

  const columns = [
    {
      key: 'alias',
      header: 'Alias',
      width: '180px',
      render: (row) => (
        <a
          href={`/dashboard/projects/${encodeURIComponent(row.id)}`}
          className="table-link"
          onClick={(e) => {
            if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
            e.preventDefault()
            navigateToProject(row.id)
          }}
        >
          {row.alias || row.id}
        </a>
      ),
    },
    {
      key: 'root',
      header: 'Workspace root',
      width: '320px',
      render: (row) => <code className="cell-code">{row.root}</code>,
    },
    {
      key: 'profile',
      header: 'Profile',
      width: '160px',
      render: (row) => <span className="profile-tag">{row.profile || (isHydrating ? '…' : 'default')}</span>,
    },
    {
      key: 'activity',
      header: 'Activity',
      width: '140px',
      render: (row) => <span>{row.activity || (isHydrating ? '…' : 'Idle')}</span>,
    },
    {
      key: 'health',
      header: 'Health',
      width: '180px',
      render: (row) => (
        <StatusBadge
          status={row.health || (isHydrating ? 'unknown' : 'healthy')}
          label={row.health === 'invalid' ? 'Configuration invalid' : row.health === 'healthy' ? 'Healthy' : 'Checking…'}
        />
      ),
    },
  ]

  return (
    <div className="page">
      <PageHeader
        title="Projects"
        description="Registered project workspaces and their effective configuration."
        actions={
          <div className="header-filter-bar">
            <input
              type="search"
              className="search-input"
              placeholder="Filter projects…"
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              aria-label="Filter projects"
            />
            <button
              type="button"
              className="button button-ghost button-sm"
              onClick={() => {
                refresh()
                refreshConfigurationHealth()
              }}
              disabled={isLoading}
            >
              {isLoading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        }
      />

      {error && !rawProjects && (
        <Alert tone="error" title="Unable to load projects">
          {error.message || 'Failed to fetch registered projects.'}
        </Alert>
      )}
      <ConfigurationHealthBanner health={configurationHealth} />

      {error && rawProjects && (
        <Alert tone="warning" title="Showing previously loaded projects">
          Background refresh failed. The project table remains unchanged; retry when the daemon is available.
        </Alert>
      )}

      <DataGrid
        columns={columns}
        rows={displayedProjects}
        rowKey={(row) => row.id}
        onRowClick={(row) => navigateToProject(row.id)}
        emptyMessage={filterText ? 'No projects match your filter.' : 'No project workspaces registered.'}
        recoveryAction={
          filterText ? (
            <button type="button" className="button button-secondary button-sm" onClick={() => setFilterText('')}>
              Clear filter
            </button>
          ) : (
            <p className="caption">Register a workspace with <code>openmcp register &lt;path&gt;</code> to begin.</p>
          )
        }
        ariaLabel="Projects table"
        isLoading={isLoading}
      />
    </div>
  )
}
