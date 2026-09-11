import { useEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import StatusBadge from './StatusBadge'

function getStatusLabel(status, streamStatus) {
  if (streamStatus === 'unavailable') return 'Transcript unavailable'
  if (streamStatus === 'truncated') return 'Transcript truncated'
  if (streamStatus === 'failed') return 'Stream failed'
  if (status === 'connecting') return 'Connecting to transcript…'
  if (status === 'live') return 'Live stream connected'
  if (status === 'reconnecting') return 'Reconnecting…'
  if (status === 'complete' || streamStatus === 'complete') return 'Transcript complete'
  return status
}

export default function JobTranscript({
  entities = [],
  status = 'live',
  streamStatus = 'active',
  error = null,
  isLoading = false,
  onRefresh,
}) {
  const parentRef = useRef(null)
  const isAtBottomRef = useRef(true)
  const [showNewActivity, setShowNewActivity] = useState(false)

  const flatItems = useMemo(() => {
    const items = []
    for (const attempt of entities) {
      items.push({
        key: `attempt-header-${attempt.attempt}`,
        type: 'attempt_header',
        attempt,
      })
      for (let i = 0; i < attempt.items.length; i += 1) {
        const it = attempt.items[i]
        items.push({
          key: `${attempt.attempt}-${it.type}-${it.entity_id || it.call_id || i}`,
          type: it.type,
          item: it,
          attempt,
        })
      }
    }
    return items
  }, [entities])

  const prevCountRef = useRef(flatItems.length)

  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 72,
    overscan: 5,
  })

  const handleScroll = () => {
    if (!parentRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = parentRef.current
    const atBottom = scrollHeight - scrollTop - clientHeight < 50
    isAtBottomRef.current = atBottom
    if (atBottom) {
      setShowNewActivity(false)
    }
  }

  useEffect(() => {
    if (flatItems.length > prevCountRef.current) {
      if (isAtBottomRef.current && parentRef.current) {
        if (typeof parentRef.current.scrollTo === 'function') {
          parentRef.current.scrollTo({ top: parentRef.current.scrollHeight, behavior: 'smooth' })
        }
      } else {
        setShowNewActivity(true)
      }
    }
    prevCountRef.current = flatItems.length
  }, [flatItems.length])

  const scrollToBottom = () => {
    if (parentRef.current) {
      if (typeof parentRef.current.scrollTo === 'function') {
        parentRef.current.scrollTo({ top: parentRef.current.scrollHeight, behavior: 'smooth' })
      }
      isAtBottomRef.current = true
      setShowNewActivity(false)
    }
  }

  const virtualItems = virtualizer.getVirtualItems()
  const renderItems = virtualItems.length > 0
    ? virtualItems.map((virtualRow) => ({
        ...flatItems[virtualRow.index],
        virtualRow,
      }))
    : flatItems.map((it) => ({
        ...it,
        virtualRow: null,
      }))

  const statusMessage = getStatusLabel(status, streamStatus)
  const isUnavailable = streamStatus === 'unavailable' || (entities.length === 0 && (status === 'complete' || streamStatus === 'complete'))

  return (
    <section className="panel job-transcript-panel" aria-labelledby="job-transcript-heading">
      <div className="panel-header">
        <div className="transcript-header-title">
          <h3 id="job-transcript-heading">Live transcript</h3>
          <span className={`transcript-status-badge status-badge-${status}`}>
            <span className={`status-dot status-dot-${status === 'live' ? 'running' : status === 'failed' ? 'failed' : 'neutral'}`} aria-hidden="true" />
            {statusMessage}
          </span>
        </div>
        {onRefresh && (
          <button
            type="button"
            className="button button-ghost button-sm"
            onClick={onRefresh}
            disabled={isLoading}
            aria-label="Refresh transcript"
          >
            {isLoading ? 'Loading…' : 'Refresh'}
          </button>
        )}
      </div>

      <div
        className="sr-only"
        role="status"
        aria-live="polite"
        data-testid="transcript-live-region"
      >
        {statusMessage}
      </div>

      {isUnavailable ? (
        <div className="transcript-unavailable">
          <p className="caption">Transcript is not available for this job.</p>
        </div>
      ) : (
        <div className="transcript-container-wrapper">
          <div
            ref={parentRef}
            className="transcript-scroll-container"
            data-testid="transcript-scroll-container"
            onScroll={handleScroll}
            tabIndex={0}
            role="region"
            aria-label="Job execution transcript"
          >
            <div
              className="transcript-virtual-inner"
              style={{
                height: virtualItems.length > 0 ? `${virtualizer.getTotalSize()}px` : 'auto',
                position: 'relative',
                width: '100%',
              }}
            >
              {renderItems.map(({ key, type, attempt, item, virtualRow }) => {
                const style = virtualRow
                  ? {
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      width: '100%',
                      transform: `translateY(${virtualRow.start}px)`,
                    }
                  : undefined

                if (type === 'attempt_header') {
                  return (
                    <div key={key} style={style} className="transcript-attempt-header">
                      <div className="attempt-title">
                        <strong>Attempt {attempt.attempt}</strong>
                        {attempt.target_id && <code className="cell-code">{attempt.target_id}</code>}
                        {attempt.backend && <span className="profile-tag">{attempt.backend}</span>}
                      </div>
                      <StatusBadge status={attempt.status} label={attempt.status} />
                    </div>
                  )
                }

                if (type === 'assistant_message') {
                  return (
                    <div key={key} style={style} className="transcript-card transcript-assistant-card">
                      <div className="transcript-card-header">
                        <span className="eyebrow">Assistant</span>
                        {item.status === 'streaming' && (
                          <span className="streaming-indicator" aria-label="Streaming in progress">
                            <span className="status-dot status-dot-running" aria-hidden="true" />
                            streaming…
                          </span>
                        )}
                      </div>
                      <pre className="transcript-text">{item.text}</pre>
                    </div>
                  )
                }

                if (type === 'tool_call') {
                  return (
                    <div key={key} style={style} className="transcript-card transcript-tool-card">
                      <div className="transcript-card-header">
                        <span className="eyebrow">Tool</span>
                        <StatusBadge status={item.status} label={item.status} />
                      </div>
                      <div className="tool-call-details">
                        <span className="tool-name"><strong>{item.tool_name}</strong></span>
                        {item.call_id && <code className="cell-code caption">{item.call_id}</code>}
                      </div>
                    </div>
                  )
                }

                if (type === 'notice') {
                  return (
                    <div key={key} style={style} className="transcript-card transcript-notice-card">
                      <p className="caption">{item.text}</p>
                    </div>
                  )
                }

                if (type === 'truncated') {
                  return (
                    <div key={key} style={style} className="transcript-card transcript-truncated-card">
                      <span className="eyebrow">Stream truncated</span>
                      <p className="caption">Reason: {item.reason}</p>
                    </div>
                  )
                }

                return null
              })}
            </div>
          </div>

          {showNewActivity && (
            <button
              type="button"
              className="button button-primary button-sm transcript-new-activity-btn"
              onClick={scrollToBottom}
              aria-label="New activity, scroll to live edge"
            >
              ↓ New activity
            </button>
          )}
        </div>
      )}
    </section>
  )
}
