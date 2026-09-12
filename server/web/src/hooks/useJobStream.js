import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getJobOutput } from '../api'

const TERMINAL_STREAM_STATUSES = new Set(['complete', 'failed', 'truncated', 'unavailable'])

export function reduceTranscriptEvents(events = []) {
  if (!events || events.length === 0) return []

  const attemptsMap = new Map() // attemptNum -> attemptObj
  const sorted = [...events].sort((a, b) => a.id - b.id)

  for (const event of sorted) {
    const attemptNum = event.attempt || 1
    if (!attemptsMap.has(attemptNum)) {
      attemptsMap.set(attemptNum, {
        type: 'attempt',
        attempt: attemptNum,
        target_id: event.target_id || '',
        backend: event.backend || '',
        status: 'running',
        started_at: event.created_at || '',
        ended_at: null,
        items: [],
      })
    }
    const attempt = attemptsMap.get(attemptNum)
    if (event.target_id && !attempt.target_id) attempt.target_id = event.target_id
    if (event.backend && !attempt.backend) attempt.backend = event.backend

    const { kind, entity_id, data = {} } = event

    if (kind === 'attempt.started') {
      attempt.started_at = event.created_at || attempt.started_at
      if (data.target_id && !attempt.target_id) attempt.target_id = data.target_id
      if (data.backend && !attempt.backend) attempt.backend = data.backend
    } else if (kind === 'attempt.finished' || kind === 'attempt.completed') {
      attempt.ended_at = event.created_at || attempt.ended_at
      attempt.status = data.status || data.outcome || 'succeeded'
    } else if (kind === 'assistant.message.started' || kind === 'assistant.message_start') {
      attempt.items.push({
        type: 'assistant_message',
        entity_id: entity_id || `msg-${event.id}`,
        text: data.text || '',
        status: 'streaming',
      })
    } else if (kind === 'assistant.text.delta' || kind === 'assistant.text_delta') {
      const targetId = entity_id || ''
      let item = null
      if (targetId) {
        item = attempt.items.find((it) => it.type === 'assistant_message' && it.entity_id === targetId)
      } else {
        const last = attempt.items[attempt.items.length - 1]
        if (last && last.type === 'assistant_message' && last.status !== 'completed') {
          item = last
        }
      }
      if (!item) {
        item = {
          type: 'assistant_message',
          entity_id: targetId || `msg-${event.id}`,
          text: '',
          status: 'streaming',
        }
        attempt.items.push(item)
      }
      item.text += data.text || ''
    } else if (kind === 'assistant.message.completed' || kind === 'assistant.message_end') {
      const targetId = entity_id || ''
      const item = targetId
        ? attempt.items.find((it) => it.type === 'assistant_message' && it.entity_id === targetId)
        : [...attempt.items].reverse().find((it) => it.type === 'assistant_message' && it.status !== 'completed')
      if (item) {
        item.status = 'completed'
      }
    } else if (kind === 'tool.started' || kind === 'tool.call_start') {
      const toolItem = {
        type: 'tool_call',
        entity_id: entity_id || `tool-${event.id}`,
        tool_name: data.tool || data.tool_name || data.name || 'tool',
        status: 'running',
        call_id: data.call_id || data.callId || entity_id || '',
      }
      if (Object.prototype.hasOwnProperty.call(data, 'input')) {
        toolItem.input = data.input
      }
      attempt.items.push(toolItem)
    } else if (kind === 'tool.completed' || kind === 'tool.call_end') {
      const targetId = entity_id || ''
      let item = null
      if (targetId) {
        item = attempt.items.find((it) => it.type === 'tool_call' && it.entity_id === targetId)
      } else {
        const legacyCallId = data.call_id || data.callId || ''
        if (legacyCallId) {
          item = attempt.items.find((it) => it.type === 'tool_call' && (it.call_id === legacyCallId || it.entity_id === legacyCallId))
        }
        if (!item) {
          item = [...attempt.items].reverse().find((it) => it.type === 'tool_call' && it.status === 'running')
        }
      }
      if (item) {
        item.status = data.status || data.outcome || 'completed'
        if (Object.prototype.hasOwnProperty.call(data, 'output')) {
          item.output = data.output
        }
      }
    } else if (kind === 'stream.notice') {
      attempt.items.push({
        type: 'notice',
        entity_id: entity_id || `notice-${event.id}`,
        text: data.text || '',
      })
    } else if (kind === 'stream.truncated') {
      attempt.items.push({
        type: 'truncated',
        entity_id: entity_id || `trunc-${event.id}`,
        reason: data.reason || 'quota_exceeded',
      })
    }
  }

  return Array.from(attemptsMap.values())
}

