import { useProjectDetail } from '../hooks/useProjectDetail'
import Alert from '../components/Alert'
import ConfigurationHealthBanner from '../components/ConfigurationHealthBanner'
import DataGrid from '../components/DataGrid'
import Inspector, { InspectorRow, SourceChip } from '../components/Inspector'
import JobDetails from '../components/JobDetails'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import TabbedPanel from '../components/TabbedPanel'
import ProfileEditor from '../components/ProfileEditor'
import ConfigurationMutationDialog from '../components/ConfigurationMutationDialog'
export function getEffectiveTargetsSortValue(row) {
  if (!row) return ''
  if (Array.isArray(row.rawTargets)) {
    return row.rawTargets.join(', ')
  }
  return String(row.rawTargets ?? '')
}

export default function ProjectDetail({ projectId, jobId, onNavigate }) {
  const {
    projectData, projectError, isProjectLoading, refreshProject,
    refreshOverrides, taskGuideData, jobsData, jobsError, refreshJobs,
    configurationHealth, refreshConfigurationHealth,
    activeTab, setActiveTab, selectedWorkflowItem, setSelectedWorkflowItem,
    setSelectedProfileId, announcement, setAnnouncement,
    selectedJobId, fullJob, isJobLoading, jobFetchError, jobRefreshError, jobHeadingRef,
    jobSearchTerm, setJobSearchTerm, jobStateFilter, setJobStateFilter,
    jobWorkflowFilter, setJobWorkflowFilter, projectJobsList, totalProjectJobs,
    editorState, setEditorState, removeDialogState, setRemoveDialogState,
    project, profiles, defaultProfileId, currentProfileId, activeProfile, isOverridden,
    handleSelectJob, handleBackToJobs, handleRefreshSelectedJob,
    handleOpenCreateOverride, handleOpenEditOverride, handleOpenRemoveOverride,
    handleConfirmRemoveOverride, handleOverrideSaved, handleReloadRequired, handleNavigate,
  } = useProjectDetail({ projectId, jobId, onNavigate })

  // Build effective workflow rows from activeProfile.effective (never concatenate declared + inherited)
  const effectiveRows = Object.keys(activeProfile.effective || {})
    .sort((a, b) => a.localeCompare(b))
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
        timeoutS: selection.timeout_s ?? 60,
        source,
        provenance: isDeclared ? 'Declared' : 'Inherited',
      }
    })

  const effectiveColumns = [
    {
      key: 'workflow',
      header: 'Workflow',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.workflow,
      width: '160px',
      minWidth: '120px',
      render: (row) => <strong>{row.workflow}</strong>,
    },
    {
      key: 'profile',
      header: 'Declared profile',
      priority: 'secondary',
      sortable: true,
      sortAccessor: (row) => row.profile,
      width: '160px',
      minWidth: '120px',
      render: (row) => <span className="profile-tag">{row.profile}</span>,
    },
    {
      key: 'targets',
      header: 'Effective targets',
      priority: 'primary',
      sortable: true,
      sortAccessor: getEffectiveTargetsSortValue,
      width: '240px',
      minWidth: '160px',
      wrap: true,
      render: (row) => <code className="cell-code">{row.targets}</code>,
    },
    {
      key: 'source',
      header: 'Source',
      priority: 'secondary',
      sortable: true,
      sortAccessor: (row) => (typeof row.source === 'string' ? row.source : row.source?.scope || ''),
      width: '140px',
      minWidth: '110px',
      render: (row) => <SourceChip source={row.source} />,
    },
    {
      key: 'timeoutS',
      header: 'Timeout',
      priority: 'tertiary',
      sortable: true,
      sortAccessor: (row) => row.timeoutS ?? 0,
      width: '100px',
      minWidth: '80px',
      render: (row) => <span>{row.timeoutS}s</span>,
    },
  ]

  const profileResolutionColumns = [
    {
      key: 'workflow',
      header: 'Workflow',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.workflow,
      width: '160px',
      minWidth: '120px',
      render: (row) => <strong>{row.workflow}</strong>,
    },
    {
      key: 'provenance',
      header: 'Provenance',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.provenance,
      width: '140px',
      minWidth: '110px',
      render: (row) => (
        <span className={`provenance-tag ${row.provenance === 'Declared' ? 'provenance-declared' : 'provenance-inherited'}`}>
          {row.provenance}
        </span>
      ),
    },
    {
      key: 'targets',
      header: 'Effective targets',
      priority: 'primary',
      sortable: true,
      sortAccessor: getEffectiveTargetsSortValue,
      width: '240px',
      minWidth: '160px',
      wrap: true,
      render: (row) => <code className="cell-code">{row.targets}</code>,
    },
    {
      key: 'timeoutS',
      header: 'Timeout',
      priority: 'tertiary',
      sortable: true,
      sortAccessor: (row) => row.timeoutS ?? 0,
      width: '100px',
      minWidth: '80px',
      render: (row) => <span>{row.timeoutS}s</span>,
    },
    {
      key: 'source',
      header: 'Source',
      priority: 'secondary',
      sortable: true,
      sortAccessor: (row) => (typeof row.source === 'string' ? row.source : row.source?.scope || ''),
      width: '140px',
      minWidth: '110px',
      render: (row) => <SourceChip source={row.source} />,
    },
  ]

  const jobsColumns = [
    {
      key: 'id',
      header: 'Job ID',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.id,
      width: '180px',
      minWidth: '140px',
      render: (row) => (
        <a
          id={`job-link-${row.id}`}
          href={`/dashboard/projects/${encodeURIComponent(projectId)}/jobs/${encodeURIComponent(row.id)}`}
          className="table-link cell-code"
          onClick={(e) => {
            if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
            e.preventDefault()
            handleSelectJob(row.id)
          }}
        >
          {row.id}
        </a>
      ),
    },
    {
      key: 'workflow',
      header: 'Workflow',
      priority: 'primary',
      sortable: true,
      sortAccessor: (row) => row.workflow,
      width: '140px',
      minWidth: '110px',
      render: (row) => <span>{row.workflow}</span>,
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
      width: '180px',
      minWidth: '130px',
      render: (row) => (
        <div className="state-cell-container">
          <StatusBadge status={row.state} label={row.state} />
          {row.suspect && (
            <span
              className="suspect-badge"
              aria-label={`Job is suspect: ${row.diagnostic_count || 1} diagnostic report(s)`}
            >
              <span className="suspect-icon" aria-hidden="true">!</span>
              <span>Suspect</span>
            </span>
          )}
        </div>
      ),
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


  const tabs = [
    { id: 'effective', label: 'Effective configuration' },
    { id: 'profiles', label: 'Profile resolution', count: profiles.length },
    { id: 'guidance', label: 'Task guidance' },
    { id: 'jobs', label: 'Jobs', count: jobsData ? totalProjectJobs : undefined },
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
              refreshOverrides()
              refreshJobs()
              refreshConfigurationHealth()
            }}
            disabled={isProjectLoading}
          >
            {isProjectLoading ? 'Loading…' : 'Refresh'}
          </button>
        }
      />

      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>

      <ConfigurationHealthBanner health={configurationHealth} />

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

                  <div className="profile-parent-info">
                    <span className="eyebrow">Scope</span>
                    <div>
                      <span className={`source-chip ${isOverridden ? 'source-chip-declared' : 'source-chip-inherited'}`}>
                        {isOverridden ? 'Project override' : 'Global profile'}
                      </span>
                    </div>
                  </div>

                  <div className="profile-resolution-actions">
                    <button
                      type="button"
                      className="button button-primary button-sm"
                      onClick={() => handleOpenCreateOverride()}
                      aria-label="Create override"
                    >
                      Create override
                    </button>
                    {isOverridden ? (
                      <>
                        <button
                          type="button"
                          className="button button-secondary button-sm"
                          onClick={() => handleOpenEditOverride(currentProfileId)}
                          aria-label={`Edit override: ${currentProfileId}`}
                        >
                          Edit override
                        </button>
                        <button
                          type="button"
                          className="button button-destructive-outline button-sm"
                          onClick={() => handleOpenRemoveOverride(currentProfileId)}
                          aria-label={`Remove override: ${currentProfileId}`}
                        >
                          Remove override
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="button button-secondary button-sm"
                        onClick={() => handleOpenCreateOverride(currentProfileId)}
                        aria-label={`Override profile: ${currentProfileId}`}
                      >
                        Override this profile
                      </button>
                    )}
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

            {activeTab === 'jobs' && (
              <div className="tab-section">
                {selectedJobId ? (
                  <JobDetails
                    job={fullJob}
                    isLoading={isJobLoading}
                    error={jobFetchError}
                    refreshError={jobRefreshError}
                    onRefresh={handleRefreshSelectedJob}
                    onBack={handleBackToJobs}
                    onNavigate={onNavigate}
                    headingRef={jobHeadingRef}
                  />
                ) : (
                  <>
                    <div className="jobs-toolbar" aria-label="Jobs filters">
                      <input
                        type="search"
                        className="search-input"
                        placeholder="Search jobs by ID, workflow, profile, or target…"
                        value={jobSearchTerm}
                        onChange={(e) => setJobSearchTerm(e.target.value)}
                        aria-label="Search jobs"
                      />
                      <select
                        className="profile-select"
                        value={jobStateFilter}
                        onChange={(e) => setJobStateFilter(e.target.value)}
                        aria-label="Filter by job state"
                      >
                        <option value="all">All states</option>
                        <option value="running">running</option>
                        <option value="pending">pending</option>
                        <option value="queued">queued</option>
                        <option value="succeeded">succeeded</option>
                        <option value="failed">failed</option>
                        <option value="cancelled">cancelled</option>
                        <option value="interrupted">interrupted</option>
                      </select>
                      <select
                        className="profile-select"
                        value={jobWorkflowFilter}
                        onChange={(e) => setJobWorkflowFilter(e.target.value)}
                        aria-label="Filter by workflow"
                      >
                        <option value="all">All workflows</option>
                        <option value="consult">consult</option>
                        <option value="implement">implement</option>
                        <option value="review">review</option>
                        <option value="other">other</option>
                      </select>
                      {(jobSearchTerm || jobStateFilter !== 'all' || jobWorkflowFilter !== 'all') && (
                        <button
                          type="button"
                          className="button button-ghost button-sm"
                          onClick={() => {
                            setJobSearchTerm('')
                            setJobStateFilter('all')
                            setJobWorkflowFilter('all')
                          }}
                          aria-label="Clear filters"
                        >
                          Clear filters
                        </button>
                      )}
                    </div>

                    {jobsError && jobsData && (
                      <Alert tone="warning" title="Showing previously loaded jobs">
                        Background refresh failed. The jobs table remains unchanged; retry when the daemon is available.
                      </Alert>
                    )}
                    {jobsData?.more_recent > 0 && (
                      <p className="caption" role="status">
                        {jobsData.more_recent} older terminal jobs omitted from recent history.
                      </p>
                    )}

                    <DataGrid
                      columns={jobsColumns}
                      rows={
                        projectJobsList.filter((j) => {
                          if (jobStateFilter !== 'all' && j.state !== jobStateFilter) return false
                          if (jobWorkflowFilter !== 'all' && j.workflow !== jobWorkflowFilter) return false
                          if (jobSearchTerm.trim()) {
                            const q = jobSearchTerm.toLowerCase().trim()
                            const matchId = j.id?.toLowerCase().includes(q)
                            const matchWf = j.workflow?.toLowerCase().includes(q)
                            const matchProf = j.profile?.toLowerCase().includes(q)
                            const matchTarget = j.target_id?.toLowerCase().includes(q)
                            if (!matchId && !matchWf && !matchProf && !matchTarget) return false
                          }
                          return true
                        })
                      }
                      rowKey={(r) => r.id}
                      onRowClick={(row) => handleSelectJob(row.id)}
                      emptyMessage="No jobs submitted for this project workspace yet."
                      ariaLabel="Project jobs table"
                      isLoading={!jobsData}
                    />
                  </>
                )}
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
              <InspectorRow label="Timeout" value={`${selectedWorkflowItem.timeoutS} seconds`} />
              <InspectorRow label="Source origin">
                <SourceChip source={selectedWorkflowItem.source} />
              </InspectorRow>
            </Inspector>
          </div>
        )}
      </div>

      <ProfileEditor
        isOpen={editorState.isOpen}
        mode={editorState.mode}
        scope="project"
        projectId={projectId}
        profile={editorState.profile}
        revision={editorState.revision}
        availableTargets={editorState.availableTargets}
        availableProfiles={editorState.availableProfiles}
        workflows={taskGuideData?.workflows}
        onClose={() => setEditorState((prev) => ({ ...prev, isOpen: false }))}
        onSaved={handleOverrideSaved}
        onAnnounce={(msg) => setAnnouncement(msg)}
        onReloadRequired={handleReloadRequired}
      />

      <ConfigurationMutationDialog
        isOpen={removeDialogState.isOpen}
        title={`Remove override: ${removeDialogState.profileId}`}
        targetId={removeDialogState.profileId}
        entity="profile override"
        action="remove"
        references={removeDialogState.references}
        error={removeDialogState.error}
        isSubmitting={removeDialogState.isSubmitting}
        onClose={() => setRemoveDialogState((prev) => ({ ...prev, isOpen: false }))}
        onConfirm={handleConfirmRemoveOverride}
      >
        <div className="fallback-preview-panel" style={{ marginBottom: 'var(--space-md)' }}>
          <span className="eyebrow" style={{ display: 'block', marginBottom: 'var(--space-xs)' }}>
            Resulting global fallback policy
          </span>
          {removeDialogState.fallback ? (
            <div className="fallback-preview-content">
              <p className="caption" style={{ margin: '0 0 var(--space-xs) 0' }}>
                Parent profile: <strong>{removeDialogState.fallback.extends || '(None - base profile)'}</strong>
              </p>
              <div className="data-grid-container" tabIndex={0} role="region" aria-label="Resulting global fallback policy">
                <table className="data-grid-table data-table" style={{ width: '100%', fontSize: 'var(--type-text-xs-size)' }}>
                  <thead>
                    <tr>
                      <th scope="col">Workflow</th>
                      <th scope="col">Fallback targets</th>
                      <th scope="col">Timeout</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(taskGuideData?.workflows || []).map((wf) => {
                      const pol = removeDialogState.fallback.effective?.[wf]
                      return (
                        <tr key={wf}>
                          <td><strong>{wf}</strong></td>
                          <td><code>{pol?.targets ? pol.targets.join(', ') : '—'}</code></td>
                          <td>{pol?.timeout_s ?? 60}s</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <Alert tone="neutral" title="No global profile fallback">
              Profile <strong>{removeDialogState.profileId}</strong> does not exist in global configuration.
              Removing this override will completely remove the profile from this project.
            </Alert>
          )}
        </div>
      </ConfigurationMutationDialog>
    </div>
  )
}
