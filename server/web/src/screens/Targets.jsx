import { useEffect, useState } from 'react'
import {
  getConfiguration,
  getTargets,
  getConfigurationTargets,
  getConfigurationTarget,
  deleteConfigurationTarget,
  DashboardApiError,
} from '../api'
import Alert from '../components/Alert'
import ConfigurationHealthBanner from '../components/ConfigurationHealthBanner'
import ConfigurationMutationDialog from '../components/ConfigurationMutationDialog'
import DataGrid from '../components/DataGrid'
import Inspector, { InspectorRow } from '../components/Inspector'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import TargetEditor from '../components/TargetEditor'
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
  const [editorState, setEditorState] = useState({
    isOpen: false,
    mode: 'create',
    target: null,
    revision: '',
  })
  const [deleteDialogState, setDeleteDialogState] = useState({
    isOpen: false,
    targetId: '',
    revision: '',
    references: null,
    error: null,
    isSubmitting: false,
  })
  const [editorError, setEditorError] = useState(null)
  const [announcement, setAnnouncement] = useState('')

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
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.id,
      width: '180px',
      minWidth: '140px',
      render: (row) => <strong>{row.id}</strong>,
    },
    {
      key: 'backend',
      header: 'Backend',
      priority: 'secondary',
      sortable: true,
      sortAccessor: (row) => row.backend || 'default',
      width: '140px',
      minWidth: '100px',
      render: (row) => <span>{row.backend || 'default'}</span>,
    },
    {
      key: 'model',
      header: 'Model',
      priority: 'secondary',
      sortable: true,
      sortAccessor: (row) => row.model || '',
      width: '180px',
      minWidth: '130px',
      wrap: true,
      render: (row) => <code className="cell-code">{row.model}</code>,
    },
    {
      key: 'isolated',
      header: 'Isolation',
      priority: 'optional',
      sortable: true,
      sortAccessor: (row) => (row.isolated ? 'Isolated' : 'Shared'),
      width: '110px',
      minWidth: '90px',
      render: (row) => <span>{row.isolated ? 'Isolated' : 'Shared'}</span>,
    },
    {
      key: 'read_only',
      header: 'Access',
      priority: 'optional',
      sortable: true,
      sortAccessor: (row) => (row.read_only ? 'Read-only' : 'Read-write'),
      width: '110px',
      minWidth: '90px',
      render: (row) => <span>{row.read_only ? 'Read-only' : 'Read-write'}</span>,
    },
    {
      key: 'max_concurrency',
      header: 'Concurrency',
      priority: 'tertiary',
      sortable: true,
      sortAccessor: (row) => row.max_concurrency ?? 0,
      width: '120px',
      minWidth: '90px',
      render: (row) => <span>{row.max_concurrency}</span>,
    },
    {
      key: 'active',
      header: 'Active jobs',
      priority: 'secondary',
      sortable: true,
      sortAccessor: (row) => row.active ?? 0,
      width: '110px',
      minWidth: '90px',
      render: (row) => <span>{row.active}</span>,
    },
    {
      key: 'health',
      header: 'Health',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) =>
        isCircuitOpenUntil(row.circuit_open_until)
          ? 'circuit-open'
          : row.healthy
            ? 'healthy'
            : 'unhealthy',
      width: '160px',
      minWidth: '130px',
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

  async function handleOpenCreate() {
    setEditorError(null)
    try {
      const payload = await getConfigurationTargets()
      setEditorState({
        isOpen: true,
        mode: 'create',
        target: null,
        revision: payload.revision || '',
      })
    } catch (err) {
      setEditorError(err.message || 'Failed to load target configuration.')
    }
  }

  async function handleOpenEdit(targetId) {
    setEditorError(null)
    try {
      const payload = await getConfigurationTarget(targetId)
      setEditorState({
        isOpen: true,
        mode: 'edit',
        target: payload.target || null,
        revision: payload.revision || '',
      })
    } catch (err) {
      setEditorError(err.message || 'Failed to load target details.')
    }
  }

  async function handleOpenDelete(targetId) {
    setEditorError(null)
    try {
      const payload = await getConfigurationTargets()
      setDeleteDialogState({
        isOpen: true,
        targetId,
        revision: payload.revision || '',
        references: null,
        error: null,
        isSubmitting: false,
      })
    } catch (err) {
      setEditorError(err.message || 'Failed to prepare target deletion.')
    }
  }

  async function handleConfirmDelete() {
    setDeleteDialogState((prev) => ({ ...prev, isSubmitting: true, error: null }))
    try {
      await deleteConfigurationTarget(deleteDialogState.targetId, deleteDialogState.revision)
      setAnnouncement(`Target "${deleteDialogState.targetId}" deleted.`)
      const deletedId = deleteDialogState.targetId
      setDeleteDialogState({
        isOpen: false,
        targetId: '',
        revision: '',
        references: null,
        error: null,
        isSubmitting: false,
      })
      if (selectedTarget?.id === deletedId) {
        setSelectedTarget(null)
      }
      refresh()
      refreshConfigurationHealth()
    } catch (err) {
      if ((err instanceof DashboardApiError || err?.status === 409) && err?.payload?.code === 'referenced') {
        setDeleteDialogState((prev) => ({
          ...prev,
          isSubmitting: false,
          references: err.payload?.references || [],
        }))
      } else {
        setDeleteDialogState((prev) => ({
          ...prev,
          isSubmitting: false,
          error: err.payload?.error || err.message || 'Failed to delete target.',
        }))
      }
    }
  }

  function handleTargetSaved(result) {
    setEditorState((prev) => ({ ...prev, isOpen: false }))
    refresh()
    refreshConfigurationHealth()
    if (result.target && selectedTarget?.id === result.target.id) {
      setSelectedTarget((prev) => ({ ...prev, ...result.target }))
    }
  }

  async function handleReloadRequired() {
    refresh()
    refreshConfigurationHealth()
    if (editorState.isOpen) {
      if (editorState.mode === 'edit' && editorState.target?.id) {
        try {
          const payload = await getConfigurationTarget(editorState.target.id)
          setEditorState((prev) => ({
            ...prev,
            revision: payload.revision || '',
            target: payload.target || prev.target,
          }))
          return payload
        } catch {
          return null
        }
      } else {
        try {
          const payload = await getConfigurationTargets()
          setEditorState((prev) => ({
            ...prev,
            revision: payload.revision || '',
          }))
          return payload
        } catch {
          return null
        }
      }
    }
    return null
  }

  return (
    <div className="page">
      <PageHeader
        title="Targets"
        description="Configured execution targets and runtime availability."
        actions={
          <div className="header-actions-group">
            <button
              type="button"
              className="button button-primary button-sm"
              onClick={handleOpenCreate}
            >
              Create target
            </button>
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
          </div>
        }
      />

      <ConfigurationHealthBanner health={configurationHealth} />

      {editorError && (
        <Alert tone="error" title="Editor error">
          {editorError}
        </Alert>
      )}

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

              <div className="inspector-actions-group">
                <button
                  type="button"
                  className="button button-secondary button-sm"
                  onClick={() => handleOpenEdit(selectedTarget.id)}
                >
                  Edit target
                </button>
                <button
                  type="button"
                  className="button button-destructive-outline button-sm"
                  onClick={() => handleOpenDelete(selectedTarget.id)}
                >
                  Delete target
                </button>
              </div>
            </Inspector>
          </div>
        )}
      </div>

      <TargetEditor
        isOpen={editorState.isOpen}
        mode={editorState.mode}
        target={editorState.target}
        revision={editorState.revision}
        onClose={() => setEditorState((prev) => ({ ...prev, isOpen: false }))}
        onSaved={handleTargetSaved}
        onAnnounce={setAnnouncement}
        onReloadRequired={handleReloadRequired}
      />

      <ConfigurationMutationDialog
        isOpen={deleteDialogState.isOpen}
        targetId={deleteDialogState.targetId}
        references={deleteDialogState.references}
        error={deleteDialogState.error}
        isSubmitting={deleteDialogState.isSubmitting}
        onClose={() => setDeleteDialogState((prev) => ({ ...prev, isOpen: false }))}
        onConfirm={handleConfirmDelete}
      />

      {announcement && (
        <div className="sr-only" role="status" aria-live="polite">
          {announcement}
        </div>
      )}
    </div>
  )
}
