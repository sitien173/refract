import { useEffect, useState } from 'react'
import { getProject, getProjectJobs, getTaskGuide } from '../api'
import Alert from '../components/Alert'
import DataGrid from '../components/DataGrid'
import Inspector, { InspectorRow, SourceChip } from '../components/Inspector'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import TabbedPanel from '../components/TabbedPanel'
import { useDashboardQuery } from '../hooks/useDashboardQuery'

export default function ProjectDetail({ projectId, onNavigate }) {
  const {
    data: projectData,
    error: projectError,
    isLoading: isProjectLoading,
    refresh: refreshProject,
  } = useDashboardQuery(() => getProject(projectId), {
    deps: [projectId],
  })

  const { data: taskGuideData } = useDashboardQuery(() => getTaskGuide(projectId), {
    deps: [projectId],
  })

  const { data: jobsData, error: jobsError, refresh: refreshJobs } = useDashboardQuery(() => getProjectJobs(projectId), {
    deps: [projectId],
    pollInterval: 5000,
  })

  const [activeTab, setActiveTab] = useState('effective')
  const [selectedWorkflowItem, setSelectedWorkflowItem] = useState(null)
  const [selectedJob, setSelectedJob] = useState(null)
  const [selectedProfileId, setSelectedProfileId] = useState('')

  const project = projectData?.project || { id: projectId, alias: projectId, root: '' }
  const configData = projectData?.configuration || {}
  const profiles = configData.profiles || []
  const defaultProfileId =
    configData.project_default_profile || configData.global_default_profile || (profiles[0]?.id ?? 'default')

  const currentProfileId = selectedProfileId || defaultProfileId
  const activeProfile = profiles.find((p) => p.id === currentProfileId) || profiles[0] || {
    id: currentProfileId,
    parent: { value: null, source: 'global' },
    declared: {},
    inherited: {},
    effective: {},
    sources: {},
  }

  function handleNavigate(path) {
    if (onNavigate) {
      onNavigate(path)
    } else {
      window.history.pushState({}, '', path)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }
  }

  // Build effective workflow rows from activeProfile.effective (never concatenate declared + inherited)
  const effectiveRows = Object.keys(activeProfile.effective || {})
    .sort()
    .map((workflow) => {
      const selection = activeProfile.effective[workflow] || {}
      const isInherited = Boolean(activeProfile.inherited && activeProfile.inherited[workflow])
      const isDeclared = !isInherited && Boolean(activeProfile.declared && activeProfile.declared[workflow])
      const source = activeProfile.sources?.[workflow] || (isDeclared ? activeProfile.declared[workflow]?.source : 'global') || 'global'
      return {
        id: workflow,
        workflow,
        profile: activeProfile.id,
        targets: Array.isArray(selection.targets) ? selection.targets.join(', ') : '',
        rawTargets: selection.targets || [],
        maxAttempts: selection.max_attempts ?? 1,
        timeoutS: selection.timeout_s ?? 60,
        source,
        provenance: isDeclared ? 'Declared' : 'Inherited',
      }
    })

  const effectiveColumns = [
    {
      key: 'workflow',
      header: 'Workflow',
      width: '180px',
      render: (row) => <strong>{row.workflow}</strong>,
    },
    {
      key: 'profile',
      header: 'Declared profile',
      width: '180px',
      render: (row) => <span className="profile-tag">{row.profile}</span>,
    },
    {
      key: 'targets',
      header: 'Effective targets',
      width: '260px',
      render: (row) => <code className="cell-code">{row.targets}</code>,
    },
    {
      key: 'source',
      header: 'Source',
      width: '160px',
      render: (row) => <SourceChip source={row.source} />,
    },
    {
      key: 'maxAttempts',
      header: 'Attempts',
      width: '100px',
      render: (row) => <span>{row.maxAttempts}</span>,
    },
    {
      key: 'timeoutS',
      header: 'Timeout',
      width: '100px',
      render: (row) => <span>{row.timeoutS}s</span>,
    },
  ]

  const profileResolutionColumns = [
    {
      key: 'workflow',
      header: 'Workflow',
      width: '160px',
      render: (row) => <strong>{row.workflow}</strong>,
    },
    {
      key: 'provenance',
      header: 'Provenance',
      width: '140px',
      render: (row) => (
        <span className={`provenance-tag ${row.provenance === 'Declared' ? 'provenance-declared' : 'provenance-inherited'}`}>
          {row.provenance}
        </span>
      ),
    },
    {
      key: 'targets',
      header: 'Effective targets',
      width: '240px',
      render: (row) => <code className="cell-code">{row.targets}</code>,
    },
    {
      key: 'maxAttempts',
      header: 'Attempts',
      width: '100px',
      render: (row) => <span>{row.maxAttempts}</span>,
    },
    {
      key: 'timeoutS',
      header: 'Timeout',
      width: '100px',
      render: (row) => <span>{row.timeoutS}s</span>,
    },
    {
      key: 'source',
      header: 'Source',
      width: '160px',
      render: (row) => <SourceChip source={row.source} />,
    },
  ]

  const jobsColumns = [
    {
      key: 'id',
      header: 'Job ID',
      width: '200px',
      render: (row) => <code className="cell-code">{row.id}</code>,
    },
    {
      key: 'workflow',
      header: 'Workflow',
      width: '140px',
      render: (row) => <span>{row.workflow}</span>,
    },
    {
      key: 'profile',
      header: 'Profile',
      width: '140px',
      render: (row) => <span className="profile-tag">{row.profile}</span>,
    },
    {
      key: 'state',
      header: 'State',
      width: '140px',
      render: (row) => <StatusBadge status={row.state} label={row.state} />,
    },
    {
      key: 'target_id',
      header: 'Target',
      width: '160px',
      render: (row) => <span>{row.target_id || '—'}</span>,
    },
    {
      key: 'config_revision',
      header: 'Config revision',
      width: '180px',
      render: (row) => (
        <code className="cell-code">
          {row.config_revision ? row.config_revision.slice(0, 12) : 'Unavailable'}
        </code>
      ),
    },
    {
      key: 'created_at',
      header: 'Created at',
      width: '180px',
      render: (row) => <span className="caption">{row.created_at}</span>,
    },
  ]

  const contextInstructions = projectData?.context_instructions || {}
  const contextWorkflows = ['consult', 'implement', 'review', 'research', 'plan', 'debug']
  const contextRows = contextWorkflows.map((wf) => ({
    id: wf,
    workflow: wf,
    instruction: contextInstructions[wf] || '',
  }))

  const contextColumns = [
    {
      key: 'workflow',
      header: 'Workflow',
      width: '180px',
      render: (row) => <strong>{row.workflow}</strong>,
    },
    {
      key: 'instruction',
      header: 'Instruction',
      width: '500px',
      render: (row) =>
        row.instruction ? (
          <span className="context-preview">{row.instruction}</span>
        ) : (
          <span className="context-empty">No custom instruction</span>
        ),
    },
    {
      key: 'status',
      header: 'Status',
      width: '140px',
      render: (row) => (
        <span className="caption">{row.instruction ? 'Configured' : 'Default'}</span>
      ),
    },
  ]

  const tabs = [
    { id: 'effective', label: 'Effective configuration' },
    { id: 'profiles', label: 'Profile resolution', count: profiles.length },
    { id: 'guidance', label: 'Task guidance' },
    { id: 'context', label: 'Context instructions' },
    { id: 'jobs', label: 'Jobs', count: Array.isArray(jobsData) ? jobsData.length : undefined },
  ]

  const hasParent = Boolean(activeProfile.parent && activeProfile.parent.value)
  const parentValue = hasParent ? activeProfile.parent.value : 'No parent'

  return (
    <div className="page">
      <PageHeader
        title={project.alias || project.id}
        description={project.root || 'Project workspace'}
        backLink={
          <a
            href="/dashboard/projects"
            className="back-link"
            onClick={(e) => {
              if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
              e.preventDefault()
              handleNavigate('/dashboard/projects')
            }}
          >
            ← Back to projects
          </a>
        }
        actions={
          <button
            type="button"
            className="button button-ghost button-sm"
            onClick={() => {
              refreshProject()
              refreshJobs()
            }}
            disabled={isProjectLoading}
          >
            {isProjectLoading ? 'Loading…' : 'Refresh'}
          </button>
        }
      />

      {projectError && !projectData && (
        <Alert tone="error" title="Configuration error">
          <span>{projectError.message || 'Unable to load project configuration.'} </span>
          {projectError.payload?.source_path && (
            <div className="alert-path">
              <code>{projectError.payload.source_path}</code>
            </div>
          )}
        </Alert>
      )}
      {projectError && projectData && (
        <Alert tone="warning" title="Showing previously loaded project configuration">
          Background refresh failed. The project view remains unchanged; retry when the daemon is available.
        </Alert>
      )}

      <div className="project-detail-layout">
        <div className="project-detail-main">
          <TabbedPanel tabs={tabs} activeTab={activeTab} onTabChange={setActiveTab}>
            {activeTab === 'effective' && (
              <div className="tab-section">
                <div className="tab-section-header">
                  <div className="profile-selector-group">
                    <label htmlFor="effective-profile-select" className="eyebrow">
                      Active profile
                    </label>
                    <select
                      id="effective-profile-select"
                      className="profile-select"
                      value={currentProfileId}
                      onChange={(e) => setSelectedProfileId(e.target.value)}
                    >
                      {profiles.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.id} {p.id === defaultProfileId ? '(default)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <DataGrid
                  columns={effectiveColumns}
                  rows={effectiveRows}
                  rowKey={(r) => r.id}
                  onRowClick={(row) => setSelectedWorkflowItem(row)}
                  emptyMessage="No effective workflows resolved for this profile."
                  ariaLabel="Effective configuration table"
                  isLoading={isProjectLoading}
                />
              </div>
            )}

            {activeTab === 'profiles' && (
              <div className="tab-section">
                <div className="profile-resolution-header">
                  <div className="profile-selector-group">
                    <label htmlFor="resolution-profile-select" className="eyebrow">
                      Select profile
                    </label>
                    <select
                      id="resolution-profile-select"
                      className="profile-select"
                      value={currentProfileId}
                      onChange={(e) => setSelectedProfileId(e.target.value)}
                    >
                      {profiles.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.id} {p.id === defaultProfileId ? '(default)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="profile-parent-info">
                    <span className="eyebrow">Parent profile</span>
                    <div className="parent-badge-row">
                      <strong>{parentValue}</strong>
                      {hasParent && <SourceChip source={activeProfile.parent.source} />}
                    </div>
                  </div>
                </div>

                <DataGrid
                  columns={profileResolutionColumns}
                  rows={effectiveRows}
                  rowKey={(r) => r.id}
                  onRowClick={(row) => setSelectedWorkflowItem(row)}
                  emptyMessage="No workflows configured for this profile."
                  ariaLabel="Profile resolution table"
                  isLoading={isProjectLoading}
                />
              </div>
            )}

            {activeTab === 'guidance' && (
              <div className="tab-section">
                <section className="panel task-guide-panel">
                  <div className="panel-header">
                    <span className="eyebrow">Task guidance source</span>
                    <code>{taskGuideData?.source_path || 'Default built-in guide'}</code>
                  </div>
                  <div className="task-guide-content">
                    {taskGuideData?.guide ? (
                      <pre className="code-block">{JSON.stringify(taskGuideData.guide, null, 2)}</pre>
                    ) : (
                      <p className="empty-message">No custom task guidance found for this project.</p>
                    )}
                  </div>
                </section>
              </div>
            )}

            {activeTab === 'context' && (
              <div className="tab-section">
                <div className="tab-section-header">
                  <p className="caption">
                    Context instructions provide persistent guidance to agents on future jobs.
                  </p>
                </div>
                <DataGrid
                  columns={contextColumns}
                  rows={contextRows}
                  rowKey={(r) => r.id}
                  emptyMessage="No context instructions configured."
                  ariaLabel="Context instructions table"
                  isLoading={isProjectLoading}
                />
              </div>
            )}

            {activeTab === 'jobs' && (
              <div className="tab-section">
                {jobsError && jobsData && (
                  <Alert tone="warning" title="Showing previously loaded jobs">
                    Background refresh failed. The jobs table remains unchanged; retry when the daemon is available.
                  </Alert>
                )}
                <DataGrid
                  columns={jobsColumns}
                  rows={jobsData || []}
                  rowKey={(r) => r.id}
                  onRowClick={(row) => setSelectedJob(row)}
                  emptyMessage="No jobs submitted for this project workspace yet."
                  ariaLabel="Project jobs table"
                  isLoading={!jobsData}
                />
              </div>
            )}
          </TabbedPanel>
        </div>

        {selectedWorkflowItem && (
          <div className="project-detail-inspector">
            <Inspector
              title={`Workflow: ${selectedWorkflowItem.workflow}`}
              description={`Resolved configuration in profile "${selectedWorkflowItem.profile}".`}
              source={selectedWorkflowItem.source}
              onClose={() => setSelectedWorkflowItem(null)}
            >
              <InspectorRow label="Workflow" value={selectedWorkflowItem.workflow} />
              <InspectorRow label="Declared profile" value={selectedWorkflowItem.profile} />
              <InspectorRow label="Provenance" value={selectedWorkflowItem.provenance} />
              <InspectorRow label="Effective targets" value={selectedWorkflowItem.targets} />
              <InspectorRow label="Max attempts" value={selectedWorkflowItem.maxAttempts} />
              <InspectorRow label="Timeout" value={`${selectedWorkflowItem.timeoutS} seconds`} />
              <InspectorRow label="Source origin">
                <SourceChip source={selectedWorkflowItem.source} />
              </InspectorRow>
            </Inspector>
          </div>
        )}

        {selectedJob && (
          <div className="project-detail-inspector">
            <Inspector
              title={`Job ${selectedJob.id}`}
              description={`Workflow: ${selectedJob.workflow} (${selectedJob.profile})`}
              onClose={() => setSelectedJob(null)}
            >
              <InspectorRow label="Job ID" value={selectedJob.id} />
              <InspectorRow label="State">
                <StatusBadge status={selectedJob.state} label={selectedJob.state} />
              </InspectorRow>
              <InspectorRow label="Workflow" value={selectedJob.workflow} />
              <InspectorRow label="Profile" value={selectedJob.profile} />
              <InspectorRow label="Target" value={selectedJob.target_id || 'Unassigned'} />
              <InspectorRow
                label="Config revision"
                value={selectedJob.config_revision || 'Unavailable'}
              />
              <InspectorRow label="Attempts" value={selectedJob.attempts} />
              <InspectorRow label="Created at" value={selectedJob.created_at} />
              {selectedJob.result?.error && (
                <InspectorRow label="Error" value={selectedJob.result.error} />
              )}
            </Inspector>
          </div>
        )}
      </div>
    </div>
  )
}
