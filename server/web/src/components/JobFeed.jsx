import React, { useState, useEffect, useMemo, useRef } from 'react'

export function JobFeed({
  activeJobs = [],
  recentJobs = [],
  moreRecent = 0,
  selectedJobId = null,
  onSelectJob = () => {},
  followNewestRunning = false,
  onToggleFollowNewest = () => {},
}) {
  const allJobs = useMemo(() => [...activeJobs, ...recentJobs], [activeJobs, recentJobs])
  const itemRefs = useRef([])

  const [focusedIndex, setFocusedIndex] = useState(() => {
    const idx = allJobs.findIndex((j) => j.id === selectedJobId)
    return idx >= 0 ? idx : 0
  })

  useEffect(() => {
    if (allJobs.length === 0) {
      setFocusedIndex(0)
      return
    }
    const idx = allJobs.findIndex((j) => j.id === selectedJobId)
    if (idx >= 0) {
      setFocusedIndex(idx)
    } else {
      setFocusedIndex((prev) => {
        if (selectedJobId) {
          return 0
        }
        if (prev >= 0 && prev < allJobs.length) {
          return prev
        }
        return 0
      })
    }
  }, [selectedJobId, allJobs])

  const handleItemKeyDown = (e, index, job) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      const nextIndex = Math.min(index + 1, allJobs.length - 1)
      setFocusedIndex(nextIndex)
      itemRefs.current[nextIndex]?.focus()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      const prevIndex = Math.max(index - 1, 0)
      setFocusedIndex(prevIndex)
      itemRefs.current[prevIndex]?.focus()
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSelectJob(job.id)
    }
  }

  const renderJobItem = (job, index) => {
    const isSelected = job.id === selectedJobId
    const isFocused = index === focusedIndex

    let tagVariant = 'tds-tag--default'
    if (job.state === 'running') tagVariant = 'tds-tag--intermediate'
    else if (job.state === 'succeeded') tagVariant = 'tds-tag--positive'
    else if (job.state === 'failed') tagVariant = 'tds-tag--negative'

    return (
      <li
        key={job.id}
        ref={(el) => {
          itemRefs.current[index] = el
        }}
        role="button"
        aria-label={`Job ${job.id}`}
        tabIndex={isFocused ? 0 : -1}
        onClick={() => {
          setFocusedIndex(index)
          onSelectJob(job.id)
        }}
        onKeyDown={(e) => handleItemKeyDown(e, index, job)}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--gap-xs)',
          padding: 'var(--padding-sm) var(--padding-md)',
          borderRadius: 'var(--radius-button)',
          border: isSelected
            ? '1px solid var(--border-interactive)'
            : '1px solid var(--border-subtle)',
          backgroundColor: isSelected
            ? 'var(--surface-selected)'
            : isFocused
            ? 'var(--surface-hover)'
            : 'var(--surface-neutral-01)',
          cursor: 'pointer',
          marginBottom: 'var(--gap-xs)',
          boxSizing: 'border-box',
          outline: 'none',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span
            style={{
              fontFamily: 'var(--font-family-mono)',
              fontSize: 'var(--font-size-xs)',
              fontWeight: 'var(--font-weight-bold)',
              color: 'var(--text-default)',
            }}
          >
            {job.id}
          </span>
          <span className={`tds-tag tds-tag--sm ${tagVariant}`}>
            {job.state}
          </span>
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontSize: 'var(--font-size-xs)',
            color: 'var(--text-description)',
          }}
        >
          <span>{job.workflow}</span>
          <span>{job.target_id || job.profile || ''}</span>
        </div>
      </li>
    )
  }

  return (
    <aside
      role="complementary"
      aria-label="Job feed"
      data-testid="job-feed"
      style={{
        width: '360px',
        flexShrink: 0,
        backgroundColor: 'var(--surface-neutral-01)',
        borderRight: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        boxSizing: 'border-box',
      }}
    >
      <div
        style={{
          padding: 'var(--padding-md)',
          borderBottom: '1px solid var(--border-subtle)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span
          style={{
            fontWeight: 'var(--font-weight-bold)',
            fontSize: 'var(--font-size-md)',
            color: 'var(--text-default)',
          }}
        >
          Jobs
        </span>
        <label
          htmlFor="follow-newest-toggle"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 'var(--gap-xs)',
            fontSize: 'var(--font-size-xs)',
            color: 'var(--text-description)',
            cursor: 'pointer',
          }}
        >
          <input
            id="follow-newest-toggle"
            type="checkbox"
            checked={followNewestRunning}
            onChange={(e) => onToggleFollowNewest(e.target.checked)}
            aria-label="Follow newest running job"
          />
          Follow newest running job
        </label>
      </div>

      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: 'var(--padding-md)',
        }}
      >
        <ul
          role="list"
          aria-label="Job list"
          style={{
            listStyle: 'none',
            padding: 0,
            margin: 0,
            outline: 'none',
          }}
        >
          <div
            style={{
              fontSize: 'var(--font-size-xs)',
              fontWeight: 'var(--font-weight-bold)',
              letterSpacing: '0.5px',
              color: 'var(--text-caption)',
              marginBottom: 'var(--gap-xs)',
            }}
          >
            ACTIVE ({activeJobs.length})
          </div>
          {activeJobs.length === 0 ? (
            <div
              style={{
                fontSize: 'var(--font-size-xs)',
                color: 'var(--text-description)',
                padding: 'var(--padding-sm) 0',
                marginBottom: 'var(--gap-md)',
              }}
            >
              No active jobs
            </div>
          ) : (
            activeJobs.map((job, idx) => renderJobItem(job, idx))
          )}

          <div
            style={{
              fontSize: 'var(--font-size-xs)',
              fontWeight: 'var(--font-weight-bold)',
              letterSpacing: '0.5px',
              color: 'var(--text-caption)',
              marginTop: 'var(--gap-md)',
              marginBottom: 'var(--gap-xs)',
            }}
          >
            RECENT ({recentJobs.length})
          </div>
          {recentJobs.length === 0 ? (
            <div
              style={{
                fontSize: 'var(--font-size-xs)',
                color: 'var(--text-description)',
                padding: 'var(--padding-sm) 0',
              }}
            >
              No recent jobs
            </div>
          ) : (
            recentJobs.map((job, idx) => renderJobItem(job, activeJobs.length + idx))
          )}

          {moreRecent > 0 && (
            <div
              style={{
                fontSize: 'var(--font-size-xs)',
                color: 'var(--text-caption)',
                textAlign: 'center',
                padding: 'var(--padding-sm) 0',
              }}
            >
              +{moreRecent} more recent terminal jobs
            </div>
          )}
        </ul>
      </div>
    </aside>
  )
}
