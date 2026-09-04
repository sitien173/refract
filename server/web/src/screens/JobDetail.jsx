import { getJob } from '../api'
import Alert from '../components/Alert'
import PageHeader from '../components/PageHeader'
import StatusBadge from '../components/StatusBadge'
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

  function handleBack() {
    const target = job?.project_id
      ? `/dashboard/jobs?project=${encodeURIComponent(job.project_id)}`
      : '/dashboard/jobs'
    if (onNavigate) {
      onNavigate(target)
    } else {
      window.history.pushState({}, '', target)
      window.dispatchEvent(new PopStateEvent('popstate'))
    }
  }

  if (isLoading && !job) {
    return (
      <div className="page">
        <div className="loading">Loading job details…</div>
      </div>
    )
  }

  if (error && !job) {
    return (
      <div className="page">
        <PageHeader title="Job details" description="View execution trace and configuration revision." />
        <Alert tone="error" title="Unable to load job">
          {error.message || 'The requested job could not be found.'}
        </Alert>
        <button type="button" className="button button-secondary button-sm" onClick={handleBack}>
          ← Back to jobs
        </button>
      </div>
    )
  }

  if (!job) return null

  const plan = job.execution_plan || {}
  const hasPlan = Boolean(plan && Object.keys(plan).length > 0)
  const selection = plan.selection || {}
  const targets = Array.isArray(plan.targets) ? plan.targets : []

  return (
    <div className="page">
      <PageHeader
        title={`Job ${job.id}`}
        description={`Project: ${job.project_id} · Workflow: ${job.workflow}`}
        backLink={
          <button
            type="button"
            className="back-link-btn"
            onClick={handleBack}
            aria-label="Back to jobs list"
          >
            ← Back to jobs
          </button>
        }
        actions={
          <button
            type="button"
            className="button button-ghost button-sm"
            onClick={() => refresh()}
            disabled={isLoading}
          >
            {isLoading ? 'Loading…' : 'Refresh'}
          </button>
        }
      />

      <div className="job-detail-grid">
        <section className="panel job-meta-panel" aria-labelledby="job-metadata-heading">
          <div className="panel-header">
            <h3 id="job-metadata-heading">Execution status</h3>
            <StatusBadge status={job.state} label={job.state} />
          </div>
          <div className="job-meta-rows">
            <div className="meta-row">
              <span className="eyebrow">Job ID</span>
              <code className="cell-code">{job.id}</code>
            </div>
            <div className="meta-row">
              <span className="eyebrow">Project</span>
              <span>{job.project_id}</span>
            </div>
            <div className="meta-row">
              <span className="eyebrow">Workflow</span>
              <strong>{job.workflow}</strong>
            </div>
            <div className="meta-row">
              <span className="eyebrow">Profile</span>
              <span className="profile-tag">{job.profile}</span>
            </div>
            <div className="meta-row">
              <span className="eyebrow">Assigned target</span>
              <span>{job.target_id || 'Unassigned'}</span>
            </div>
            <div className="meta-row">
              <span className="eyebrow">Context key</span>
              <code className="cell-code">{job.context_key || '—'}</code>
            </div>
            <div className="meta-row">
              <span className="eyebrow">Attempts</span>
              <span>{job.attempts}</span>
            </div>
            <div className="meta-row">
              <span className="eyebrow">Created</span>
              <span className="caption">{job.created_at}</span>
            </div>
            <div className="meta-row">
              <span className="eyebrow">Updated</span>
              <span className="caption">{job.updated_at}</span>
            </div>
          </div>
        </section>

        <section className="panel job-revision-panel" aria-labelledby="job-revision-heading">
          <div className="panel-header">
            <h3 id="job-revision-heading">Configuration revision</h3>
          </div>
          <div className="job-revision-content">
            {job.config_revision ? (
              <div className="revision-active">
                <span className="eyebrow">Resolved revision SHA-256</span>
                <code className="cell-code block-code">{job.config_revision}</code>
                <p className="caption">
                  This revision was snapshotted when the job was submitted. Changes to global configuration do not affect this execution.
                </p>
              </div>
            ) : (
              <div className="revision-unavailable">
                <p className="caption">Configuration revision unavailable</p>
              </div>
            )}
          </div>
        </section>
      </div>

      <section className="panel job-plan-panel" aria-labelledby="job-plan-heading">
        <div className="panel-header">
          <h3 id="job-plan-heading">Execution plan</h3>
        </div>
        <div className="job-plan-content">
          {hasPlan ? (
            <div className="allowlisted-plan-fields">
              <div className="plan-section">
                <span className="eyebrow">Resolved profile & workflow</span>
                <div className="plan-tag-row">
                  <span className="profile-tag">{plan.profile || 'default'}</span>
                  <strong>{plan.workflow || job.workflow}</strong>
                </div>
              </div>

              {selection && (
                <div className="plan-section">
                  <span className="eyebrow">Selection policy</span>
                  <div className="plan-selection-details">
                    <div>
                      <span className="caption">Targets: </span>
                      <code className="cell-code">
                        {Array.isArray(selection.targets) ? selection.targets.join(', ') : 'None'}
                      </code>
                    </div>
                    <div>
                      <span className="caption">Max attempts: </span>
                      <span>{selection.max_attempts ?? 1}</span>
                    </div>
                    <div>
                      <span className="caption">Timeout: </span>
                      <span>{selection.timeout_s ? `${selection.timeout_s}s` : 'None'}</span>
                    </div>
                  </div>
                </div>
              )}

              {targets.length > 0 && (
                <div className="plan-section">
                  <span className="eyebrow">Candidate execution targets</span>
                  <div className="plan-targets-list">
                    {targets.map((target) => (
                      <div key={target.id} className="plan-target-card">
                        <div className="plan-target-header">
                          <strong>{target.id}</strong>
                          <span className="caption">{target.backend || 'default'}</span>
                        </div>
                        <div className="plan-target-meta">
                          <span>Model: <code className="cell-code">{target.model}</code></span>
                          <span>Isolation: {target.isolated ? 'Isolated' : 'Shared'}</span>
                          <span>Access: {target.read_only ? 'Read-only' : 'Read-write'}</span>
                          <span>Max concurrency: {target.max_concurrency}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="plan-unavailable">
              <p className="caption">Execution plan unavailable</p>
            </div>
          )}
        </div>
      </section>

      {job.result && (job.result.error || job.result.text || job.result.output) && (
        <section className="panel job-result-panel" aria-labelledby="job-result-heading">
          <div className="panel-header">
            <h3 id="job-result-heading">Execution result</h3>
          </div>
          <div className="job-result-content">
            {job.result.error && (
              <Alert tone="error" title="Execution error">
                <p>{job.result.error}</p>
              </Alert>
            )}
            {(job.result.output || job.result.text) && (
              <div className="result-output-area">
                <span className="eyebrow">Result output</span>
                <pre className="code-block">{job.result.output || job.result.text}</pre>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  )
}
