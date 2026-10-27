import { useEffect, useRef, useState } from 'react'
import { getDiagnostics } from '../api'
import Alert from '../components/Alert'
import DataGrid from '../components/DataGrid'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'

function readUrlFilters() {
  const params = new URLSearchParams(window.location.search)
  return {
    projectId: params.get('project_id') || params.get('project') || '',
    jobId: params.get('job_id') || params.get('job') || '',
    category: params.get('category') || '',
  }
}

export default function Diagnostics({ onNavigate }) {
  const [initialFilters] = useState(readUrlFilters)
  const [projectId, setProjectId] = useState(initialFilters.projectId)
  const [jobId, setJobId] = useState(initialFilters.jobId)
  const [category, setCategory] = useState(initialFilters.category)

  const [reports, setReports] = useState(null)
  const [nextBefore, setNextBefore] = useState(null)
  const [currentBefore, setCurrentBefore] = useState(null)
  const [cursorHistory, setCursorHistory] = useState([])
  const [pageIndex, setPageIndex] = useState(0)

  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  const requestIdRef = useRef(0)
  const abortControllerRef = useRef(null)
  const lastQueryKeyRef = useRef(null)

  function updateUrl(newProj, newJob, newCat) {
    const url = new URL(window.location.href)
    if (newProj) url.searchParams.set('project_id', newProj)
    else url.searchParams.delete('project_id')
    url.searchParams.delete('project')

    if (newJob) url.searchParams.set('job_id', newJob)
    else url.searchParams.delete('job_id')
    url.searchParams.delete('job')

    if (newCat) url.searchParams.set('category', newCat)
    else url.searchParams.delete('category')

    window.history.replaceState({}, '', url.pathname + (url.searchParams.toString() ? `?${url.searchParams.toString()}` : ''))
  }

  function resetPagination() {
    setCurrentBefore(null)
    setCursorHistory([])
    setPageIndex(0)
    setNextBefore(null)
  }

  function handleProjectChange(val) {
    setProjectId(val)
    resetPagination()
    updateUrl(val, jobId, category)
  }

  function handleJobChange(val) {
    setJobId(val)
    resetPagination()
    updateUrl(projectId, val, category)
  }

  function handleCategoryChange(val) {
    setCategory(val)
    resetPagination()
    updateUrl(projectId, jobId, val)
  }

  function handleClearFilters() {
    setProjectId('')
    setJobId('')
    setCategory('')
    resetPagination()
    updateUrl('', '', '')
  }

  function handleRefresh() {
    setRefreshTrigger((t) => t + 1)
  }

  function handleNextPage() {
    if (!nextBefore || isLoading) return
    setCursorHistory((prev) => [...prev, currentBefore])
    setCurrentBefore(nextBefore)
    setPageIndex((prev) => prev + 1)
  }

  function handlePrevPage() {
    if (cursorHistory.length === 0 || isLoading) return
    const prevBefore = cursorHistory[cursorHistory.length - 1]
    setCursorHistory((prev) => prev.slice(0, -1))
    setCurrentBefore(prevBefore)
    setPageIndex((prev) => Math.max(0, prev - 1))
  }

  function navigateToJob(projId, jId) {
    const href = projId
      ? `/dashboard/projects/${encodeURIComponent(projId)}/jobs/${encodeURIComponent(jId)}`
      : `/dashboard/jobs/${encodeURIComponent(jId)}`
    if (onNavigate) {
      onNavigate(href)
    } else {
      window.history.pushState({}, '', href)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }
  }

  useEffect(() => {
    function handlePopState() {
      const f = readUrlFilters()
      setProjectId(f.projectId)
      setJobId(f.jobId)
      setCategory(f.category)
      resetPagination()
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    const trimmedProject = projectId ? projectId.trim() : ''
    const trimmedJob = jobId ? jobId.trim() : ''
    const trimmedCat = category ? category.trim() : ''
    const currentQueryKey = `${trimmedProject}|${trimmedJob}|${trimmedCat}|${currentBefore || ''}`

    const isNewQuery = lastQueryKeyRef.current !== currentQueryKey
    lastQueryKeyRef.current = currentQueryKey

    if (isNewQuery) {
      setReports(null)
      setNextBefore(null)
      setError(null)
    }

    const requestId = ++requestIdRef.current
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    const controller = new AbortController()
    abortControllerRef.current = controller

    setIsLoading(true)

    getDiagnostics(
      {
        projectId: trimmedProject || undefined,
        jobId: trimmedJob || undefined,
        category: trimmedCat || undefined,
        before: currentBefore || undefined,
        limit: 50,
      },
      controller.signal
    )
      .then((data) => {
        if (requestIdRef.current !== requestId) return
        setReports(data.reports || [])
        setNextBefore(data.next_before || null)
        setError(null)
        setIsLoading(false)
      })
      .catch((err) => {
        if (requestIdRef.current !== requestId || controller.signal.aborted) return
        setError(err)
        setIsLoading(false)
      })

    return () => {
      controller.abort()
      requestIdRef.current += 1
    }
  }, [projectId, jobId, category, currentBefore, refreshTrigger])

  const columns = [
    {
      key: 'id',
      header: 'Report ID',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.id,
      width: '120px',
      minWidth: '90px',
      render: (row) => <code className="cell-code">{row.id}</code>,
    },
    {
      key: 'created_at',
      header: 'Reported at',
      priority: 'tertiary',
      sortable: true,
      sortAccessor: (row) => row.created_at,
      width: '160px',
      minWidth: '130px',
      render: (row) => <span className="caption">{row.created_at}</span>,
    },
    {
      key: 'category',
      header: 'Category',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.category,
      width: '110px',
      minWidth: '90px',
      render: (row) => <strong className="category-tag">{row.category}</strong>,
    },
    {
      key: 'job_id',
      header: 'Job ID',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.job_id,
      width: '160px',
      minWidth: '130px',
      render: (row) => {
        const href = row.project_id
          ? `/dashboard/projects/${encodeURIComponent(row.project_id)}/jobs/${encodeURIComponent(row.job_id)}`
          : `/dashboard/jobs/${encodeURIComponent(row.job_id)}`
        return (
          <a
            href={href}
            className="table-link cell-code"
            onClick={(e) => {
              if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
              e.preventDefault()
              navigateToJob(row.project_id, row.job_id)
            }}
          >
            {row.job_id}
          </a>
        )
      },
    },
    {
      key: 'current_state',
      header: 'Current state',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.current_state,
      width: '150px',
      minWidth: '120px',
      render: (row) => (
        <div className="current-state-cell">
          <StatusBadge status={row.current_state} label={`Current: ${row.current_state}`} />
        </div>
      ),
    },
    {
      key: 'expected',
      header: 'Expected',
      priority: 'primary',
      wrap: true,
      render: (row) => <span className="summary-text">{row.expected}</span>,
    },
    {
      key: 'observed',
      header: 'Observed',
      priority: 'primary',
      wrap: true,
      render: (row) => <span className="summary-text">{row.observed}</span>,
    },
  ]

  const hasActiveFilters = Boolean(projectId || jobId || category)

  return (
    <div className="page">
      <PageHeader
        title="Diagnostics"
        description="Client-reported anomalies and protocol observations."
        actions={
          <button
            type="button"
            className="button button-ghost button-sm"
            onClick={handleRefresh}
            disabled={isLoading}
            aria-label="Refresh diagnostics"
          >
            {isLoading ? 'Loading…' : 'Refresh'}
          </button>
        }
      />

      <div className="diagnostics-toolbar" aria-label="Diagnostics filters">
        <label className="filter-field">
          <span className="eyebrow">Project:</span>
          <input
            type="search"
            className="search-input"
            placeholder="Filter by project ID…"
            value={projectId}
            onChange={(e) => handleProjectChange(e.target.value)}
            aria-label="Filter by project"
          />
        </label>
        <label className="filter-field">
          <span className="eyebrow">Job:</span>
          <input
            type="search"
            className="search-input"
            placeholder="Filter by job ID…"
            value={jobId}
            onChange={(e) => handleJobChange(e.target.value)}
            aria-label="Filter by job"
          />
        </label>
        <label className="filter-field">
          <span className="eyebrow">Category:</span>
          <select
            className="profile-select"
            value={category}
            onChange={(e) => handleCategoryChange(e.target.value)}
            aria-label="Filter by category"
          >
            <option value="">All categories</option>
            <option value="protocol">protocol</option>
            <option value="output">output</option>
          </select>
        </label>
        {hasActiveFilters && (
          <button
            type="button"
            className="button button-ghost button-sm"
            onClick={handleClearFilters}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                handleClearFilters()
              }
            }}
            aria-label="Clear filters"
          >
            Clear filters
          </button>
        )}
      </div>

      {error && (!reports || reports.length === 0) && (
        <Alert tone="error" title="Unable to load diagnostics">
          {error.message || 'Failed to fetch diagnostic reports.'}
        </Alert>
      )}

      {error && reports && reports.length > 0 && (
        <Alert tone="warning" title="Showing previously loaded diagnostics">
          Background refresh failed. Displayed reports remain unchanged; retry when the daemon is available.
        </Alert>
      )}

      <DataGrid
        columns={columns}
        rows={reports || []}
        rowKey={(r) => r.id}
        emptyMessage="No diagnostic reports found."
        ariaLabel="Diagnostic reports table"
        isLoading={isLoading && !reports}
      />

      <div className="pagination-bar" aria-label="Pagination controls">
        <button
          type="button"
          className="button button-secondary button-sm"
          onClick={handlePrevPage}
          disabled={cursorHistory.length === 0 || isLoading}
          aria-label="Previous page"
        >
          Previous
        </button>
        <span className="caption page-indicator">
          Page {pageIndex + 1}
        </span>
        <button
          type="button"
          className="button button-secondary button-sm"
          onClick={handleNextPage}
          disabled={!nextBefore || isLoading}
          aria-label="Next page"
        >
          Next
        </button>
      </div>
    </div>
  )
}
