import React, { useRef, useState, useEffect, useMemo, useCallback } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { processTranscriptEvents } from '../hooks/useTranscriptStream.js'

export function TranscriptViewer({
  events = [],
  streamStatus = 'unavailable',
  retainedFrom = 0,
  fallbackText = '',
}) {
  const parentRef = useRef(null)
  const [autoScroll, setAutoScroll] = useState(true)

  const items = useMemo(() => processTranscriptEvents(events), [events])

  const rowVirtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 48,
    overscan: 10,
    initialRect: { width: 800, height: 600 },
  })

  // Auto-scroll to tail when new events arrive and autoScroll is enabled
  useEffect(() => {
    if (autoScroll && items.length > 0 && parentRef.current) {
      rowVirtualizer.scrollToIndex(items.length - 1, { align: 'end' })
    }
  }, [items.length, autoScroll, rowVirtualizer])

  const handleScroll = useCallback(() => {
    if (!parentRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = parentRef.current
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 40
    if (!isAtBottom && autoScroll) {
      setAutoScroll(false)
    } else if (isAtBottom && !autoScroll) {
      setAutoScroll(true)
    }
  }, [autoScroll])

  const jumpToLive = useCallback(() => {
    setAutoScroll(true)
    if (items.length > 0) {
      rowVirtualizer.scrollToIndex(items.length - 1, { align: 'end' })
    }
  }, [items.length, rowVirtualizer])

  const isPruned = retainedFrom > 1 && events.length > 0 && events[0].id > 1

  if (streamStatus === 'unavailable' && items.length === 0) {
    return (
      <div
        data-testid="transcript-fallback"
        style={{
          padding: 'var(--padding-lg)',
          fontFamily: 'var(--font-family-mono)',
          fontSize: 'var(--font-size-sm)',
          lineHeight: 'var(--line-height-md)',
          color: 'var(--text-default)',
          backgroundColor: 'var(--surface-neutral-01)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-card)',
        }}
      >
        {fallbackText || 'No transcript available for this job.'}
      </div>
    )
  }

  return (
    <div
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: '300px',
        border: '1px solid var(--border-subtle)',
        borderRadius: 'var(--radius-card)',
        backgroundColor: 'var(--surface-neutral-01)',
        overflow: 'hidden',
      }}
    >
      {isPruned && (
        <div
          role="status"
          className="tds-announcement tds-announcement--warning tds-announcement--inline"
          style={{
            borderBottom: '1px solid var(--border-intermediate)',
            borderRadius: 0,
          }}
        >
          <span className="tds-announcement__message">
            Earlier output pruned (retained from event #{retainedFrom}).
          </span>
        </div>
      )}

      <div
        ref={parentRef}
        data-testid="transcript-scroll-area"
        onScroll={handleScroll}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: 'var(--padding-md)',
          fontFamily: 'var(--font-family-mono)',
          fontSize: 'var(--font-size-sm)',
        }}
      >
        {items.length === 0 ? (
          <div
            style={{
              padding: 'var(--padding-xl)',
              color: 'var(--text-description)',
              textAlign: 'center',
            }}
          >
            No events in transcript.
          </div>
        ) : (
          <div
            style={{
              height: `${rowVirtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const item = items[virtualRow.index]
              return (
                <div
                  key={virtualRow.key}
                  data-index={virtualRow.index}
                  ref={rowVirtualizer.measureElement}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${virtualRow.start}px)`,
                    padding: 'var(--padding-xs) 0',
                  }}
                >
                  <TranscriptRow item={item} />
                </div>
              )
            })}
          </div>
        )}
      </div>

      {!autoScroll && (
        <div
          style={{
            position: 'absolute',
            bottom: 'var(--padding-md)',
            right: 'var(--padding-md)',
            zIndex: 10,
          }}
        >
          <button
            type="button"
            className="tds-btn tds-btn--sm tds-btn--secondary"
            onClick={jumpToLive}
          >
            Jump to live
          </button>
        </div>
      )}
    </div>
  )
}

