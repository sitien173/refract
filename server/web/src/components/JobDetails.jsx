import { useEffect, useMemo, useRef, useState } from 'react'
import { getDiagnostics } from '../api'
import Alert from './Alert'
import StatusBadge from './StatusBadge'
import JobTranscript from './JobTranscript'
import { useJobStream } from '../hooks/useJobStream'

const TERMINAL_STATES = new Set(['succeeded', 'failed', 'cancelled', 'interrupted'])

function TelemetryRow({ label, measurement, isPercent = false, forceUnavailable = false }) {
  const isUnavailable = forceUnavailable || !measurement || measurement.value == null
  const displayValue = isUnavailable
    ? 'Unavailable'
    : isPercent
    ? `${measurement.value}%`
    : String(measurement.value)
  const quality = isUnavailable ? (forceUnavailable ? 'unavailable' : measurement?.quality || 'unavailable') : measurement.quality
  const source = isUnavailable && forceUnavailable ? null : measurement?.source
  const observedAt = isUnavailable && forceUnavailable ? null : measurement?.observed_at

  return (
    <div className="meta-row telemetry-row">
      <div className="telemetry-label-col">
        <span className="eyebrow">{label}</span>
      </div>
      <div className="telemetry-value-col">
        <span className="telemetry-value">{displayValue}</span>
        <div className="telemetry-details caption">
          {quality && <span className="telemetry-quality tag">{quality}</span>}
          {source && <span className="telemetry-source tag">{source}</span>}
          {observedAt && <span className="telemetry-observed-at">{observedAt}</span>}
        </div>
      </div>
    </div>
  )
}