export function useJobStream(jobId, options = {}) {
  const { isTerminal = false, pollIntervalMs = 5000 } = options

  const [events, setEvents] = useState([])
  const [cursor, setCursor] = useState(0)
  const [retainedFrom, setRetainedFrom] = useState(0)
  const [streamStatus, setStreamStatus] = useState('active')
  const [status, setStatus] = useState('connecting')
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(false)

  const activeJobIdRef = useRef(jobId)
  activeJobIdRef.current = jobId

  const cursorRef = useRef(0)
  const notifiedCursorRef = useRef(0)
  const inFlightJobRef = useRef(null)
  const abortControllerRef = useRef(null)
  const esRef = useRef(null)
  const fetchEpochRef = useRef(0)

  const entities = useMemo(() => reduceTranscriptEvents(events), [events])

  const drainPages = useCallback(
    async (targetJobId, signal) => {
      if (!targetJobId || activeJobIdRef.current !== targetJobId || signal?.aborted) return
      if (inFlightJobRef.current === targetJobId) return

      inFlightJobRef.current = targetJobId
      const fetchEpoch = ++fetchEpochRef.current
      setIsLoading(true)

      try {
        let currentCursor = cursorRef.current
        let keepGoing = true

        while (keepGoing && !signal?.aborted && activeJobIdRef.current === targetJobId) {
          const response = await getJobOutput(targetJobId, { after: currentCursor, limit: 100 }, signal)
          if (signal?.aborted || activeJobIdRef.current !== targetJobId || fetchEpochRef.current !== fetchEpoch) {
            return
          }

          if (response.events && response.events.length > 0) {
            setEvents((prev) => {
              if (activeJobIdRef.current !== targetJobId) return prev
              const existingIds = new Set(prev.map((e) => e.id))
              const newEvents = response.events.filter((e) => !existingIds.has(e.id))
              return newEvents.length > 0 ? [...prev, ...newEvents] : prev
            })
          }

          if (activeJobIdRef.current !== targetJobId || fetchEpochRef.current !== fetchEpoch) return

          currentCursor = response.cursor ?? currentCursor
          cursorRef.current = currentCursor
          setCursor(currentCursor)
          if (response.retained_from !== undefined) setRetainedFrom(response.retained_from)
          if (response.stream_status) setStreamStatus(response.stream_status)
          setError(null)

          if (response.has_more) {
            keepGoing = true
          } else if (currentCursor < notifiedCursorRef.current) {
            keepGoing = true
          } else {
            keepGoing = false
          }
        }
      } catch (err) {
        if (!signal?.aborted && activeJobIdRef.current === targetJobId && fetchEpochRef.current === fetchEpoch) {
          setError(err)
        }
      } finally {
        if (inFlightJobRef.current === targetJobId && fetchEpochRef.current === fetchEpoch) {
          inFlightJobRef.current = null
        }
        if (activeJobIdRef.current === targetJobId && fetchEpochRef.current === fetchEpoch) {
          setIsLoading(false)
        }
      }
    },
    []
  )

  const refresh = useCallback(() => {
    if (!jobId) return Promise.resolve()
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    inFlightJobRef.current = null
    const controller = new AbortController()
    abortControllerRef.current = controller
    return drainPages(jobId, controller.signal)
  }, [jobId, drainPages])

  const prevTerminalRef = useRef({ jobId, isTerminal })

  useEffect(() => {
    const prev = prevTerminalRef.current
    prevTerminalRef.current = { jobId, isTerminal }

    if (prev.jobId === jobId && !prev.isTerminal && isTerminal) {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      inFlightJobRef.current = null
      const controller = new AbortController()
      abortControllerRef.current = controller

      drainPages(jobId, controller.signal).finally(() => {
        if (activeJobIdRef.current === jobId) {
          if (esRef.current) {
            esRef.current.close()
            esRef.current = null
          }
        }
      })
    }
  }, [jobId, isTerminal, drainPages])

  // Setup initial fetch and EventSource
  useEffect(() => {
    if (!jobId) {
      setEvents([])
      setCursor(0)
      setRetainedFrom(0)
      setStatus('connecting')
      setError(null)
      cursorRef.current = 0
      notifiedCursorRef.current = 0
      inFlightJobRef.current = null
      return
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    inFlightJobRef.current = null

    // Reset state for new job
    setEvents([])
    setCursor(0)
    setRetainedFrom(0)
    setStatus('connecting')
    setError(null)
    cursorRef.current = 0
    notifiedCursorRef.current = 0

    const controller = new AbortController()
    abortControllerRef.current = controller

    // Start initial fetch
    drainPages(jobId, controller.signal).then(() => {
      if (!controller.signal.aborted && activeJobIdRef.current === jobId) {
        setStatus((prev) => (prev === 'connecting' ? 'live' : prev))
      }
    })

    // Setup EventSource if available
    let es = null
    if (!isTerminal && typeof window !== 'undefined' && typeof window.EventSource !== 'undefined') {
      const url = `/dashboard/api/jobs/${encodeURIComponent(jobId)}/output/updates`
      es = new window.EventSource(url)
      esRef.current = es

      es.onopen = () => {
        if (!controller.signal.aborted && activeJobIdRef.current === jobId) {
          setStatus('live')
        }
      }

      es.addEventListener('output-updated', (event) => {
        if (controller.signal.aborted || activeJobIdRef.current !== jobId) return
        try {
          const payload = JSON.parse(event.data)
          const newCursor = Number(payload.cursor)
          if (!Number.isNaN(newCursor)) {
            if (newCursor > notifiedCursorRef.current) {
              notifiedCursorRef.current = newCursor
            }
            if (newCursor > cursorRef.current) {
              drainPages(jobId, controller.signal)
            }
          }
        } catch {
          // ignore parse error
        }
      })

      es.onerror = () => {
        if (!controller.signal.aborted && activeJobIdRef.current === jobId && es.readyState !== 2) {
          setStatus('reconnecting')
        }
      }
    }

    return () => {
      controller.abort()
      inFlightJobRef.current = null
      if (es) {
        es.close()
        esRef.current = null
      }
    }
  }, [jobId, drainPages])

  // Periodic fallback polling when reconnecting or if EventSource unavailable
  useEffect(() => {
    if (!jobId || isTerminal || TERMINAL_STREAM_STATUSES.has(streamStatus)) return
    if (status !== 'reconnecting' && esRef.current !== null) return

    const timer = setInterval(() => {
      if (abortControllerRef.current && !abortControllerRef.current.signal.aborted && activeJobIdRef.current === jobId) {
        drainPages(jobId, abortControllerRef.current.signal)
      }
    }, pollIntervalMs)

    return () => clearInterval(timer)
  }, [jobId, isTerminal, streamStatus, status, pollIntervalMs, drainPages])

  return {
    events,
    entities,
    cursor,
    retainedFrom,
    streamStatus,
    status,
    error,
    isLoading,
    refresh,
  }
}
