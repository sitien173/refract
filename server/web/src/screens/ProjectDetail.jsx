import { useEffect, useRef, useState } from 'react'
import {
  getConfiguration,
  getJob,
  getProject,
  getProjectJobs,
  getTaskGuide,
  getProjectProfileOverrides,
  getProjectProfileOverride,
  deleteProjectProfileOverride,
  getConfigurationProfile,
  DashboardApiError,
} from '../api'
import Alert from '../components/Alert'
import ConfigurationHealthBanner from '../components/ConfigurationHealthBanner'
import DataGrid from '../components/DataGrid'
import Inspector, { InspectorRow, SourceChip } from '../components/Inspector'
import JobDetails from '../components/JobDetails'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
import TabbedPanel from '../components/TabbedPanel'
import ProfileEditor from '../components/ProfileEditor'
import Modal from '../components/Modal'
import { useDashboardQuery } from '../hooks/useDashboardQuery'
import { usePolling } from '../hooks/usePolling'

const TERMINAL_STATES = new Set(['succeeded', 'failed', 'cancelled', 'interrupted'])

export function getEffectiveTargetsSortValue(row) {
  if (!row) return ''
  if (Array.isArray(row.rawTargets)) {
    return row.rawTargets.join(', ')
  }
  return String(row.rawTargets ?? '')
}