export default function JobDetails({
  job,
  isLoading = false,
  error = null,
  refreshError = null,
  onRefresh,
  onBack,
  onNavigate,
  headingRef,
  stream: providedStream,
}) {
  const isTerminal = job ? TERMINAL_STATES.has(job.state) : true
  const internalStream = useJobStream(job?.id, { isTerminal })
  const stream = providedStream || internalStream

  const reconstructedFinalText = useMemo(() => {
    if (!stream?.entities || stream.entities.length === 0) return ''
    const lastAttempt = stream.entities[stream.entities.length - 1]
    if (!lastAttempt || !lastAttempt.items) return ''
    return lastAttempt.items
      .filter((it) => it.type === 'assistant_message')
      .map((it) => it.text)
      .join('')
  }, [stream?.entities])

  const [reports, setReports] = useState(null)
  const [nextBefore, setNextBefore] = useState(null)
  const [isReportsLoading, setIsReportsLoading] = useState(false)
  const [reportsError, setReportsError] = useState(null)
  const [reportsRefreshTrigger, setReportsRefreshTrigger] = useState(0)

  const reportsRequestIdRef = useRef(0)
  const reportsAbortControllerRef = useRef(null)
  const lastJobIdRef = useRef(null)

  useEffect(() => {
    if (!job?.id) {
      setReports(null)
      setNextBefore(null)
      setReportsError(null)
      setIsReportsLoading(false)
      lastJobIdRef.current = null
      return
    }

    const isNewJob = lastJobIdRef.current !== job.id
    lastJobIdRef.current = job.id

    if (isNewJob) {
      setReports(null)
      setNextBefore(null)
      setReportsError(null)
    }

    const reqId = ++reportsRequestIdRef.current
    if (reportsAbortControllerRef.current) {
      reportsAbortControllerRef.current.abort()
    }
    const controller = new AbortController()
    reportsAbortControllerRef.current = controller

    setIsReportsLoading(true)

    getDiagnostics({ jobId: job.id, limit: 50 }, controller.signal)
      .then((data) => {
        if (reportsRequestIdRef.current !== reqId) return
        setReports(data.reports || [])
        setNextBefore(data.next_before || null)
        setReportsError(null)
        setIsReportsLoading(false)
      })
      .catch((err) => {
        if (reportsRequestIdRef.current !== reqId || controller.signal.aborted) return
        setReportsError(err)
        setIsReportsLoading(false)
      })

    return () => {
      controller.abort()
      reportsRequestIdRef.current += 1
    }
  }, [job?.id, reportsRefreshTrigger])

  function handleRefreshClick() {
    setReportsRefreshTrigger((t) => t + 1)
    if (onRefresh) {
      onRefresh()
    }
  }

  if (error && !job) {
    return (
      <div className="job-details-container" data-testid="job-details-error">
        {onBack && (
          <div className="job-details-top-bar">
            <button
              type="button"
              className="button button-secondary button-sm back-link-btn"
              onClick={onBack}
              aria-label="Back to jobs list"
            >
              ← Back to jobs
            </button>
          </div>
        )}
        <Alert tone="error" title="Unable to load job">
          {error.message || String(error) || 'The requested job could not be found.'}
        </Alert>
      </div>
    )
  }

  if (isLoading && !job) {
    return (
      <div className="job-details-container" data-testid="job-details-loading">
        <div className="loading" role="status" aria-live="polite">
          Loading job details…
        </div>
      </div>
    )
  }

  if (!job) return null

  const plan = job.execution_plan || {}
  const hasPlan = Boolean(plan && Object.keys(plan).length > 0)
  const selection = plan.selection || {}
  const targets = Array.isArray(plan.targets) ? plan.targets : []

  const resultText = job.result?.output || job.result?.text || ''
  const isDuplicateFinalText =
    Boolean(resultText) &&
    stream?.streamStatus === 'complete' &&
    reconstructedFinalText === resultText

  const shouldRenderResultText = Boolean(resultText) && !isDuplicateFinalText
  const shouldRenderResultSection = Boolean(
    job.result && (job.result.error || shouldRenderResultText)
  )

  return (
    <div className="job-details-container" data-testid="job-details">
      <div className="job-details-top-bar">
        {onBack && (
          <button
            type="button"
            className="button button-secondary button-sm back-link-btn"
            onClick={onBack}
            aria-label="Back to jobs list"
          >
            ← Back to jobs
          </button>
        )}
        <div className="job-details-header-actions">
          {!isTerminal && (
            <span className="job-polling-indicator" aria-live="polite">
              <span className="status-dot status-dot-running" aria-hidden="true" />
              Live polling active
            </span>
          )}
          {onRefresh && (
            <button
              type="button"
              className="button button-ghost button-sm"
              onClick={handleRefreshClick}
              disabled={isLoading}
              aria-label="Refresh job details"
            >
              {isLoading ? 'Loading…' : 'Refresh'}
            </button>
          )}
        </div>
      </div>

      {refreshError && (
        <Alert tone="warning" title="Showing previously loaded job details">
          Background refresh failed. Displayed job details remain unchanged; retry when the daemon is available.
        </Alert>
      )}

      <div className="job-details-title-row">
        <div className="job-details-heading-group">
          <h2
            id="job-details-heading"
            ref={headingRef}
            tabIndex={-1}
            className="job-details-heading"
          >
            Job {job.id}
          </h2>
          {job.suspect && (
            <span
              className="suspect-badge"
              aria-label={`Job is suspect: ${job.diagnostic_count || 1} diagnostic report(s)`}
            >
              <span className="suspect-icon" aria-hidden="true">!</span>
              <span>Suspect</span>
            </span>
          )}
        </div>
        <p className="caption">
          Project: <strong>{job.project_id}</strong> · Workflow: <strong>{job.workflow}</strong>
        </p>
      </div>

      <div className="job-detail-grid">
        <section className="panel job-meta-panel" aria-labelledby="job-metadata-heading">
          <div className="panel-header">
            <h3 id="job-metadata-heading">Execution status</h3>
            <div className="job-status-badges">
              <StatusBadge status={job.state} label={job.state} />
              {job.suspect && (
                <span
                  className="suspect-badge"
                  aria-label={`Job is suspect: ${job.diagnostic_count || 1} diagnostic report(s)`}
                >
                  <span className="suspect-icon" aria-hidden="true">!</span>
                  <span>Suspect</span>
                </span>
              )}
            </div>
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

      {(() => {
        const telemetry = job.result?.metadata?.telemetry
        const hasTelemetry = Boolean(telemetry && typeof telemetry === 'object' && Object.keys(telemetry).length > 0)

        if (!hasTelemetry) {
          return (
            <section className="panel job-telemetry-panel" aria-labelledby="job-telemetry-heading">
              <div className="panel-header">
                <h3 id="job-telemetry-heading">Telemetry</h3>
              </div>
              <div className="job-telemetry-content">
                <div className="telemetry-unavailable">
                  <p className="caption">Telemetry unavailable</p>
                </div>
              </div>
            </section>
          )
        }

        const completeness = telemetry.completeness || 'unavailable'
        const capacityKnown = telemetry.context_window_size?.value != null
        const hasCacheRead = Boolean(
          telemetry.cache_read_tokens &&
            (telemetry.cache_read_tokens.value != null ||
              (telemetry.cache_read_tokens.quality && telemetry.cache_read_tokens.quality !== 'unavailable'))
        )
        const hasCacheWrite = Boolean(
          telemetry.cache_write_tokens &&
            (telemetry.cache_write_tokens.value != null ||
              (telemetry.cache_write_tokens.quality && telemetry.cache_write_tokens.quality !== 'unavailable'))
        )

        return (
          <section className="panel job-telemetry-panel" aria-labelledby="job-telemetry-heading">
            <div className="panel-header">
              <h3 id="job-telemetry-heading">Telemetry</h3>
              {completeness && (
                <span className={`telemetry-completeness tag tag-${completeness}`}>
                  {completeness}
                </span>
              )}
            </div>
            <div className="job-telemetry-content">
              <div className="telemetry-grid">
                <div className="telemetry-section telemetry-context-section">
                  <h4 className="telemetry-subheading" id="telemetry-context-subheading">Context</h4>
                  <div className="job-meta-rows">
                    <TelemetryRow
                      label="Context used"
                      measurement={telemetry.context_used_tokens}
                    />
                    <TelemetryRow
                      label="Context capacity"
                      measurement={telemetry.context_window_size}
                    />
                    <TelemetryRow
                      label="Context remaining"
                      measurement={telemetry.context_remaining_percent}
                      isPercent={true}
                      forceUnavailable={!capacityKnown}
                    />
                  </div>
                </div>

                <div className="telemetry-section telemetry-consumption-section">
                  <h4 className="telemetry-subheading" id="telemetry-consumption-subheading">Consumption</h4>
                  <div className="job-meta-rows">
                    <TelemetryRow
                      label="Job input tokens"
                      measurement={telemetry.total_input_tokens}
                    />
                    <TelemetryRow
                      label="Job output tokens"
                      measurement={telemetry.total_output_tokens}
                    />
                    {hasCacheRead && (
                      <TelemetryRow
                        label="Cache read tokens"
                        measurement={telemetry.cache_read_tokens}
                      />
                    )}
                    {hasCacheWrite && (
                      <TelemetryRow
                        label="Cache write tokens"
                        measurement={telemetry.cache_write_tokens}
                      />
                    )}
                  </div>
                </div>
              </div>
            </div>
          </section>
        )
      })()}

      <section className="panel job-prompt-panel" aria-labelledby="job-prompt-heading">
        <details className="job-prompt-disclosure">
          <summary className="job-prompt-summary">
            <h3 id="job-prompt-heading">Prompt details</h3>
          </summary>
          <div className="job-prompt-content">
            {job.prompt ? (
              <pre className="code-block prompt-text">{job.prompt}</pre>
            ) : (
              <div className="prompt-unavailable">
                <p className="caption">Prompt unavailable</p>
              </div>
            )}
          </div>
        </details>
      </section>

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

      {stream?.windowTruncated && (
        <Alert tone="warning" title="Showing recent transcript events">
          Earlier events left the browser retention window.
        </Alert>
      )}

      {stream && (
        <JobTranscript
          entities={stream.entities}
          status={stream.status}
          streamStatus={stream.streamStatus}
          error={stream.error}
          isLoading={stream.isLoading}
          onRefresh={stream.refresh}
          submittedPrompt={job?.prompt}
        />
      )}

      {shouldRenderResultSection && (
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
            {shouldRenderResultText && (
              <div className="result-output-area">
                <span className="eyebrow">Result output</span>
                <pre className="code-block">{job.result.output || job.result.text}</pre>
              </div>
            )}
          </div>
        </section>
      )}

      <section className="panel job-diagnostics-panel" aria-labelledby="job-diagnostics-heading">
        <div className="panel-header">
          <h3 id="job-diagnostics-heading">Diagnostic reports</h3>
          {reports && reports.length > 0 && (
            <span className="caption">{reports.length} report(s)</span>
          )}
        </div>
        <p className="caption job-diagnostics-note">
          Client observations, not verified server failures.
        </p>
        <div className="job-diagnostics-content">
          {reportsError && (!reports || reports.length === 0) && (
            <Alert tone="error" title="Unable to load diagnostic reports">
              {reportsError.message || 'Failed to fetch diagnostic reports.'}
            </Alert>
          )}
          {reportsError && reports && reports.length > 0 && (
            <Alert tone="warning" title="Showing previously loaded diagnostic reports">
              Background refresh failed. Displayed reports remain unchanged; retry when the daemon is available.
            </Alert>
          )}
          {isReportsLoading && !reports && (
            <p className="caption" role="status">Loading diagnostic reports…</p>
          )}
          {!isReportsLoading && !reportsError && reports && reports.length === 0 && (
            <p className="empty-message">No diagnostic reports for this job.</p>
          )}
          {nextBefore && job?.id && (
            <p className="caption diagnostics-subset-indicator">
              Showing bounded newest subset.{' '}
              <a
                href={`/dashboard/diagnostics?job_id=${encodeURIComponent(job.id)}`}
                onClick={(e) => {
                  if (onNavigate) {
                    e.preventDefault()
                    onNavigate(`/dashboard/diagnostics?job_id=${encodeURIComponent(job.id)}`)
                  }
                }}
              >
                Inspect remaining reports
              </a>
            </p>
          )}
          {reports && reports.length > 0 && (
            <div className="diagnostic-reports-list" role="feed" aria-label="Diagnostic reports list">
              {reports.map((r) => (
                <div key={r.id} className="diagnostic-report-card" tabIndex={0} role="article" aria-label={`Report ${r.id}: ${r.category}`}>
                  <div className="diagnostic-report-header">
                    <span className="eyebrow">Report ID:</span> <code className="cell-code">{r.id}</code>
                    <span className="category-tag">{r.category}</span>
                    <span className="caption">{r.created_at}</span>
                    <div className="current-state-inline">
                      <span className="sr-only">Current state: </span>
                      <StatusBadge status={r.current_state} label={`Current: ${r.current_state}`} />
                    </div>
                  </div>
                  <div className="diagnostic-report-body">
                    <div>
                      <span className="eyebrow">Expected</span>
                      <div className="diagnostics-summary-box">{r.expected}</div>
                    </div>
                    <div>
                      <span className="eyebrow">Observed</span>
                      <div className="diagnostics-summary-box">{r.observed}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
