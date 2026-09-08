import { useEffect } from 'react'
import { getJob } from '../api'
import JobDetails from '../components/JobDetails'
import { useDashboardQuery } from '../hooks/useDashboardQuery'
import { usePolling } from '../hooks/usePolling'

const TERMINAL_STATES = new Set(['succeeded', 'failed', 'cancelled', 'interrupted'])

export default function JobDetail({ jobId, onNavigate }) {
  const {
    data: job,
    error,
    isLoading,
    refresh,
  } = useDashboardQuery(() => (jobId ? getJob(jobId) : Promise.resolve(null)), {
    deps: [jobId],
  })

  const isTerminal = job ? TERMINAL_STATES.has(job.state) : true

  // Poll active jobs every 5 seconds; stop when terminal or unmounted
  usePolling(refresh, 5000, {
    enabled: Boolean(jobId && !isTerminal),
    isTerminal,
    deps: [jobId, isTerminal],
  })

  // Bridge legacy /dashboard/jobs/:jobId route into owning project canonical route
  useEffect(() => {
    if (job?.project_id && jobId) {
      const canonical = `/dashboard/projects/${encodeURIComponent(job.project_id)}/jobs/${encodeURIComponent(jobId)}`
      if (onNavigate) {
        onNavigate(canonical)
      } else {
        window.history.replaceState({}, '', canonical)
        window.dispatchEvent(new PopStateEvent('popstate'))
      }
    }
  }, [job?.project_id, jobId, onNavigate])

  function handleBack() {
    const target = job?.project_id
      ? `/dashboard/projects/${encodeURIComponent(job.project_id)}`
      : '/dashboard/projects'
    if (onNavigate) {
      onNavigate(target)
    } else {
      window.history.pushState({}, '', target)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }
  }

  return (
    <div className="page">
      <JobDetails
        job={job}
        isLoading={isLoading}
        error={error}
        onRefresh={refresh}
        onBack={handleBack}
      />
    </div>
  )
}
