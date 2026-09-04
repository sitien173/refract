import { useEffect, useState } from 'react'
import { getContextInstructions, getProjects } from '../api'
import Alert from '../components/Alert'
import ContextInstructionEditor from '../components/ContextInstructionEditor'
import DataGrid from '../components/DataGrid'
import PageHeader from '../components/PageHeader'
import { useDashboardQuery } from '../hooks/useDashboardQuery'

const BUILTIN_WORKFLOWS = ['consult', 'implement', 'other', 'review']

export default function ContextInstructions({ projectId: propProjectId, onNavigate }) {
  const [selectedProjectId, setSelectedProjectId] = useState(propProjectId || '')
  const [projectsList, setProjectsList] = useState([])
  const [announcement, setAnnouncement] = useState('')
  const [localInstructions, setLocalInstructions] = useState(null)
  const [editorState, setEditorState] = useState({
    isOpen: false,
    workflow: '',
    currentInstruction: '',
    mode: 'edit',
  })

  useEffect(() => {
    if (propProjectId) {
      setSelectedProjectId(propProjectId)
      return
    }
    const params = new URLSearchParams(window.location.search)
    const qProject = params.get('project')
    if (qProject) {
      setSelectedProjectId(qProject)
    } else {
      getProjects()
        .then((projects) => {
          if (Array.isArray(projects) && projects.length > 0) {
            setProjectsList(projects)
            setSelectedProjectId(projects[0].id)
          }
        })
        .catch(() => {})
    }
  }, [propProjectId])

  const activeProjectId = propProjectId || selectedProjectId

  const {
    data: fetchedData,
    error,
    isLoading,
    refresh,
  } = useDashboardQuery(
    () => (activeProjectId ? getContextInstructions(activeProjectId) : Promise.resolve(null)),
    { deps: [activeProjectId] }
  )

  useEffect(() => {
    if (fetchedData) {
      const instructions = fetchedData.instructions || fetchedData.context_instructions || fetchedData || {}
      setLocalInstructions(instructions)
    }
  }, [fetchedData])

  const instructionsMap = localInstructions || fetchedData?.instructions || fetchedData?.context_instructions || {}
  const workflowKeys = Array.from(new Set([...BUILTIN_WORKFLOWS, ...Object.keys(instructionsMap)])).sort()

  const rows = workflowKeys.map((wf) => {
    const instruction = typeof instructionsMap[wf] === 'string' ? instructionsMap[wf] : ''
    return {
      id: wf,
      workflow: wf,
      instruction,
      isConfigured: Boolean(instruction && instruction.trim()),
    }
  })

  function handleOpenEditor(workflow, instruction, mode = 'edit') {
    setEditorState({
      isOpen: true,
      workflow,
      currentInstruction: instruction,
      mode,
    })
  }

  function handleCloseEditor() {
    setEditorState((prev) => ({ ...prev, isOpen: false }))
  }

  function handleSaved({ workflow, instruction }) {
    setLocalInstructions((prev) => ({
      ...(prev || {}),
      [workflow]: instruction,
    }))
    refresh()
  }

  function handleProjectChange(newId) {
    setSelectedProjectId(newId)
    setLocalInstructions(null)
    const url = new URL(window.location.href)
    url.searchParams.set('project', newId)
    window.history.pushState({}, '', url.pathname + url.search)
  }

  const columns = [
    {
      key: 'workflow',
      header: 'Workflow',
      width: '160px',
      render: (row) => <strong>{row.workflow}</strong>,
    },
    {
      key: 'instruction',
      header: 'Context instruction',
      width: '420px',
      render: (row) =>
        row.isConfigured ? (
          <span className="context-preview" title={row.instruction}>
            {row.instruction}
          </span>
        ) : (
          <span className="context-empty">No custom instruction</span>
        ),
    },
    {
      key: 'status',
      header: 'Status',
      width: '140px',
      render: (row) => (
        <span className={`status-pill ${row.isConfigured ? 'status-pill-configured' : 'status-pill-default'}`}>
          {row.isConfigured ? 'Configured' : 'Default'}
        </span>
      ),
    },
    {
      key: 'actions',
      header: 'Actions',
      width: '200px',
      render: (row) => (
        <div className="table-actions">
          {row.isConfigured ? (
            <>
              <button
                type="button"
                className="button button-secondary button-sm"
                onClick={() => handleOpenEditor(row.workflow, row.instruction, 'edit')}
                aria-label={`Edit ${row.workflow} context instruction`}
              >
                Edit
              </button>
              <button
                type="button"
                className="button button-destructive-outline button-sm"
                onClick={() => handleOpenEditor(row.workflow, row.instruction, 'clear')}
                aria-label={`Clear ${row.workflow} context instruction`}
              >
                Clear
              </button>
            </>
          ) : (
            <button
              type="button"
              className="button button-secondary button-sm"
              onClick={() => handleOpenEditor(row.workflow, '', 'add')}
              aria-label={`Add instruction for ${row.workflow}`}
            >
              Add instruction
            </button>
          )}
        </div>
      ),
    },
  ]

  return (
    <div className="context-instructions-view">
      {/* Persistent polite live region for accessible status announcements */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>

      {!propProjectId && (
        <PageHeader
          title="Context instructions"
          description="Manage durable worker context instructions for project workflows."
          actions={
            <div className="header-actions-group">
              {projectsList.length > 0 && (
                <label className="header-select-label">
                  <span className="eyebrow">Project:</span>
                  <select
                    className="profile-select"
                    value={activeProjectId}
                    onChange={(e) => handleProjectChange(e.target.value)}
                    aria-label="Select project workspace"
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
      )}

      {error && (
        <Alert tone="error" title="Unable to load context instructions" role="alert">
          {error.message || 'Failed to fetch context instructions for this project workspace.'}
        </Alert>
      )}

      <div className="context-instructions-notice">
        <p className="caption">
          Context instructions are injected into agent executions for matching workflows.
          Configuration changes affect newly submitted jobs only.
        </p>
      </div>

      <DataGrid
        columns={columns}
        rows={rows}
        rowKey={(r) => r.id}
        emptyMessage="No workflows available."
        ariaLabel="Context instructions table"
        isLoading={isLoading && !localInstructions}
      />

      {editorState.isOpen && (
        <ContextInstructionEditor
          projectId={activeProjectId}
          workflow={editorState.workflow}
          currentInstruction={editorState.currentInstruction}
          isOpen={editorState.isOpen}
          mode={editorState.mode}
          onClose={handleCloseEditor}
          onSaved={handleSaved}
          onAnnounce={setAnnouncement}
        />
      )}
    </div>
  )
}
