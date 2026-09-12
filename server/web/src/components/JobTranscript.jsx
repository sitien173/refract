import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
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

function formatPayload(value) {
  if (typeof value === 'string') {
    return value
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function ToolCallItem({ item, onToggle }) {
  const [isOpen, setIsOpen] = useState(false)
  const detailsRef = useRef(null)
  const isFirstRender = useRef(true)

  useLayoutEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false
      return
    }
    if (detailsRef.current && onToggle) {
      const row = detailsRef.current.closest('.transcript-virtual-row')
      if (row) {
        onToggle(row)
      }
    }
  }, [isOpen, onToggle])

  const hasInput = Object.prototype.hasOwnProperty.call(item, 'input')
  const hasOutput = Object.prototype.hasOwnProperty.call(item, 'output')

  const handleToggle = (e) => {
    const nextOpen = e.currentTarget.open
    if (nextOpen !== isOpen) {
      setIsOpen(nextOpen)
    } else if (onToggle && detailsRef.current) {
      const row = detailsRef.current.closest('.transcript-virtual-row')
      if (row) onToggle(row)
    }
  }

  const isCommand = item.contentType === 'command'
  const label = isCommand ? 'Command' : 'Tool'
  const cardClass = isCommand ? 'transcript-command-card' : 'transcript-tool-card'

  return (
    <details
      ref={detailsRef}
      className={`transcript-card ${cardClass} transcript-tool-disclosure`}
      onToggle={handleToggle}
    >
      <summary className="transcript-tool-summary">
        <div className="transcript-tool-summary-main">
          <span className="eyebrow">{label}</span>
          <span className="tool-name">
            <strong>{item.tool_name}</strong>
          </span>
          {(item.call_id || item.entity_id) && (
            <code className="cell-code caption transcript-identifier">
              {item.call_id || item.entity_id}
            </code>
          )}
        </div>
        <StatusBadge status={item.status} label={item.status} />
      </summary>
      {isOpen && (
        <div className="transcript-tool-body">
          <div className="transcript-payload-section">
            <span className="eyebrow transcript-payload-label">Input</span>
            {hasInput ? (
              <pre className="transcript-payload-code">
                {formatPayload(item.input)}
              </pre>
            ) : (
              <p className="caption transcript-payload-empty">
                Input was not captured for this event.
              </p>
            )}
          </div>
          <div className="transcript-payload-section">
            <span className="eyebrow transcript-payload-label">Output</span>
            {hasOutput ? (
              <pre className="transcript-payload-code">
                {formatPayload(item.output)}
              </pre>
            ) : (
              <p className="caption transcript-payload-empty">
                Output was not captured for this event.
              </p>
            )}
          </div>
        </div>
      )}
    </details>
  )
}

const DEFAULT_ROLE_FILTERS = {
  user: true,
  assistant: true,
}

const DEFAULT_CONTENT_FILTERS = {
  text: true,
  thinking: false,
  tool_call: true,
  command: true,
}

