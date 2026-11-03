import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { fetchDiagnostics, fetchProjects } from '../api.js'
import { useDiagnostics, useProjects } from '../hooks/usePolling.js'

export function DiagnosticsView() {
  const [projectFilter, setProjectFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [jobIdFilter, setJobIdFilter] = useState('')

  // Projects list for filter dropdown
  const { data: projectsData } = useProjects()
  const projectsList = Array.isArray(projectsData) ? projectsData : []

  // Active query parameters for diagnostics
  const queryParams = useMemo(() => {
    const params = {}
    if (projectFilter) params.project_id = projectFilter
    if (categoryFilter) params.category = categoryFilter
    if (jobIdFilter.trim()) params.job_id = jobIdFilter.trim()
    return params
  }, [projectFilter, categoryFilter, jobIdFilter])

  const queryKey = useMemo(() => JSON.stringify(queryParams), [queryParams])

  // Polling hook for top page
  const { data: polledData, isLoading, error } = useDiagnostics(queryParams)

  // Accumulated reports and cursor associated with queryKey
  const [activeKey, setActiveKey] = useState(queryKey)
  const [reports, setReports] = useState([])
  const [nextBefore, setNextBefore] = useState(null)
  const [hasPaged, setHasPaged] = useState(false)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [expandedRowIds, setExpandedRowIds] = useState(() => new Set())

  const activeKeyRef = useRef(queryKey)
  activeKeyRef.current = queryKey
  const generationRef = useRef(0)
  const hasPagedRef = useRef(false)
  hasPagedRef.current = hasPaged

  // Atomically reset state if query key changed
  if (queryKey !== activeKey) {
    setActiveKey(queryKey)
    generationRef.current += 1
    setReports([])
    setNextBefore(null)
    setHasPaged(false)
    hasPagedRef.current = false
    setExpandedRowIds(new Set())
    setIsLoadingMore(false)
  }

  // Sync polledData when it updates and matches current key
  useEffect(() => {
    if (!polledData) return
    if (polledData._queryKey && polledData._queryKey !== queryKey) {
      return
    }

    const incoming = polledData.reports || []

    if (!hasPagedRef.current) {
      const seen = new Set()
      const deduplicated = []
      for (const r of incoming) {
        if (!seen.has(r.id)) {
          seen.add(r.id)
          deduplicated.push(r)
        }
      }
      setReports(deduplicated)
      setNextBefore(polledData.next_before ?? null)
    } else {
      setReports((prev) => {
        const incomingMap = new Map(incoming.map((r) => [r.id, r]))
        const updatedExisting = prev.map((r) => incomingMap.get(r.id) || r)
        const existingIds = new Set(prev.map((r) => r.id))
        const brandNew = incoming.filter((r) => !existingIds.has(r.id))
        const combined = [...brandNew, ...updatedExisting]
        const seen = new Set()
        const deduplicated = []
        for (const item of combined) {
          if (!seen.has(item.id)) {
            seen.add(item.id)
            deduplicated.push(item)
          }
        }
        return deduplicated
      })
      // Keep paged nextBefore cursor
    }
  }, [polledData, queryKey])

  // Filter change handlers
  const handleProjectChange = (e) => {
    setProjectFilter(e.target.value)
  }

  const handleCategoryChange = (e) => {
    setCategoryFilter(e.target.value)
  }

  const handleJobIdChange = (e) => {
    setJobIdFilter(e.target.value)
  }

  const handleLoadMore = useCallback(async () => {
    if (!nextBefore || isLoadingMore) return
    const currentGeneration = generationRef.current
    const currentKey = activeKeyRef.current
    setIsLoadingMore(true)
    try {
      const res = await fetchDiagnostics({
        ...queryParams,
        before: nextBefore,
      })
      if (generationRef.current !== currentGeneration || activeKeyRef.current !== currentKey) {
        return
      }
      const newReports = res.reports || []
      setReports((prev) => {
        const seen = new Set(prev.map((r) => r.id))
        const deduplicatedNew = newReports.filter((r) => !seen.has(r.id))
        return [...prev, ...deduplicatedNew]
      })
      setNextBefore(res.next_before ?? null)
      setHasPaged(true)
      hasPagedRef.current = true
    } catch {
      // Keep existing
    } finally {
      if (generationRef.current === currentGeneration) {
        setIsLoadingMore(false)
      }
    }
  }, [nextBefore, isLoadingMore, queryParams])

  const toggleRowExpanded = (id) => {
    setExpandedRowIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  return (
    <main
      role="main"
      data-testid="diagnostics-view"
      style={{
        flex: 1,
        padding: 'var(--padding-xl)',
        backgroundColor: 'var(--surface-neutral-01)',
        overflowY: 'auto',
      }}
    >
      <div style={{ marginBottom: 'var(--gap-xl)' }}>
        <h2
          style={{
            fontSize: 'var(--font-size-xl)',
            fontWeight: 'var(--font-weight-bold)',
            color: 'var(--text-default)',
            margin: '0 0 var(--gap-xs) 0',
          }}
        >
          Diagnostics
        </h2>
        <p
          style={{
            fontSize: 'var(--font-size-sm)',
            color: 'var(--text-description)',
            margin: 0,
          }}
        >
          Protocol mismatches, output errors, and suspected job anomalies.
        </p>
      </div>

      {/* Filter controls */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 'var(--gap-md)',
          alignItems: 'flex-end',
          marginBottom: 'var(--gap-xl)',
          padding: 'var(--padding-md)',
          backgroundColor: 'var(--surface-neutral-02)',
          borderRadius: 'var(--radius-card)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap-xs)' }}>
          <label
            htmlFor="diag-project-filter"
            style={{
              fontSize: 'var(--font-size-xs)',
              fontWeight: 'var(--font-weight-semibold)',
              color: 'var(--text-description)',
            }}
          >
            Filter by project
          </label>
          <select
            id="diag-project-filter"
            aria-label="Filter by project"
            value={projectFilter}
            onChange={handleProjectChange}
            style={{
              height: '32px',
              backgroundColor: 'var(--surface-neutral-01)',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius-button)',
              padding: '0 var(--padding-sm)',
              fontSize: 'var(--font-size-sm)',
              color: 'var(--text-default)',
              fontFamily: 'var(--font-family)',
              minWidth: '160px',
            }}
          >
            <option value="">All projects</option>
            {projectsList.map((p) => (
              <option key={p.id} value={p.id}>
                {p.alias || p.id}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap-xs)' }}>
          <label
            htmlFor="diag-category-filter"
            style={{
              fontSize: 'var(--font-size-xs)',
              fontWeight: 'var(--font-weight-semibold)',
              color: 'var(--text-description)',
            }}
          >
            Filter by category
          </label>
          <select
            id="diag-category-filter"
            aria-label="Filter by category"
            value={categoryFilter}
            onChange={handleCategoryChange}
            style={{
              height: '32px',
              backgroundColor: 'var(--surface-neutral-01)',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius-button)',
              padding: '0 var(--padding-sm)',
              fontSize: 'var(--font-size-sm)',
              color: 'var(--text-default)',
              fontFamily: 'var(--font-family)',
              minWidth: '140px',
            }}
          >
            <option value="">All categories</option>
            <option value="protocol">protocol</option>
            <option value="output">output</option>
          </select>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap-xs)' }}>
          <label
            htmlFor="diag-job-filter"
            style={{
              fontSize: 'var(--font-size-xs)',
              fontWeight: 'var(--font-weight-semibold)',
              color: 'var(--text-description)',
            }}
          >
            Filter by job ID
          </label>
          <input
            id="diag-job-filter"
            type="search"
            aria-label="Filter by job ID"
            placeholder="Search job ID..."
            value={jobIdFilter}
            onChange={handleJobIdChange}
            style={{
              height: '32px',
              backgroundColor: 'var(--surface-neutral-01)',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius-button)',
              padding: '0 var(--padding-sm)',
              fontSize: 'var(--font-size-sm)',
              color: 'var(--text-default)',
              fontFamily: 'var(--font-family)',
              minWidth: '200px',
              boxSizing: 'border-box',
            }}
          />
        </div>
      </div>

      {/* Content states */}
      {isLoading && reports.length === 0 ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 'var(--padding-3xl)',
            color: 'var(--text-description)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--gap-sm)' }}>
            <div className="tds-spinner tds-spinner--sm" aria-hidden="true" />
            <span>Loading diagnostics...</span>
          </div>
        </div>
      ) : error && reports.length === 0 ? (
        <div role="alert" className="tds-announcement tds-announcement--negative">
          <div className="tds-announcement__content">
            <p className="tds-announcement__title">Failed to load diagnostics</p>
            <p className="tds-announcement__message">{error.message || 'Unknown error'}</p>
          </div>
        </div>
      ) : reports.length === 0 ? (
        <p style={{ color: 'var(--text-description)', fontSize: 'var(--font-size-sm)' }}>
          No diagnostic reports found.
        </p>
      ) : (
        <div>
          <div
            className="tds-data-table-container"
            style={{
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-card)',
              overflow: 'hidden',
            }}
          >
            <div className="tds-data-table__wrapper">
              <table className="tds-data-table tds-data-table--compact">
                <thead>
                  <tr>
                    <th style={{ width: '40px' }} aria-label="Expand toggle"></th>
                    <th>Category</th>
                    <th>Project</th>
                    <th>Job ID</th>
                    <th>State</th>
                    <th>Created At</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((report) => {
                    const isExpanded = expandedRowIds.has(report.id)
                    return (
                      <React.Fragment key={report.id}>
                        <tr>
                          <td className="tds-data-table__text-cell" style={{ textAlign: 'center' }}>
                            <button
                              type="button"
                              aria-expanded={isExpanded}
                              aria-controls={`diag-detail-${report.id}`}
                              aria-label={isExpanded ? 'Collapse row' : 'Expand row'}
                              onClick={() => toggleRowExpanded(report.id)}
                              style={{
                                background: 'none',
                                border: 'none',
                                cursor: 'pointer',
                                color: 'var(--icon-default)',
                                padding: 'var(--padding-xs)',
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                              }}
                            >
                              <span style={{ fontSize: 'var(--font-size-xs)' }}>
                                {isExpanded ? '▼' : '▶'}
                              </span>
                            </button>
                          </td>
                          <td className="tds-data-table__text-cell">
                            <span
                              className={`tds-tag ${
                                report.category === 'protocol'
                                  ? 'tds-tag--intermediate'
                                  : 'tds-tag--default'
                              }`}
                            >
                              {report.category}
                            </span>
                          </td>
                          <td className="tds-data-table__text-cell">
                            {report.project_id || '-'}
                          </td>
                          <td className="tds-data-table__text-cell">
                            {report.job_id ? (
                              <a
                                href={`#/jobs/${encodeURIComponent(report.job_id)}`}
                                style={{
                                  color: 'var(--text-link)',
                                  textDecoration: 'none',
                                  fontWeight: 'var(--font-weight-medium)',
                                }}
                              >
                                {report.job_id}
                              </a>
                            ) : (
                              '-'
                            )}
                          </td>
                          <td className="tds-data-table__text-cell">
                            <span className="tds-tag tds-tag--default">
                              {report.current_state || '-'}
                            </span>
                          </td>
                          <td className="tds-data-table__text-cell">
                            <span className="tds-data-table__cell-subtext">
                              {report.created_at || '-'}
                            </span>
                          </td>
                        </tr>

                        {isExpanded && (
                          <tr id={`diag-detail-${report.id}`}>
                            <td
                              colSpan={6}
                              style={{
                                padding: 'var(--padding-md)',
                                backgroundColor: 'var(--surface-neutral-02)',
                                borderBottom: '1px solid var(--border-subtle)',
                              }}
                            >
                              <div
                                style={{
                                  display: 'flex',
                                  flexDirection: 'column',
                                  gap: 'var(--gap-sm)',
                                }}
                              >
                                <div>
                                  <span
                                    style={{
                                      fontSize: 'var(--font-size-xs)',
                                      fontWeight: 'var(--font-weight-semibold)',
                                      textTransform: 'uppercase',
                                      color: 'var(--text-caption)',
                                    }}
                                  >
                                    Expected:
                                  </span>
                                  <pre
                                    style={{
                                      margin: 'var(--gap-xs) 0 0 0',
                                      fontFamily: 'monospace',
                                      fontSize: 'var(--font-size-xs)',
                                      whiteSpace: 'pre-wrap',
                                      wordBreak: 'break-all',
                                      color: 'var(--text-default)',
                                      backgroundColor: 'var(--surface-neutral-01)',
                                      padding: 'var(--padding-sm)',
                                      borderRadius: 'var(--radius-button)',
                                      border: '1px solid var(--border-subtle)',
                                    }}
                                  >
                                    {report.expected || '(empty)'}
                                  </pre>
                                </div>
                                <div>
                                  <span
                                    style={{
                                      fontSize: 'var(--font-size-xs)',
                                      fontWeight: 'var(--font-weight-semibold)',
                                      textTransform: 'uppercase',
                                      color: 'var(--text-negative)',
                                    }}
                                  >
                                    Observed:
                                  </span>
                                  <pre
                                    style={{
                                      margin: 'var(--gap-xs) 0 0 0',
                                      fontFamily: 'monospace',
                                      fontSize: 'var(--font-size-xs)',
                                      whiteSpace: 'pre-wrap',
                                      wordBreak: 'break-all',
                                      color: 'var(--text-negative)',
                                      backgroundColor: 'var(--surface-neutral-01)',
                                      padding: 'var(--padding-sm)',
                                      borderRadius: 'var(--radius-button)',
                                      border: '1px solid var(--border-subtle)',
                                    }}
                                  >
                                    {report.observed || '(empty)'}
                                  </pre>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination controls */}
          {nextBefore !== null && (
            <div
              style={{
                marginTop: 'var(--gap-lg)',
                display: 'flex',
                justifyContent: 'center',
              }}
            >
              <button
                type="button"
                className="tds-btn tds-btn--secondary tds-btn--sm"
                onClick={handleLoadMore}
                disabled={isLoadingMore}
              >
                {isLoadingMore ? 'Loading...' : 'Load more'}
              </button>
            </div>
          )}
        </div>
      )}
    </main>
  )
}

export default DiagnosticsView
