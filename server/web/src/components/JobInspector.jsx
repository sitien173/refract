import React, { useState } from 'react'
import { TranscriptViewer } from './TranscriptViewer.jsx'
import { useTranscriptStream } from '../hooks/useTranscriptStream.js'

export function JobInspector({
  job = null,
  isLoading = false,
  notFound = false,
  jobId = null,
}) {
  const [activeTab, setActiveTab] = useState('transcript')

  const { events, streamStatus, retainedFrom } = useTranscriptStream({
    jobId: job?.id,
    jobState: job?.state,
    resultText: job?.result?.text || '',
  })

  if (notFound) {
    return (
      <main
        role="main"
        data-testid="job-inspector"
        style={{
          flex: 1,
          padding: 'var(--padding-xl)',
          backgroundColor: 'var(--surface-neutral-01)',
          overflowY: 'auto',
          boxSizing: 'border-box',
        }}
      >
        <div
          role="alert"
          className="tds-announcement tds-announcement--warning"
          style={{ maxWidth: '600px' }}
        >
          <div className="tds-announcement__content">
            <p className="tds-announcement__title">Job not found</p>
            <p className="tds-announcement__message">
              The job <strong>{jobId}</strong> was not found or may have been deleted.
            </p>
          </div>
        </div>
      </main>
    )
  }

  if (isLoading || !job) {
    return (
      <main
        role="main"
        data-testid="job-inspector"
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 'var(--padding-xl)',
          color: 'var(--text-description)',
          backgroundColor: 'var(--surface-neutral-01)',
        }}
      >
        {isLoading ? 'Loading job details...' : 'Select a job to inspect.'}
      </main>
    )
  }

  const result = job.result || {}
  const metadata = result.metadata || {}
  const failure = metadata.failure
  const retry = metadata.retry || {}
  const telemetry = metadata.telemetry || {}
  const hasFailure = Boolean(failure || result.error)

  const tabs = [
    { id: 'transcript', label: 'Transcript' },
    { id: 'result', label: 'Result' },
    { id: 'plan', label: 'Plan' },
  ]

  const handleTabKeyDown = (e) => {
    const currentIndex = tabs.findIndex((t) => t.id === activeTab)
    if (e.key === 'ArrowRight') {
      e.preventDefault()
      const nextIndex = (currentIndex + 1) % tabs.length
      setActiveTab(tabs[nextIndex].id)
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const prevIndex = (currentIndex - 1 + tabs.length) % tabs.length
      setActiveTab(tabs[prevIndex].id)
    } else if (e.key === 'Home') {
      e.preventDefault()
      setActiveTab(tabs[0].id)
    } else if (e.key === 'End') {
      e.preventDefault()
      setActiveTab(tabs[tabs.length - 1].id)
    }
  }

  const usedTokens = telemetry.context_used_tokens?.value
  const formattedTokens =
    typeof usedTokens === 'number'
      ? usedTokens.toLocaleString()
      : usedTokens !== undefined && usedTokens !== null
      ? String(usedTokens)
      : null

  return (
    <main
      role="main"
      data-testid="job-inspector"
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflowY: 'auto',
        backgroundColor: 'var(--surface-neutral-01)',
        padding: 'var(--padding-lg)',
        boxSizing: 'border-box',
        gap: 'var(--gap-md)',
      }}
    >
      {/* Inspector Header */}
      <section
        style={{
          backgroundColor: 'var(--surface-neutral-02)',
          borderRadius: 'var(--radius-card)',
          padding: 'var(--padding-lg)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            marginBottom: 'var(--gap-sm)',
          }}
        >
          <div>
            <div
              style={{
                fontSize: 'var(--font-size-md)',
                fontWeight: 'var(--font-weight-bold)',
                fontFamily: 'var(--font-family-mono)',
                color: 'var(--text-default)',
              }}
            >
              {job.id}
            </div>
            <div
              style={{
                fontSize: 'var(--font-size-xs)',
                color: 'var(--text-description)',
                marginTop: 'var(--gap-xs)',
              }}
            >
              Created: {job.created_at || 'n/a'} | Updated: {job.updated_at || 'n/a'}
            </div>
          </div>
          <span
            className={`tds-tag tds-tag--md ${
              job.state === 'running'
                ? 'tds-tag--intermediate'
                : job.state === 'succeeded'
                ? 'tds-tag--positive'
                : job.state === 'failed'
                ? 'tds-tag--negative'
                : 'tds-tag--default'
            }`}
          >
            {job.state}
          </span>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: 'var(--gap-sm)',
            fontSize: 'var(--font-size-xs)',
            marginTop: 'var(--gap-md)',
            paddingTop: 'var(--gap-md)',
            borderTop: '1px solid var(--border-divider)',
          }}
        >
          <div>
            <span style={{ color: 'var(--text-caption)' }}>Workflow: </span>
            <span style={{ fontWeight: 'var(--font-weight-medium)' }}>{job.workflow}</span>
          </div>
          <div>
            <span style={{ color: 'var(--text-caption)' }}>Profile: </span>
            <span style={{ fontWeight: 'var(--font-weight-medium)' }}>{job.profile}</span>
          </div>
          <div>
            <span style={{ color: 'var(--text-caption)' }}>Target: </span>
            <span style={{ fontWeight: 'var(--font-weight-medium)' }}>{job.target_id || 'none'}</span>
          </div>
          <div>
            <span style={{ color: 'var(--text-caption)' }}>Context: </span>
            <span style={{ fontWeight: 'var(--font-weight-medium)' }}>{job.context_key}</span>
          </div>
          <div>
            <span style={{ color: 'var(--text-caption)' }}>Attempts: </span>
            <span style={{ fontWeight: 'var(--font-weight-medium)' }}>Attempts: {job.attempts}</span>
          </div>
          {formattedTokens !== null && (
            <div>
              <span style={{ color: 'var(--text-caption)' }}>Tokens used: </span>
              <span style={{ fontWeight: 'var(--font-weight-medium)' }}>{formattedTokens}</span>
            </div>
          )}
        </div>
      </section>

      {/* Failure Card */}
      {hasFailure && (
        <section
          role="region"
          aria-label="Failure details"
          className="tds-announcement tds-announcement--error"
          style={{
            border: '1px solid var(--border-negative)',
          }}
        >
          <div className="tds-announcement__content">
            <p className="tds-announcement__title">
              Failure: {failure?.kind || (result.error ? 'execution error' : 'unknown')}
            </p>
            <p className="tds-announcement__message">
              {result.error || 'Execution encountered an unrecoverable failure.'}
            </p>
            <div
              style={{
                display: 'flex',
                gap: 'var(--gap-lg)',
                fontSize: 'var(--font-size-xs)',
                marginTop: 'var(--gap-xs)',
              }}
            >
              <span>Retryable: {retry.retryable !== undefined && retry.retryable !== null ? (retry.retryable ? 'Yes' : 'No') : 'No'}</span>
              <span>Next target: {retry.next_target || 'None'}</span>
              <a
                href={`#/diagnostics?job_id=${encodeURIComponent(job.id)}`}
                style={{
                  color: 'var(--text-link)',
                  textDecoration: 'underline',
                  fontWeight: 'var(--font-weight-medium)',
                }}
              >
                View diagnostics
              </a>
            </div>
          </div>
        </section>
      )}

      {/* Tabs list */}
      <div className="tds-tabs">
        <div className="tds-tabs__row">
          <div
            role="tablist"
            aria-label="Job views"
            onKeyDown={handleTabKeyDown}
            className="tds-tabs__list"
          >
            {tabs.map((tab) => {
              const isSelected = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  id={`tab-${tab.id}`}
                  aria-selected={isSelected}
                  aria-controls={`panel-${tab.id}`}
                  tabIndex={isSelected ? 0 : -1}
                  onClick={() => setActiveTab(tab.id)}
                  className={`tds-tab-item ${isSelected ? 'tds-tab-item--active' : ''}`}
                >
                  <span className="tds-tab-item__content">{tab.label}</span>
                  <span className="tds-tab-item__indicator" aria-hidden="true" />
                </button>
              )
            })}
          </div>
        </div>
        <div className="tds-tabs__divider" aria-hidden="true" />
      </div>

      {/* Tab Panels */}
      <div style={{ flex: 1, minHeight: 0 }}>
        {activeTab === 'transcript' && (
          <div
            role="tabpanel"
            id="panel-transcript"
            aria-labelledby="tab-transcript"
            style={{ height: '100%' }}
          >
            <TranscriptViewer
              events={events}
              streamStatus={streamStatus}
              retainedFrom={retainedFrom}
              fallbackText={result.text}
            />
          </div>
        )}

        {activeTab === 'result' && (
          <div
            role="tabpanel"
            id="panel-result"
            aria-labelledby="tab-result"
            style={{
              padding: 'var(--padding-md)',
              backgroundColor: 'var(--surface-neutral-02)',
              borderRadius: 'var(--radius-card)',
              fontFamily: 'var(--font-family-mono)',
              fontSize: 'var(--font-size-xs)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              color: 'var(--text-default)',
            }}
          >
            {result.text && <div>{result.text}</div>}
            {result.error && (
              <div style={{ color: 'var(--text-negative)', marginTop: 'var(--gap-sm)' }}>
                {result.error}
              </div>
            )}
            <div style={{ marginTop: 'var(--gap-md)', color: 'var(--text-caption)' }}>
              Metadata:
              <pre style={{ margin: 0 }}>{JSON.stringify(result.metadata || {}, null, 2)}</pre>
            </div>
          </div>
        )}

        {activeTab === 'plan' && (
          <div
            role="tabpanel"
            id="panel-plan"
            aria-labelledby="tab-plan"
            style={{
              padding: 'var(--padding-md)',
              backgroundColor: 'var(--surface-neutral-02)',
              borderRadius: 'var(--radius-card)',
              fontSize: 'var(--font-size-xs)',
              color: 'var(--text-default)',
            }}
          >
            <div style={{ marginBottom: 'var(--gap-md)' }}>
              <strong>Execution Plan:</strong>
              <pre
                style={{
                  fontFamily: 'var(--font-family-mono)',
                  margin: 'var(--gap-xs) 0',
                }}
              >
                {JSON.stringify(job.execution_plan || {}, null, 2)}
              </pre>
            </div>
            <div style={{ marginBottom: 'var(--gap-sm)' }}>
              <strong>Attempts:</strong> {job.attempts}
            </div>
            <div>
              <a
                href={`#/diagnostics?job_id=${encodeURIComponent(job.id)}`}
                style={{
                  color: 'var(--text-link)',
                  textDecoration: 'underline',
                }}
              >
                Diagnostics for this job
              </a>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
