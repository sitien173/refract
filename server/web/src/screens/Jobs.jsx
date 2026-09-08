import { useEffect, useState } from 'react'
import { getProjectJobs, getProjects } from '../api'
import Alert from '../components/Alert'
import DataGrid from '../components/DataGrid'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import { useDashboardQuery } from '../hooks/useDashboardQuery'
import { usePolling } from '../hooks/usePolling'

const TERMINAL_STATES = new Set(['succeeded', 'failed', 'cancelled', 'interrupted'])

export default function Jobs({ projectId: propProjectId, onNavigate }) {
  const [selectedProjectId, setSelectedProjectId] = useState(propProjectId || '')
  const [projectsList, setProjectsList] = useState([])

  useEffect(() => {
    if (propProjectId) {
      setSelectedProjectId(propProjectId)
      return
    }

    function readProjectFromUrl() {
      const params = new URLSearchParams(window.location.search)
      return params.get('project') || ''
    }

    const urlProj = readProjectFromUrl()
    if (urlProj) {
      setSelectedProjectId(urlProj)
    }

    getProjects()
      .then((projects) => {
        if (Array.isArray(projects) && projects.length > 0) {
          setProjectsList(projects)
          if (!urlProj) {
            setSelectedProjectId(projects[0].id)
            const url = new URL(window.location.href)
            url.searchParams.set('project', projects[0].id)
            window.history.replaceState({}, '', url.pathname + url.search)
          }
        }
      })
      .catch(() => {})

    function handlePopState() {
      const p = readProjectFromUrl()
      if (p) setSelectedProjectId(p)
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [propProjectId])

  const activeProjectId = propProjectId || selectedProjectId

  const {
    data: jobsData,
    error,
    isLoading,
    refresh,
  } = useDashboardQuery(
    () => (activeProjectId ? getProjectJobs(activeProjectId) : Promise.resolve([])),
    { deps: [activeProjectId] }
  )

  const jobsList = Array.isArray(jobsData) ? jobsData : []
  const allTerminal = Array.isArray(jobsData) && jobsList.every((j) => TERMINAL_STATES.has(j.state))

  // Poll active jobs every 5 seconds; stop when all displayed jobs are terminal or unmounted
  usePolling(refresh, 5000, {
    enabled: Boolean(activeProjectId),
    isTerminal: allTerminal,
    deps: [activeProjectId, allTerminal],
  })

  function handleProjectChange(newId) {
    setSelectedProjectId(newId)
    const url = new URL(window.location.href)
    url.searchParams.set('project', newId)
    window.history.pushState({}, '', url.pathname + url.search)
  }

  function navigateToJob(jobId) {
    const path = activeProjectId
      ? `/dashboard/projects/${encodeURIComponent(activeProjectId)}/jobs/${encodeURIComponent(jobId)}`
      : `/dashboard/jobs/${encodeURIComponent(jobId)}`
    if (onNavigate) {
      onNavigate(path)
    } else {
      window.history.pushState({}, '', path)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }
  }

  const columns = [
    {
      key: 'id',
      header: 'Job ID',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.id,
      width: '180px',
      minWidth: '140px',
      render: (row) => {
        const href = activeProjectId
          ? `/dashboard/projects/${encodeURIComponent(activeProjectId)}/jobs/${encodeURIComponent(row.id)}`
          : `/dashboard/jobs/${encodeURIComponent(row.id)}`
        return (
          <a
            id={`job-link-${row.id}`}
            href={href}
            className="table-link cell-code"
            onClick={(e) => {
              if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
              e.preventDefault()
              navigateToJob(row.id)
            }}
          >
            {row.id}
          </a>
        )
      },
    },
    {
      key: 'workflow',
      header: 'Workflow',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.workflow,
      width: '140px',
      minWidth: '110px',
      render: (row) => <strong>{row.workflow}</strong>,
    },
    {
      key: 'profile',
      header: 'Profile',
      priority: 'secondary',
      sortable: true,
      sortAccessor: (row) => row.profile || '',
      width: '140px',
      minWidth: '110px',
      render: (row) => <span className="profile-tag">{row.profile}</span>,
    },
    {
      key: 'state',
      header: 'State',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.state,
      width: '140px',
      minWidth: '100px',
      render: (row) => <StatusBadge status={row.state} label={row.state} />,
    },
    {
      key: 'target_id',
      header: 'Target',
      priority: 'secondary',
      sortable: true,
      sortAccessor: (row) => row.target_id || '',
      width: '160px',
      minWidth: '120px',
      render: (row) => <span>{row.target_id || '—'}</span>,
    },
    {
      key: 'config_revision',
      header: 'Config revision',
      priority: 'optional',
      sortable: true,
      sortAccessor: (row) => row.config_revision || '',
      width: '180px',
      minWidth: '130px',
      render: (row) => (
        <code className="cell-code">
          {row.config_revision ? row.config_revision.slice(0, 12) : 'Unavailable'}
        </code>
      ),
    },
    {
      key: 'created_at',
      header: 'Created at',
      priority: 'tertiary',
      sortable: true,
      sortAccessor: (row) => row.created_at || '',
      width: '180px',
      minWidth: '140px',
      render: (row) => <span className="caption">{row.created_at}</span>,
    },
  ]

  return (
    <div className="page">
      <PageHeader
        title="Jobs"
        description="Historical and active job execution records."
        actions={
          <div className="header-actions-group">
            {projectsList.length > 0 && !propProjectId && (
              <label className="header-select-label">
                <span className="eyebrow">Project:</span>
                <select
                  className="profile-select"
                  value={activeProjectId}
                  onChange={(e) => handleProjectChange(e.target.value)}
                  aria-label="Select project for jobs view"
                >
                  {projectsList.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.alias || p.id}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button
              type="button"
              className="button button-ghost button-sm"
              onClick={() => refresh()}
              disabled={isLoading}
            >
              {isLoading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        }
      />

      {error && !jobsData && (
        <Alert tone="error" title="Unable to load jobs">
          {error.message || 'Failed to fetch job history.'}
        </Alert>
      )}

      {error && jobsData && (
        <Alert tone="warning" title="Showing previously loaded jobs">
          Background refresh failed. Displayed jobs remain unchanged; retry when the daemon is available.
        </Alert>
      )}

      <DataGrid
        columns={columns}
        rows={jobsList}
        rowKey={(r) => r.id}
        onRowClick={(r) => navigateToJob(r.id)}
        emptyMessage={
          activeProjectId ? 'No jobs submitted for this project yet.' : 'Select a project to view jobs.'
        }
        ariaLabel="Jobs table"
        isLoading={isLoading && !jobsData}
      />
    </div>
  )
}