function TranscriptRow({ item }) {
  if (item.kind === 'assistant.text') {
    return (
      <div
        style={{
          backgroundColor: 'var(--surface-neutral-02)',
          padding: 'var(--padding-sm) var(--padding-md)',
          borderRadius: 'var(--radius-button)',
          border: '1px solid var(--border-subtle)',
          color: 'var(--text-default)',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          lineHeight: 'var(--line-height-md)',
        }}
      >
        <div
          style={{
            fontSize: 'var(--font-size-xs)',
            color: 'var(--text-caption)',
            marginBottom: 'var(--gap-xs)',
          }}
        >
          Assistant #{item.entity_id}
        </div>
        <div>{item.text}</div>
      </div>
    )
  }

  if (item.kind === 'tool.call') {
    const isRunning = item.status === 'running'
    const isFailed = item.status === 'failed' || item.status === 'error' || Boolean(item.error)
    const tagVariant = isRunning
      ? 'tds-tag--intermediate'
      : isFailed
      ? 'tds-tag--negative'
      : 'tds-tag--positive'

    return (
      <div
        style={{
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-button)',
          padding: 'var(--padding-sm) var(--padding-md)',
          backgroundColor: 'var(--surface-neutral-01)',
          marginBottom: 'var(--gap-xs)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--gap-sm)',
            fontSize: 'var(--font-size-xs)',
            color: 'var(--text-description)',
            marginBottom: 'var(--gap-xs)',
          }}
        >
          <span style={{ fontWeight: 'var(--font-weight-bold)', color: 'var(--text-default)' }}>
            {item.name}
          </span>
          <span className={`tds-tag tds-tag--sm ${tagVariant}`}>
            {item.status}
          </span>
        </div>
        {item.input !== undefined && (
          <div style={{ color: 'var(--text-description)', fontSize: 'var(--font-size-xs)' }}>
            Input: {typeof item.input === 'object' ? JSON.stringify(item.input) : String(item.input)}
          </div>
        )}
        {item.output !== undefined && (
          <div style={{ color: 'var(--text-default)', marginTop: 'var(--gap-xs)', whiteSpace: 'pre-wrap' }}>
            Output: {typeof item.output === 'object' ? JSON.stringify(item.output) : String(item.output)}
          </div>
        )}
        {item.error && (
          <div style={{ color: 'var(--text-negative)', marginTop: 'var(--gap-xs)' }}>
            Error: {String(item.error)}
          </div>
        )}
      </div>
    )
  }

  if (item.kind === 'stream.truncated') {
    return (
      <div
        role="alert"
        className="tds-announcement tds-announcement--warning tds-announcement--inline"
        style={{
          margin: 'var(--gap-xs) 0',
          border: '1px solid var(--border-intermediate)',
        }}
      >
        <span className="tds-announcement__message">
          Stream truncated: {item.data?.reason || 'stream limit reached'}.
        </span>
      </div>
    )
  }

  if (item.kind === 'stream.persistence_failed') {
    return (
      <div
        role="alert"
        className="tds-announcement tds-announcement--error tds-announcement--inline"
        style={{
          margin: 'var(--gap-xs) 0',
          border: '1px solid var(--border-negative)',
        }}
      >
        <span className="tds-announcement__message">
          Stream persistence failed: {item.data?.error || 'persistence write failure'}.
        </span>
      </div>
    )
  }

  // Default lifecycle or custom marker
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--gap-sm)',
        color: 'var(--text-caption)',
        fontSize: 'var(--font-size-xs)',
        padding: 'var(--padding-xs) 0',
      }}
    >
      <span style={{ fontWeight: 'var(--font-weight-semibold)' }}>[{item.kind}]</span>
      {item.data?.message || item.data?.msg || (Object.keys(item.data || {}).length ? JSON.stringify(item.data) : '')}
    </div>
  )
}