export default function JobTranscript({
  entities = [],
  status = 'live',
  streamStatus = 'active',
  error = null,
  isLoading = false,
  onRefresh,
  submittedPrompt = '',
}) {
  const parentRef = useRef(null)
  const [isFollowing, setIsFollowing] = useState(true)
  const isFollowingRef = useRef(true)
  isFollowingRef.current = isFollowing

  const [roleFilters, setRoleFilters] = useState(DEFAULT_ROLE_FILTERS)
  const [contentFilters, setContentFilters] = useState(DEFAULT_CONTENT_FILTERS)

  const handleResetFilters = useCallback(() => {
    setRoleFilters(DEFAULT_ROLE_FILTERS)
    setContentFilters(DEFAULT_CONTENT_FILTERS)
  }, [])

  const manualPointerScrollRef = useRef(false)
  const prevScrollTopRef = useRef(0)
  const touchStartYRef = useRef(0)

  const flatItems = useMemo(() => {
    const items = []

    if (submittedPrompt && roleFilters.user && contentFilters.text) {
      items.push({
        key: 'submitted-prompt',
        type: 'user_message',
        item: {
          role: 'user',
          contentType: 'text',
          text: submittedPrompt,
        },
      })
    }

    for (const attempt of entities) {
      const visibleItems = attempt.items.filter((it) => {
        if (it.type === 'notice' || it.type === 'truncated') {
          return true
        }
        const role = it.role || 'assistant'
        const contentType =
          it.contentType ||
          (it.type === 'reasoning_summary'
            ? 'thinking'
            : it.type === 'tool_call'
            ? 'tool_call'
            : 'text')
        return Boolean(roleFilters[role] && contentFilters[contentType])
      })

      if (visibleItems.length > 0) {
        items.push({
          key: `attempt-header-${attempt.attempt}`,
          type: 'attempt_header',
          attempt,
        })
        for (let i = 0; i < visibleItems.length; i += 1) {
          const it = visibleItems[i]
          items.push({
            key: `${attempt.attempt}-${it.type}-${it.parent_entity_id || ''}-${it.entity_id || it.call_id || i}`,
            type: it.type,
            item: it,
            attempt,
          })
        }
      }
    }
    return items
  }, [entities, submittedPrompt, roleFilters, contentFilters])

  const virtualizer = useVirtualizer({
    count: flatItems.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 72,
    overscan: 5,
    gap: 8,
    useFlushSync: false,
    initialRect: { width: 800, height: 600 },
    getItemKey: (index) => flatItems[index]?.key || index,
    observeElementRect: (instance, cb) => {
      const element = instance.scrollElement
      if (!element) return
      const handler = () => {
        const width = element.clientWidth || element.offsetWidth || 800
        const height = element.clientHeight || element.offsetHeight || 600
        cb({ width, height })
      }
      handler()
      const targetWindow = instance.targetWindow || window
      if (!targetWindow.ResizeObserver) return () => {}
      const observer = new targetWindow.ResizeObserver(handler)
      observer.observe(element)
      return () => observer.disconnect()
    },
    measureElement: (element) => {
      const rect = element.getBoundingClientRect()
      return rect.height || element.offsetHeight || 72
    },
  })

  const scrollToLive = useCallback(() => {
    if (virtualizer && typeof virtualizer.scrollToEnd === 'function') {
      virtualizer.scrollToEnd({ behavior: 'auto' })
    }
    if (parentRef.current && typeof parentRef.current.scrollTo === 'function') {
      parentRef.current.scrollTo({
        top: parentRef.current.scrollHeight,
        behavior: 'auto',
      })
      prevScrollTopRef.current = parentRef.current.scrollTop
    }
  }, [virtualizer])

  const contentSignature = useMemo(() => {
    let len = 0
    for (const it of flatItems) {
      if (it.type === 'assistant_message' || it.type === 'reasoning_summary') {
        len += it.item?.text?.length || 0
      }
    }
    return `${flatItems.length}:${len}`
  }, [flatItems])

  const prevSignatureRef = useRef('')

  useEffect(() => {
    const isInitial = prevSignatureRef.current === ''
    const isChanged = prevSignatureRef.current !== contentSignature
    prevSignatureRef.current = contentSignature

    if ((isInitial || isChanged) && isFollowingRef.current) {
      scrollToLive()
    }
  }, [contentSignature, scrollToLive])

  useEffect(() => {
    const handleResize = () => {
      if (!parentRef.current || !virtualizer) return
      const rowElements = parentRef.current.querySelectorAll('.transcript-virtual-row')
      rowElements.forEach((el) => {
        if (typeof virtualizer.measureElement === 'function') {
          virtualizer.measureElement(el)
        }
      })
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [virtualizer])

  const handleToggle = useCallback(
    (target) => {
      if (!virtualizer) return
      const row =
        target instanceof Element
          ? (target.classList?.contains('transcript-virtual-row')
              ? target
              : target.closest?.('.transcript-virtual-row'))
          : target?.currentTarget?.closest?.('.transcript-virtual-row')

      if (row && typeof virtualizer.measureElement === 'function') {
        virtualizer.measureElement(row)
      }
    },
    [virtualizer]
  )

  const handleWheel = (e) => {
    if (e.deltaY < 0) {
      setIsFollowing(false)
    }
  }

  const handleTouchStart = (e) => {
    if (e.touches && e.touches.length > 0) {
      touchStartYRef.current = e.touches[0].clientY
    }
  }

  const handleTouchMove = (e) => {
    if (e.touches && e.touches.length > 0) {
      const deltaY = e.touches[0].clientY - touchStartYRef.current
      if (deltaY > 5) {
        setIsFollowing(false)
      }
    }
  }

  const handleKeyDown = (e) => {
    if (
      e.key === 'ArrowUp' ||
      e.key === 'PageUp' ||
      e.key === 'Home' ||
      (e.key === ' ' && e.shiftKey)
    ) {
      setIsFollowing(false)
    }
  }

  const handlePointerDown = (e) => {
    if (e.target === e.currentTarget) {
      manualPointerScrollRef.current = true
    }
  }

  const handlePointerEnd = () => {
    manualPointerScrollRef.current = false
  }

  const handleScroll = () => {
    if (!parentRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = parentRef.current

    const prevScrollTop = prevScrollTopRef.current
    prevScrollTopRef.current = scrollTop

    const maxScroll = Math.max(0, scrollHeight - clientHeight)
    const isUpward =
      scrollTop < prevScrollTop - 2 ||
      (maxScroll > 0 && scrollTop < maxScroll - 50)

    if (isUpward && manualPointerScrollRef.current) {
      setIsFollowing(false)
    }
  }

  const handleJumpToLive = () => {
    setIsFollowing(true)
    isFollowingRef.current = true
    scrollToLive()
  }

  const INITIAL_BOUNDED_COUNT = 20
  const virtualItems = virtualizer.getVirtualItems()
  const renderItems =
    virtualItems.length > 0
      ? virtualItems.map((virtualRow) => ({
          ...flatItems[virtualRow.index],
          virtualRow,
        }))
      : flatItems.slice(0, INITIAL_BOUNDED_COUNT).map((it, idx) => ({
          ...it,
          virtualRow: {
            index: idx,
            start: idx * (72 + 8),
            size: 72,
          },
        }))

  const statusMessage = getStatusLabel(status, streamStatus)
  const isUnavailable =
    streamStatus === 'unavailable' ||
    (entities.length === 0 && (status === 'complete' || streamStatus === 'complete'))

  return (
    <section className="panel job-transcript-panel" aria-labelledby="job-transcript-heading">
      <div className="panel-header">
        <div className="transcript-header-title">
          <h3 id="job-transcript-heading">Live transcript</h3>
          <span className={`transcript-status-badge status-badge-${status}`}>
            <span
              className={`status-dot status-dot-${
                status === 'live' ? 'running' : status === 'failed' ? 'failed' : 'neutral'
              }`}
              aria-hidden="true"
            />
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
          <div className="transcript-toolbar">
            <div className="transcript-filters">
              <fieldset className="transcript-filter-group">
                <legend>Role</legend>
                <label className="transcript-filter-label">
                  <input
                    type="checkbox"
                    checked={roleFilters.user}
                    onChange={(e) =>
                      setRoleFilters((prev) => ({ ...prev, user: e.target.checked }))
                    }
                  />
                  <span>User</span>
                </label>
                <label className="transcript-filter-label">
                  <input
                    type="checkbox"
                    checked={roleFilters.assistant}
                    onChange={(e) =>
                      setRoleFilters((prev) => ({ ...prev, assistant: e.target.checked }))
                    }
                  />
                  <span>Assistant</span>
                </label>
              </fieldset>

              <fieldset className="transcript-filter-group">
                <legend>Content</legend>
                <label className="transcript-filter-label">
                  <input
                    type="checkbox"
                    checked={contentFilters.text}
                    onChange={(e) =>
                      setContentFilters((prev) => ({ ...prev, text: e.target.checked }))
                    }
                  />
                  <span>Text</span>
                </label>
                <label className="transcript-filter-label">
                  <input
                    type="checkbox"
                    checked={contentFilters.thinking}
                    onChange={(e) =>
                      setContentFilters((prev) => ({ ...prev, thinking: e.target.checked }))
                    }
                  />
                  <span>Thinking</span>
                </label>
                <label className="transcript-filter-label">
                  <input
                    type="checkbox"
                    checked={contentFilters.tool_call}
                    onChange={(e) =>
                      setContentFilters((prev) => ({ ...prev, tool_call: e.target.checked }))
                    }
                  />
                  <span>Tool Call</span>
                </label>
                <label className="transcript-filter-label">
                  <input
                    type="checkbox"
                    checked={contentFilters.command}
                    onChange={(e) =>
                      setContentFilters((prev) => ({ ...prev, command: e.target.checked }))
                    }
                  />
                  <span>Command</span>
                </label>
              </fieldset>
            </div>
          </div>

          {flatItems.length === 0 ? (
            <div className="transcript-filter-empty">
              <p className="caption">No transcript entries match the current filters.</p>
              <button
                type="button"
                className="button button-ghost button-sm"
                onClick={handleResetFilters}
              >
                Reset filters
              </button>
            </div>
          ) : (
            <div
              ref={parentRef}
              className="transcript-scroll-container"
              data-testid="transcript-scroll-container"
              onScroll={handleScroll}
              onWheel={handleWheel}
              onTouchStart={handleTouchStart}
              onTouchMove={handleTouchMove}
              onPointerDown={handlePointerDown}
              onPointerUp={handlePointerEnd}
              onPointerCancel={handlePointerEnd}
              onKeyDown={handleKeyDown}
              tabIndex={0}
              role="region"
              aria-label="Job execution transcript"
            >
              <div
                className="transcript-virtual-inner"
                style={{
                  height: `${virtualizer.getTotalSize()}px`,
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

                  let content = null

                  if (type === 'attempt_header') {
                    content = (
                      <div className="transcript-attempt-header">
                        <div className="attempt-title">
                          <strong>Attempt {attempt.attempt}</strong>
                          {attempt.target_id && (
                            <code className="cell-code transcript-identifier">
                              {attempt.target_id}
                            </code>
                          )}
                          {attempt.backend && (
                            <span className="profile-tag">{attempt.backend}</span>
                          )}
                        </div>
                        <StatusBadge status={attempt.status} label={attempt.status} />
                      </div>
                    )
                  } else if (type === 'user_message') {
                    content = (
                      <div className="transcript-card transcript-user-card">
                        <div className="transcript-card-header">
                          <span className="eyebrow">User</span>
                        </div>
                        <div className="transcript-user-text transcript-text">
                          {item.text}
                        </div>
                      </div>
                    )
                  } else if (type === 'assistant_message') {
                    content = (
                      <div className="transcript-card transcript-assistant-card">
                        <div className="transcript-card-header">
                          <span className="eyebrow">Assistant</span>
                          {item.status === 'streaming' && (
                            <span
                              className="streaming-indicator"
                              aria-label="Streaming in progress"
                            >
                              <span
                                className="status-dot status-dot-running"
                                aria-hidden="true"
                              />
                              streaming…
                            </span>
                          )}
                        </div>
                        <div className="transcript-assistant-text transcript-text">
                          {item.text}
                        </div>
                      </div>
                    )
                  } else if (type === 'reasoning_summary') {
                    content = (
                      <div className="transcript-card transcript-thinking-card">
                        <div className="transcript-card-header">
                          <span className="eyebrow">Thinking</span>
                        </div>
                        <div className="transcript-thinking-text transcript-text">
                          {item.text}
                        </div>
                      </div>
                    )
                  } else if (type === 'tool_call') {
                    content = <ToolCallItem item={item} onToggle={handleToggle} />
                  } else if (type === 'notice') {
                    content = (
                      <div className="transcript-card transcript-notice-card">
                        <p className="caption">{item.text}</p>
                      </div>
                    )
                  } else if (type === 'truncated') {
                    content = (
                      <div className="transcript-card transcript-truncated-card">
                        <span className="eyebrow">Stream truncated</span>
                        <p className="caption">Reason: {item.reason}</p>
                      </div>
                    )
                  }

                  if (!content) return null

                  return (
                    <div
                      key={key}
                      ref={virtualizer.measureElement}
                      data-index={virtualRow ? virtualRow.index : undefined}
                      style={style}
                      className="transcript-virtual-row"
                    >
                      {content}
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {!isFollowing && (
            <button
              type="button"
              className="button button-primary button-sm transcript-jump-live-btn"
              onClick={handleJumpToLive}
              aria-label="Jump to live"
            >
              ↓ Jump to live
            </button>
          )}
        </div>
      )}
    </section>
  )
}