export default function ProjectDetail({ projectId, jobId: propJobId, onNavigate }) {
  const {
    data: projectData,
    error: projectError,
    isLoading: isProjectLoading,
    refresh: refreshProject,
  } = useDashboardQuery(() => getProject(projectId), {
    deps: [projectId],
    pollInterval: 5000,
  })

  const {
    data: projectOverridesData,
    refresh: refreshOverrides,
  } = useDashboardQuery(() => getProjectProfileOverrides(projectId), {
    deps: [projectId],
    pollInterval: 5000,
  })

  const { data: taskGuideData } = useDashboardQuery(() => getTaskGuide(projectId), {
    deps: [projectId],
  })

  const { data: jobsData, error: jobsError, refresh: refreshJobs } = useDashboardQuery(
    () => getProjectJobs(projectId),
    { deps: [projectId] }
  )
  const { data: configurationHealth, refresh: refreshConfigurationHealth } = useDashboardQuery(getConfiguration, { pollInterval: 5000 })

  const [activeTab, setActiveTab] = useState(propJobId ? 'jobs' : 'effective')
  const [selectedWorkflowItem, setSelectedWorkflowItem] = useState(null)
  const [selectedProfileId, setSelectedProfileId] = useState('')
  const [announcement, setAnnouncement] = useState('')
  const [selectedJobId, setSelectedJobId] = useState(propJobId || '')
  const [fullJob, setFullJob] = useState(null)
  const [isJobLoading, setIsJobLoading] = useState(false)
  const [jobFetchError, setJobFetchError] = useState(null)
  const [jobRefreshError, setJobRefreshError] = useState(null)
  const [jobSearchTerm, setJobSearchTerm] = useState('')
  const [jobStateFilter, setJobStateFilter] = useState('all')
  const [jobWorkflowFilter, setJobWorkflowFilter] = useState('all')

  const lastFocusedJobIdRef = useRef(null)
  const jobHeadingRef = useRef(null)

  useEffect(() => {
    if (propJobId) {
      setSelectedJobId(propJobId)
      setActiveTab('jobs')
    } else {
      setSelectedJobId('')
    }
  }, [propJobId])

  // Fetch full details only after selecting a job
  useEffect(() => {
    if (!selectedJobId) {
      setFullJob(null)
      setJobFetchError(null)
      setJobRefreshError(null)
      return
    }

    let cancelled = false
    setIsJobLoading(true)
    setJobFetchError(null)
    setJobRefreshError(null)

    getJob(selectedJobId)
      .then((res) => {
        if (cancelled) return
        if (!res || res.project_id !== projectId) {
          setJobFetchError(new Error('Job not found in this project.'))
          setFullJob(null)
        } else {
          setFullJob(res)
          setJobFetchError(null)
        }
      })
      .catch((err) => {
        if (cancelled) return
        setJobFetchError(err)
        setFullJob(null)
      })
      .finally(() => {
        if (!cancelled) {
          setIsJobLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [selectedJobId, projectId])

  // Poll selected active job every 5 seconds until terminal
  const isJobTerminal = fullJob ? TERMINAL_STATES.has(fullJob.state) : true
  usePolling(
    async () => {
      if (!selectedJobId || isJobTerminal) return
      try {
        const updated = await getJob(selectedJobId)
        if (updated.project_id !== projectId) {
          setJobFetchError(new Error('Job not found in this project.'))
          setFullJob(null)
          return
        }
        setFullJob(updated)
        setJobRefreshError(null)
      } catch (err) {
        setJobRefreshError(err.message || 'Background refresh failed.')
      }
    },
    5000,
    {
      enabled: Boolean(selectedJobId && !isJobTerminal),
      isTerminal: isJobTerminal,
      deps: [selectedJobId, isJobTerminal, projectId],
    }
  )

  // Poll project jobs list while at least one listed job is non-terminal
  const allJobsTerminal =
    Array.isArray(jobsData) && jobsData.length > 0 && jobsData.every((j) => TERMINAL_STATES.has(j.state))
  usePolling(refreshJobs, 5000, {
    enabled: Boolean(projectId && activeTab === 'jobs' && !selectedJobId && !allJobsTerminal),
    isTerminal: allJobsTerminal,
    deps: [projectId, activeTab, selectedJobId, allJobsTerminal],
  })

  // Focus detail heading after navigation into details
  useEffect(() => {
    if (selectedJobId && (fullJob || jobFetchError)) {
      jobHeadingRef.current?.focus()
    }
  }, [selectedJobId, Boolean(fullJob), Boolean(jobFetchError)])

  // Return focus to originating job link when returning to jobs list
  useEffect(() => {
    if (!selectedJobId && lastFocusedJobIdRef.current) {
      const targetId = lastFocusedJobIdRef.current
      lastFocusedJobIdRef.current = null
      setTimeout(() => {
        const link = document.getElementById(`job-link-${targetId}`)
        if (link) {
          link.focus()
        }
      }, 0)
    }
  }, [selectedJobId])

  function handleSelectJob(jobId) {
    lastFocusedJobIdRef.current = jobId
    const path = `/dashboard/projects/${encodeURIComponent(projectId)}/jobs/${encodeURIComponent(jobId)}`
    if (onNavigate) {
      onNavigate(path)
    } else {
      window.history.pushState({}, '', path)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }
    setSelectedJobId(jobId)
  }

  function handleBackToJobs() {
    const path = `/dashboard/projects/${encodeURIComponent(projectId)}`
    if (onNavigate) {
      onNavigate(path)
    } else {
      window.history.pushState({}, '', path)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }
    setSelectedJobId('')
    setFullJob(null)
    setJobFetchError(null)
    setJobRefreshError(null)
  }

  const handleRefreshSelectedJob = async () => {
    if (!selectedJobId) return
    setIsJobLoading(true)
    try {
      const updated = await getJob(selectedJobId)
      if (updated.project_id !== projectId) {
        setJobFetchError(new Error('Job not found in this project.'))
        setFullJob(null)
      } else {
        setFullJob(updated)
        setJobRefreshError(null)
        setJobFetchError(null)
      }
    } catch (err) {
      if (fullJob) {
        setJobRefreshError(err.message || 'Background refresh failed.')
      } else {
        setJobFetchError(err)
      }
    } finally {
      setIsJobLoading(false)
    }
  }
  const [editorState, setEditorState] = useState({
    isOpen: false,
    mode: 'create',
    profile: null,
    revision: '',
    availableTargets: [],
    availableProfiles: [],
  })
  const [removeDialogState, setRemoveDialogState] = useState({
    isOpen: false,
    profileId: '',
    revision: '',
    fallback: null,
    references: null,
    error: null,
    isSubmitting: false,
    isConfirmed: false,
  })

  const project = projectData?.project || { id: projectId, alias: projectId, root: '' }
  const configData = projectData?.configuration || {}
  const profiles = configData.profiles || []
  const defaultProfileId =
    configData.project_default_profile || configData.global_default_profile || (profiles[0]?.id ?? 'default')

  const currentProfileId = (profiles.some((p) => p.id === selectedProfileId) ? selectedProfileId : '') || defaultProfileId
  const activeProfile = profiles.find((p) => p.id === currentProfileId) || profiles[0] || {
    id: currentProfileId,
    parent: { value: null, source: 'global' },
    declared: {},
    inherited: {},
    effective: {},
    sources: {},
  }

  const overrides = projectOverridesData?.overrides || []
  const currentOverride = overrides.find((o) => o.id === currentProfileId)
  const isOverridden = Boolean(currentOverride) || activeProfile.parent.source === 'project' || Object.values(activeProfile.sources || {}).some((s) => s === 'project')

  async function handleOpenCreateOverride(prefillProfileId = '') {
    let rev = projectOverridesData?.revision ?? ''
    let targets = projectOverridesData?.available_targets || []
    let profs = profiles.map((p) => p.id)

    try {
      const overridesResp = await getProjectProfileOverrides(projectId)
      rev = overridesResp.revision ?? ''
      if (overridesResp.available_targets?.length) {
        targets = overridesResp.available_targets
      }
    } catch {
      // Keep fallback values
    }

    let initialProfile = null
    if (prefillProfileId) {
      initialProfile = {
        id: prefillProfileId,
        extends: prefillProfileId,
        declared: {},
        inherited: activeProfile?.effective || {},
        effective: activeProfile?.effective || {},
        sources: {},
      }
    }

    setEditorState({
      isOpen: true,
      mode: 'create',
      profile: initialProfile,
      revision: rev,
      availableTargets: targets,
      availableProfiles: profs,
    })
  }

  async function handleOpenEditOverride(profileId) {
    try {
      let rev = projectOverridesData?.revision ?? ''
      let targets = projectOverridesData?.available_targets || []
      let profs = profiles.map((p) => p.id)

      const [overrideResp, overridesListResp] = await Promise.all([
        getProjectProfileOverride(projectId, profileId),
        getProjectProfileOverrides(projectId).catch(() => null),
      ])

      if (overridesListResp) {
        rev = overridesListResp.revision ?? rev
        if (overridesListResp.available_targets?.length) {
          targets = overridesListResp.available_targets
        }
      }

      setEditorState({
        isOpen: true,
        mode: 'edit',
        profile: overrideResp.override || null,
        revision: overrideResp.revision ?? rev,
        availableTargets: targets,
        availableProfiles: profs,
      })
    } catch (err) {
      setAnnouncement(`Failed to load profile override: ${err.message || 'error'}`)
    }
  }

  async function handleOpenRemoveOverride(profileId) {
    try {
      let fallbackProfile = null
      try {
        const globalProfileResp = await getConfigurationProfile(profileId)
        fallbackProfile = globalProfileResp.profile || null
      } catch {
        fallbackProfile = null
      }

      let rev = projectOverridesData?.revision ?? ''
      try {
        const overridesResp = await getProjectProfileOverrides(projectId)
        rev = overridesResp.revision ?? rev
      } catch {
        // Fall back to existing revision
      }

      setRemoveDialogState({
        isOpen: true,
        profileId,
        revision: rev,
        fallback: fallbackProfile,
        references: null,
        error: null,
        isSubmitting: false,
        isConfirmed: false,
      })
    } catch (err) {
      setAnnouncement(`Failed to prepare override removal: ${err.message || 'error'}`)
    }
  }

  async function handleConfirmRemoveOverride() {
    setRemoveDialogState((prev) => ({ ...prev, isSubmitting: true, error: null }))
    try {
      await deleteProjectProfileOverride(
        projectId,
        removeDialogState.profileId,
        removeDialogState.revision
      )
      const removedId = removeDialogState.profileId
      setAnnouncement(`Profile override "${removedId}" removed.`)
      setRemoveDialogState({
        isOpen: false,
        profileId: '',
        revision: '',
        fallback: null,
        references: null,
        error: null,
        isSubmitting: false,
        isConfirmed: false,
      })
      refreshProject()
      refreshOverrides()
      refreshConfigurationHealth()
    } catch (err) {
      if ((err instanceof DashboardApiError || err?.status === 409) && err?.payload?.code === 'referenced') {
        setRemoveDialogState((prev) => ({
          ...prev,
          isSubmitting: false,
          references: err.payload?.references || [],
        }))
      } else {
        setRemoveDialogState((prev) => ({
          ...prev,
          isSubmitting: false,
          error: err.payload?.error || err.message || 'Failed to remove override.',
        }))
      }
    }
  }

  function handleOverrideSaved(result) {
    const savedId = result.override?.id || result.profile?.id
    if (savedId) {
      setSelectedProfileId(savedId)
    }
    refreshProject()
    refreshOverrides()
    refreshConfigurationHealth()
    setAnnouncement(`Profile override "${savedId || 'configuration'}" saved and active.`)
  }

  async function handleReloadRequired() {
    try {
      const overridesResp = await getProjectProfileOverrides(projectId)
      let currentOverride = null
      if (editorState.mode === 'edit' && editorState.profile?.id && Array.isArray(overridesResp.overrides)) {
        currentOverride = overridesResp.overrides.find((ov) => ov.id === editorState.profile.id)
      }
      setEditorState((prev) => ({
        ...prev,
        revision: overridesResp.revision ?? '',
        profile: currentOverride || prev.profile,
        availableTargets: overridesResp.available_targets || prev.availableTargets,
      }))
      setAnnouncement('Project configuration reloaded.')
      return {
        ...overridesResp,
        override: currentOverride,
        profile: currentOverride,
      }
    } catch (err) {
      setAnnouncement(`Failed to reload configuration: ${err.message || 'error'}`)
      return null
    }
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
      key: 'maxAttempts',
      header: 'Attempts',
      priority: 'tertiary',
      sortable: true,
      sortAccessor: (row) => row.maxAttempts ?? 0,
      width: '100px',
      minWidth: '80px',
      render: (row) => <span>{row.maxAttempts}</span>,
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
      key: 'maxAttempts',
      header: 'Attempts',
      priority: 'tertiary',
      sortable: true,
      sortAccessor: (row) => row.maxAttempts ?? 0,
      width: '100px',
      minWidth: '80px',
      render: (row) => <span>{row.maxAttempts}</span>,
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


  const tabs = [
    { id: 'effective', label: 'Effective configuration' },
    { id: 'profiles', label: 'Profile resolution', count: profiles.length },
    { id: 'guidance', label: 'Task guidance' },
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

                    <DataGrid
                      columns={jobsColumns}
                      rows={
                        (jobsData || []).filter((j) => {
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
              <InspectorRow label="Max attempts" value={selectedWorkflowItem.maxAttempts} />
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
        onClose={() => setEditorState((prev) => ({ ...prev, isOpen: false }))}
        onSaved={handleOverrideSaved}
        onAnnounce={(msg) => setAnnouncement(msg)}
        onReloadRequired={handleReloadRequired}
      />

      <Modal
        isOpen={removeDialogState.isOpen}
        onClose={() => setRemoveDialogState((prev) => ({ ...prev, isOpen: false }))}
        title={`Remove override: ${removeDialogState.profileId}`}
        role="dialog"
        ariaLabel={`Remove override: ${removeDialogState.profileId}`}
      >
        {removeDialogState.references && removeDialogState.references.length > 0 ? (
          <div className="mutation-dialog-referenced">
            <Alert tone="warning" title="Profile override is currently referenced">
              Project override <strong>{removeDialogState.profileId}</strong> cannot be removed because it is referenced by:
            </Alert>
            <div className="mutation-references-list" style={{ marginTop: 'var(--space-md)' }}>
              <div className="data-grid-container" tabIndex={0} role="region" aria-label="Blocking references for override">
                <table className="data-grid-table data-table" style={{ width: '100%' }}>
                  <thead>
                    <tr>
                      <th scope="col">Scope</th>
                      <th scope="col">Profile</th>
                      <th scope="col">Relationship</th>
                    </tr>
                  </thead>
                  <tbody>
                    {removeDialogState.references.map((ref, idx) => (
                      <tr key={idx}>
                        <td>
                          <span className="source-chip source-repository">Project</span>
                        </td>
                        <td>
                          <strong>{ref.profile_id || '(project default)'}</strong>
                        </td>
                        <td>
                          <code>{ref.relationship || ref.workflow || 'reference'}</code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <p className="caption" style={{ marginTop: 'var(--space-md)' }}>
              Update or remove these references in the project configuration before removing this override.
            </p>
            <div className="modal-actions" style={{ justifyContent: 'flex-end', marginTop: 'var(--space-lg)' }}>
              <button
                type="button"
                className="button button-secondary"
                onClick={() => setRemoveDialogState((prev) => ({ ...prev, isOpen: false }))}
              >
                Close
              </button>
            </div>
          </div>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (removeDialogState.isConfirmed && !removeDialogState.isSubmitting) {
                handleConfirmRemoveOverride()
              }
            }}
            className="mutation-dialog-confirm"
          >
            {removeDialogState.error && (
              <div style={{ marginBottom: 'var(--space-md)' }}>
                <Alert tone="error" title="Action failed">
                  {removeDialogState.error}
                </Alert>
              </div>
            )}

            <p style={{ margin: '0 0 var(--space-md) 0' }}>
              Are you sure you want to remove the project override for profile{' '}
              <strong>{removeDialogState.profileId}</strong>?
            </p>

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
                          <th scope="col">Attempts</th>
                          <th scope="col">Timeout</th>
                        </tr>
                      </thead>
                      <tbody>
                        {['consult', 'implement', 'review', 'other'].map((wf) => {
                          const pol = removeDialogState.fallback.effective?.[wf]
                          return (
                            <tr key={wf}>
                              <td><strong>{wf}</strong></td>
                              <td><code>{pol?.targets ? pol.targets.join(', ') : '—'}</code></td>
                              <td>{pol?.max_attempts ?? 1}</td>
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

            <div className="confirmation-group" style={{ marginBottom: 'var(--space-md)' }}>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={removeDialogState.isConfirmed}
                  onChange={(e) =>
                    setRemoveDialogState((prev) => ({ ...prev, isConfirmed: e.target.checked }))
                  }
                  disabled={removeDialogState.isSubmitting}
                  aria-label={`I confirm removing override for profile ${removeDialogState.profileId}`}
                />
                <span>
                  I confirm removing override for profile <strong>{removeDialogState.profileId}</strong>.
                </span>
              </label>
            </div>

            <div className="modal-actions">
              <button
                type="button"
                className="button button-secondary"
                onClick={() => setRemoveDialogState((prev) => ({ ...prev, isOpen: false }))}
                disabled={removeDialogState.isSubmitting}
              >
                Cancel
              </button>
              <div className="modal-actions-right">
                <button
                  type="submit"
                  className="button button-destructive-outline"
                  disabled={!removeDialogState.isConfirmed || removeDialogState.isSubmitting}
                >
                  {removeDialogState.isSubmitting ? 'Removing override…' : 'Remove override'}
                </button>
              </div>
            </div>
          </form>
        )}
      </Modal>
    </div>
  )
}
