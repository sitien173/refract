import { useEffect, useState } from 'react'
import { getConfiguration, getTargets } from '../api'
import Alert from '../components/Alert'
import ConfigurationHealthBanner from '../components/ConfigurationHealthBanner'
import DataGrid from '../components/DataGrid'
import Inspector, { InspectorRow } from '../components/Inspector'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import { useDashboardQuery } from '../hooks/useDashboardQuery'

function isCircuitOpenUntil(value, now = Date.now()) {
  if (!value) return false
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) && timestamp > now
}

function readStatusFilterFromUrl() {
  const params = new URLSearchParams(window.location.search)
  const statusParam = params.get('status')
  if (statusParam === 'attention' || statusParam === 'unhealthy') return 'attention'
  if (statusParam === 'healthy') return 'healthy'
  return 'all'
}

export default function Targets() {
  const { data: targets, error, isLoading, isRefreshing, refresh } = useDashboardQuery(getTargets, {
    pollInterval: 5000,
  })
  const { data: configurationHealth, refresh: refreshConfigurationHealth } = useDashboardQuery(getConfiguration, { pollInterval: 5000 })

  const [statusFilter, setStatusFilter] = useState(readStatusFilterFromUrl)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedTarget, setSelectedTarget] = useState(null)

  useEffect(() => {
    function onPopState() {
      setStatusFilter(readStatusFilterFromUrl())
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  function setFilter(newFilter) {
    setStatusFilter(newFilter)
    const url = new URL(window.location.href)
    if (newFilter === 'all') {
      url.searchParams.delete('status')
    } else {
      url.searchParams.set('status', newFilter)
    }
    window.history.pushState({}, '', url.pathname + url.search)
  }

  const rawList = Array.isArray(targets) ? targets : []

  const filteredTargets = rawList.filter((target) => {
    const isCircuitOpen = isCircuitOpenUntil(target.circuit_open_until)
    const isHealthy = Boolean(target.healthy) && !isCircuitOpen

    if (statusFilter === 'attention') {
      if (isHealthy) return false
    } else if (statusFilter === 'healthy') {
      if (!isHealthy) return false
    }

    if (searchTerm) {
      const term = searchTerm.toLowerCase()
      const matchesId = target.id && target.id.toLowerCase().includes(term)
      const matchesBackend = target.backend && target.backend.toLowerCase().includes(term)
      const matchesModel = target.model && target.model.toLowerCase().includes(term)
      if (!matchesId && !matchesBackend && !matchesModel) return false
    }

    return true
  })

  const columns = [
    {
      key: 'id',
      header: 'Identifier',
      width: '180px',
      render: (row) => <strong>{row.id}</strong>,
    },
    {
      key: 'backend',
      header: 'Backend',
      width: '140px',
      render: (row) => <span>{row.backend || 'default'}</span>,
    },
    {
      key: 'model',
      header: 'Model',
      width: '200px',
      render: (row) => <code className="cell-code">{row.model}</code>,
    },
    {
      key: 'isolated',
      header: 'Isolation',
      width: '120px',
      render: (row) => <span>{row.isolated ? 'Isolated' : 'Shared'}</span>,
    },
    {
      key: 'read_only',
      header: 'Access',
      width: '120px',
      render: (row) => <span>{row.read_only ? 'Read-only' : 'Read-write'}</span>,
    },
    {
      key: 'max_concurrency',
      header: 'Concurrency',
      width: '120px',
      render: (row) => <span>{row.max_concurrency}</span>,
    },
    {
      key: 'active',
      header: 'Active jobs',
      width: '120px',
      render: (row) => <span>{row.active}</span>,
    },
    {
      key: 'health',
      header: 'Health',
      width: '180px',
      render: (row) => {
        let status = 'healthy'
        let label = 'Healthy'
        if (isCircuitOpenUntil(row.circuit_open_until)) {
          status = 'circuit-open'
          label = 'Circuit open'
        } else if (!row.healthy) {
          status = 'unhealthy'
          label = 'Unhealthy'
        }
        return <StatusBadge status={status} label={label} />
      },
    },
  ]

  const attentionCount = rawList.filter((t) => !t.healthy || isCircuitOpenUntil(t.circuit_open_until)).length
  const healthyCount = rawList.filter((t) => t.healthy && !isCircuitOpenUntil(t.circuit_open_until)).length
  const selectedCircuitOpen = selectedTarget && isCircuitOpenUntil(selectedTarget.circuit_open_until)

  return (
    <div className="page">
      <PageHeader
        title="Targets"
        description="Configured execution targets and runtime availability."
        actions={
          <button
            type="button"
            className="button button-ghost button-sm"
            onClick={() => {
              refresh()
              refreshConfigurationHealth()
            }}
            disabled={isRefreshing}
          >
            {isRefreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        }
      />

      <ConfigurationHealthBanner health={configurationHealth} />

      {error && !targets && (
        <Alert tone="error" title="Unable to load targets">
          {error.message || 'Failed to fetch target runtime status.'}
        </Alert>
      )}

      {error && targets && (
        <Alert tone="warning" title="Background refresh failed">
          Showing previously loaded target status. {error.message || 'Network error'}.
        </Alert>
      )}

      <div className="targets-toolbar">
        <div className="filter-button-group" role="group" aria-label="Status filter">
          <button
            type="button"
            className={`filter-btn ${statusFilter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            All <span className="tab-count">{rawList.length}</span>
          </button>
          <button
            type="button"
            className={`filter-btn ${statusFilter === 'attention' ? 'active' : ''}`}
            onClick={() => setFilter('attention')}
          >
            Needing attention <span className="tab-count">{attentionCount}</span>
          </button>
          <button
            type="button"
            className={`filter-btn ${statusFilter === 'healthy' ? 'active' : ''}`}
            onClick={() => setFilter('healthy')}
          >
            Healthy <span className="tab-count">{healthyCount}</span>
          </button>
        </div>

        <input
          type="search"
          className="search-input"
          placeholder="Filter targets…"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          aria-label="Filter targets"
        />
      </div>

      <div className="targets-layout">
        <div className="targets-table-area">
          <DataGrid
            columns={columns}
            rows={filteredTargets}
            rowKey={(r) => r.id}
            onRowClick={(row) => setSelectedTarget(row)}
            emptyMessage={
              statusFilter !== 'all' || searchTerm
                ? 'No targets match the active filter.'
                : 'No execution targets configured.'
            }
            recoveryAction={
              statusFilter !== 'all' || searchTerm ? (
                <button
                  type="button"
                  className="button button-secondary button-sm"
                  onClick={() => {
                    setFilter('all')
                    setSearchTerm('')
                  }}
                >
                  Clear filters
                </button>
              ) : null
            }
            ariaLabel="Execution targets table"
            isLoading={isLoading}
          />
        </div>

        {selectedTarget && (
          <div className="targets-inspector-area">
            <Inspector
              title={`Target: ${selectedTarget.id}`}
              description={`Backend: ${selectedTarget.backend || 'default'}`}
              onClose={() => setSelectedTarget(null)}
            >
              <InspectorRow label="Target ID" value={selectedTarget.id} />
              <InspectorRow label="Backend" value={selectedTarget.backend || 'default'} />
              <InspectorRow label="Model" value={selectedTarget.model} />
              <InspectorRow
                label="Isolation"
                value={selectedTarget.isolated ? 'Isolated process' : 'Shared process'}
              />
              <InspectorRow
                label="Access"
                value={selectedTarget.read_only ? 'Read-only' : 'Read-write'}
              />
              <InspectorRow
                label="Concurrency limit"
                value={`${selectedTarget.max_concurrency} concurrent job${selectedTarget.max_concurrency === 1 ? '' : 's'}`}
              />
              <InspectorRow label="Active jobs" value={selectedTarget.active} />
              <InspectorRow label="Status">
                <StatusBadge
                  status={
                    selectedCircuitOpen
                      ? 'circuit-open'
                      : selectedTarget.healthy
                        ? 'healthy'
                        : 'unhealthy'
                  }
                  label={
                    selectedCircuitOpen
                      ? 'Circuit open'
                      : selectedTarget.healthy
                        ? 'Healthy'
                        : 'Unhealthy'
                  }
                />
              </InspectorRow>
              {selectedCircuitOpen && (
                <InspectorRow
                  label="Circuit open until"
                  value={selectedTarget.circuit_open_until}
                />
              )}
            </Inspector>
          </div>
        )}
      </div>
    </div>
  )
}
