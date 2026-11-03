import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { useHashRoute, navigateTo } from './router.js'
import { fetchProjects } from './api.js'
import { useOverview, useProjectJobs, useJob } from './hooks/usePolling.js'
import { StatusStrip } from './components/StatusStrip.jsx'
import { ConfigInvalidBanner } from './components/ConfigInvalidBanner.jsx'
import { NavRail } from './components/NavRail.jsx'
import { JobFeed } from './components/JobFeed.jsx'
import { JobInspector } from './components/JobInspector.jsx'
import { ProjectsView } from './views/ProjectsView.jsx'
import { TargetsView } from './views/TargetsView.jsx'
import { DiagnosticsView } from './views/DiagnosticsView.jsx'
import { RuntimeView } from './views/RuntimeView.jsx'

const STORAGE_PROJECT_KEY = 'refract_selected_project'

export function App() {
  const { route, params } = useHashRoute()

  // Polling overview for status strip (3s)
  const { data: overview, isStale: isOverviewStale, error: overviewError } = useOverview()

  // Projects list
  const [projects, setProjects] = useState([])
  const [selectedProjectId, setSelectedProjectId] = useState(() => {
    return localStorage.getItem(STORAGE_PROJECT_KEY) || ''
  })

  useEffect(() => {
    let active = true
    fetchProjects()
      .then((data) => {
        if (!active) return
        const list = Array.isArray(data) ? data : []
        setProjects(list)
        if (list.length > 0) {
          const stored = localStorage.getItem(STORAGE_PROJECT_KEY)
          if (!stored || !list.some((p) => p.id === stored)) {
            setSelectedProjectId(list[0].id)
            localStorage.setItem(STORAGE_PROJECT_KEY, list[0].id)
          } else {
            setSelectedProjectId(stored)
          }
        }
      })
      .catch(() => {})
    return () => {
      active = false
    }
  }, [])

  const handleSelectProject = useCallback((projectId) => {
    setSelectedProjectId(projectId)
    localStorage.setItem(STORAGE_PROJECT_KEY, projectId)
  }, [])

  // Job listing for selected project (2s polling)
  const isLiveView = route === 'jobs'
  const {
    data: projectJobsData,
  } = useProjectJobs(selectedProjectId, { enabled: isLiveView })

  const activeJobs = useMemo(() => projectJobsData?.active || [], [projectJobsData])
  const recentJobs = useMemo(() => projectJobsData?.recent || [], [projectJobsData])
  const moreRecent = projectJobsData?.more_recent || 0

  // Follow newest running job toggle
  const [followNewestRunning, setFollowNewestRunning] = useState(false)

  // Selected job id
  const routeJobId = params?.id || null
  const [localSelectedJobId, setLocalSelectedJobId] = useState(null)

  // Auto-follow newest running job
  useEffect(() => {
    if (followNewestRunning && activeJobs.length > 0) {
      const runningJob = activeJobs.find((j) => j.state === 'running')
      if (runningJob && runningJob.id !== routeJobId) {
        navigateTo(`jobs/${encodeURIComponent(runningJob.id)}`)
      }
    }
  }, [followNewestRunning, activeJobs, routeJobId])

  // Effective selected job id
  const effectiveJobId = useMemo(() => {
    if (routeJobId) return routeJobId
    if (localSelectedJobId) return localSelectedJobId
    if (activeJobs.length > 0) return activeJobs[0].id
    if (recentJobs.length > 0) return recentJobs[0].id
    return null
  }, [routeJobId, localSelectedJobId, activeJobs, recentJobs])

  const handleSelectJob = useCallback((jobId) => {
    setLocalSelectedJobId(jobId)
    navigateTo(`jobs/${encodeURIComponent(jobId)}`)
  }, [])

  // Polling selected job detail until terminal (2s)
  const {
    data: selectedJob,
    isLoading: isJobLoading,
    error: jobError,
  } = useJob(effectiveJobId, { enabled: isLiveView && Boolean(effectiveJobId) })

  const isJobNotFound = Boolean(jobError && (jobError.status === 404 || jobError.message?.includes('not found')))

  return (
    <div
      data-testid="app-shell"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        width: '100vw',
        overflow: 'hidden',
        backgroundColor: 'var(--surface-neutral-01)',
        fontFamily: 'var(--font-family)',
      }}
    >
      <StatusStrip
        overview={overview}
        isStale={isOverviewStale}
        error={overviewError}
      />

      <ConfigInvalidBanner configuration={overview?.configuration} />

      <div
        style={{
          display: 'flex',
          flex: 1,
          overflow: 'hidden',
        }}
      >
        <NavRail
          currentRoute={route}
          projects={projects}
          selectedProjectId={selectedProjectId}
          onSelectProject={handleSelectProject}
        />

        {isLiveView ? (
          <div
            style={{
              display: 'flex',
              flex: 1,
              overflow: 'hidden',
            }}
          >
            <JobFeed
              activeJobs={activeJobs}
              recentJobs={recentJobs}
              moreRecent={moreRecent}
              selectedJobId={effectiveJobId}
              onSelectJob={handleSelectJob}
              followNewestRunning={followNewestRunning}
              onToggleFollowNewest={setFollowNewestRunning}
            />

            <JobInspector
              job={selectedJob}
              isLoading={isJobLoading && !selectedJob}
              notFound={isJobNotFound}
              jobId={effectiveJobId}
            />
          </div>
        ) : route === 'projects' ? (
          <ProjectsView projectId={params?.id || null} />
        ) : route === 'targets' ? (
          <TargetsView />
        ) : route === 'diagnostics' ? (
          <DiagnosticsView />
        ) : route === 'runtime' ? (
          <RuntimeView overview={overview} />
        ) : null}
      </div>
    </div>
  )
}

export default App
