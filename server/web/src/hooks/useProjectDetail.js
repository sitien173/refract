import { useEffect, useRef, useState } from 'react'
import { POLL_INTERVAL_MS } from './constants'
import {
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
import { useDashboardQuery } from './useDashboardQuery'
import { useConfiguration } from './useConfiguration'
import { usePolling } from './usePolling'

const TERMINAL_STATES = new Set(['succeeded', 'failed', 'cancelled', 'interrupted'])

export function useProjectDetail({ projectId, jobId: propJobId, onNavigate }) {
  const {
    data: projectData,
    error: projectError,
    isLoading: isProjectLoading,
    refresh: refreshProject,
  } = useDashboardQuery(() => getProject(projectId), {
    deps: [projectId],
    pollInterval: POLL_INTERVAL_MS,
  })

  const {
    data: projectOverridesData,
    refresh: refreshOverrides,
  } = useDashboardQuery(() => getProjectProfileOverrides(projectId), {
    deps: [projectId],
    pollInterval: POLL_INTERVAL_MS,
  })

  const { data: taskGuideData } = useDashboardQuery(() => getTaskGuide(projectId), {
    deps: [projectId],
  })

  const { data: jobsData, error: jobsError, refresh: refreshJobs } = useDashboardQuery(
    () => getProjectJobs(projectId),
    { deps: [projectId] }
  )
  const { data: configurationHealth, refresh: refreshConfigurationHealth } = useConfiguration()

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
  const activeRouteRef = useRef({ projectId, selectedJobId: propJobId || '' })
  activeRouteRef.current = { projectId, selectedJobId }

  // Clear selected/full job state when projectId changes
  useEffect(() => {
    setSelectedJobId(propJobId || '')
    setFullJob(null)
    setJobFetchError(null)
    setJobRefreshError(null)
    if (propJobId) {
      setActiveTab('jobs')
    }
  }, [projectId])

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

    const expectedProjectId = projectId
    const expectedJobId = selectedJobId

    getJob(selectedJobId)
      .then((res) => {
        if (
          cancelled ||
          activeRouteRef.current.projectId !== expectedProjectId ||
          activeRouteRef.current.selectedJobId !== expectedJobId
        ) {
          return
        }
        if (!res || res.project_id !== expectedProjectId) {
          setJobFetchError(new Error('Job not found in this project.'))
          setFullJob(null)
        } else {
          setFullJob(res)
          setJobFetchError(null)
        }
      })
      .catch((err) => {
        if (
          cancelled ||
          activeRouteRef.current.projectId !== expectedProjectId ||
          activeRouteRef.current.selectedJobId !== expectedJobId
        ) {
          return
        }
        setJobFetchError(err)
        setFullJob(null)
      })
      .finally(() => {
        if (
          !cancelled &&
          activeRouteRef.current.projectId === expectedProjectId &&
          activeRouteRef.current.selectedJobId === expectedJobId
        ) {
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
      const expectedProjectId = projectId
      const expectedJobId = selectedJobId
      try {
        const updated = await getJob(selectedJobId)
        if (
          activeRouteRef.current.projectId !== expectedProjectId ||
          activeRouteRef.current.selectedJobId !== expectedJobId
        ) {
          return
        }
        if (updated.project_id !== expectedProjectId) {
          setJobFetchError(new Error('Job not found in this project.'))
          setFullJob(null)
          return
        }
        setFullJob(updated)
        setJobRefreshError(null)
      } catch (err) {
        if (
          activeRouteRef.current.projectId !== expectedProjectId ||
          activeRouteRef.current.selectedJobId !== expectedJobId
        ) {
          return
        }
        setJobRefreshError(err.message || 'Background refresh failed.')
      }
    },
    POLL_INTERVAL_MS,
    {
      enabled: Boolean(selectedJobId && !isJobTerminal),
      isTerminal: isJobTerminal,
      deps: [selectedJobId, isJobTerminal, projectId],
    }
  )

  // Poll project jobs list while at least one listed job is non-terminal
  const activeJobs = jobsData?.active ?? []
  const recentJobs = jobsData?.recent ?? []
  const projectJobsList = [...activeJobs, ...recentJobs]
  const allJobsTerminal = Boolean(jobsData) && activeJobs.length === 0
  const totalProjectJobs = activeJobs.length + recentJobs.length + (jobsData?.more_recent ?? 0)
  usePolling(refreshJobs, POLL_INTERVAL_MS, {
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
    const expectedProjectId = projectId
    const expectedJobId = selectedJobId
    setIsJobLoading(true)
    try {
      const updated = await getJob(selectedJobId)
      if (
        activeRouteRef.current.projectId !== expectedProjectId ||
        activeRouteRef.current.selectedJobId !== expectedJobId
      ) {
        return
      }
      if (updated.project_id !== expectedProjectId) {
        setJobFetchError(new Error('Job not found in this project.'))
        setFullJob(null)
      } else {
        setFullJob(updated)
        setJobRefreshError(null)
        setJobFetchError(null)
      }
    } catch (err) {
      if (
        activeRouteRef.current.projectId !== expectedProjectId ||
        activeRouteRef.current.selectedJobId !== expectedJobId
      ) {
        return
      }
      if (fullJob) {
        setJobRefreshError(err.message || 'Background refresh failed.')
      } else {
        setJobFetchError(err)
      }
    } finally {
      if (
        activeRouteRef.current.projectId === expectedProjectId &&
        activeRouteRef.current.selectedJobId === expectedJobId
      ) {
        setIsJobLoading(false)
      }
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
  const isOverridden = overrides.some((o) => o.id === currentProfileId) || activeProfile.parent.source === 'project' || Object.values(activeProfile.sources || {}).includes('project')

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

  return {
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
  }
}
