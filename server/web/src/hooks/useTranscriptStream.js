import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  fetchJobOutput,
  getJobOutputUpdatesUrl,
  isTerminalState,
} from '../api.js'

export function processTranscriptEvents(events = []) {
  const processed = []
  const toolMap = new Map()

  for (const event of events) {
    if (event.kind === 'assistant.text_delta') {
      const textChunk = event.data?.text ?? event.data?.delta ?? ''
      const lastItem = processed[processed.length - 1]
      if (
        lastItem &&
        lastItem.kind === 'assistant.text' &&
        lastItem.entity_id === event.entity_id
      ) {
        lastItem.text += textChunk
        lastItem.end_id = event.id
      } else {
        processed.push({
          id: event.id,
          kind: 'assistant.text',
          entity_id: event.entity_id,
          text: textChunk,
          created_at: event.created_at,
        })
      }
    } else if (event.kind === 'tool.started') {
      const toolName =
        event.data?.tool || event.data?.name || event.data?.tool_name || 'tool'
      const item = {
        id: event.id,
        kind: 'tool.call',
        entity_id: event.entity_id,
        name: toolName,
        input: event.data?.input,
        status: 'running',
        created_at: event.created_at,
      }
      toolMap.set(event.entity_id, item)
      processed.push(item)
    } else if (event.kind === 'tool.completed') {
      const rawStatus = event.data?.status
      const hasError = Boolean(event.data?.error || event.data?.isError)
      const resolvedStatus =
        rawStatus === 'error' || rawStatus === 'failed' || hasError
          ? rawStatus || 'failed'
          : rawStatus || 'completed'

      const existing = toolMap.get(event.entity_id)
      if (existing) {
        existing.status = resolvedStatus
        existing.output = event.data?.output ?? event.data?.result
        existing.error = event.data?.error
      } else {
        const toolName =
          event.data?.tool || event.data?.name || event.data?.tool_name || 'tool'
        const item = {
          id: event.id,
          kind: 'tool.call',
          entity_id: event.entity_id,
          name: toolName,
          status: resolvedStatus,
          output: event.data?.output ?? event.data?.result,
          error: event.data?.error,
          created_at: event.created_at,
        }
        processed.push(item)
      }
    } else {
      processed.push({
        id: event.id,
        kind: event.kind,
        entity_id: event.entity_id,
        data: event.data ?? {},
        created_at: event.created_at,
      })
    }
  }

  return processed
}

export function useTranscriptStream({ jobId, jobState, resultText = '' }) {
  const [events, setEvents] = useState([])
  const [cursor, setCursor] = useState(0)
  const [streamStatus, setStreamStatus] = useState('unavailable')
  const [retainedFrom, setRetainedFrom] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  const cursorRef = useRef(0)
  const eventSourceRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const reconnectAttemptRef = useRef(0)
  const isMountedRef = useRef(true)
  const activeJobIdRef = useRef(jobId)
  const jobStateRef = useRef(jobState)
  const prevJobStateRef = useRef(jobState)
  const activeDrainRef = useRef(null)
  const pendingDrainRef = useRef(null)
  const jobSwitchIdRef = useRef(0)
  const prevJobIdRef = useRef(null)

  activeJobIdRef.current = jobId
  jobStateRef.current = jobState

  const closeEventSource = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }, [])

  const executeDrain = useCallback((targetJobId, startingCursor = null) => {
    const currentSwitchId = jobSwitchIdRef.current

    const drainPromise = (async () => {
      let currentAfter = startingCursor !== null ? startingCursor : cursorRef.current

      try {
        while (
          isMountedRef.current &&
          activeJobIdRef.current === targetJobId &&
          jobSwitchIdRef.current === currentSwitchId
        ) {
          const page = await fetchJobOutput(targetJobId, {
            after: currentAfter,
            limit: 100,
          })

          if (
            !isMountedRef.current ||
            activeJobIdRef.current !== targetJobId ||
            jobSwitchIdRef.current !== currentSwitchId
          ) {
            break
          }

          if (page.events && page.events.length > 0) {
            setEvents((prev) => {
              const seenIds = new Set(prev.map((e) => e.id))
              const newEvents = page.events.filter((e) => !seenIds.has(e.id))
              return [...prev, ...newEvents]
            })
          }

          if (page.has_more && page.cursor <= currentAfter) {
            const err = new Error(
              `Cursor did not advance while has_more is true (cursor: ${page.cursor}, after: ${currentAfter})`
            )
            setError(err)
            break
          }

          currentAfter = page.cursor
          setCursor(page.cursor)
          cursorRef.current = page.cursor
          setStreamStatus(page.stream_status)
          setRetainedFrom(page.retained_from)

          if (!page.has_more) {
            break
          }
        }
      } catch (err) {
        if (
          isMountedRef.current &&
          activeJobIdRef.current === targetJobId &&
          jobSwitchIdRef.current === currentSwitchId
        ) {
          setError(err)
        }
      } finally {
        if (activeDrainRef.current?.promise === drainPromise) {
          activeDrainRef.current = null
        }
      }
    })()

    if (jobSwitchIdRef.current === currentSwitchId) {
      activeDrainRef.current = { jobId: targetJobId, promise: drainPromise }
    }
    return drainPromise
  }, [])

  const drainOutput = useCallback(
    (targetJobId, startingCursor = null) => {
      if (!targetJobId || !isMountedRef.current || activeJobIdRef.current !== targetJobId) {
        return Promise.resolve()
      }

      if (activeDrainRef.current?.jobId === targetJobId) {
        if (pendingDrainRef.current?.jobId === targetJobId) {
          if (startingCursor !== null) {
            pendingDrainRef.current.startingCursor =
              pendingDrainRef.current.startingCursor !== null
                ? Math.min(pendingDrainRef.current.startingCursor, startingCursor)
                : startingCursor
          }
          return pendingDrainRef.current.promise
        }

        const capturedSwitchId = jobSwitchIdRef.current
        const pendingObj = {
          jobId: targetJobId,
          startingCursor: startingCursor,
          switchId: capturedSwitchId,
          promise: null,
        }

        const activePromise = activeDrainRef.current.promise
        pendingObj.promise = activePromise
          .catch(() => {})
          .then(() => {
            if (pendingDrainRef.current === pendingObj) {
              pendingDrainRef.current = null
            }
            if (
              !isMountedRef.current ||
              activeJobIdRef.current !== targetJobId ||
              jobSwitchIdRef.current !== capturedSwitchId
            ) {
              return
            }
            return executeDrain(targetJobId, pendingObj.startingCursor)
          })

        pendingDrainRef.current = pendingObj
        return pendingObj.promise
      }

      if (pendingDrainRef.current && pendingDrainRef.current.jobId !== targetJobId) {
        pendingDrainRef.current = null
      }

      return executeDrain(targetJobId, startingCursor)
    },
    [executeDrain]
  )

  const connectEventSource = useCallback((targetJobId) => {
    closeEventSource()

    if (!targetJobId || !isMountedRef.current) return
    if (isTerminalState(jobStateRef.current)) return

    if (typeof EventSource === 'undefined') return

    const url = getJobOutputUpdatesUrl(targetJobId)
    const es = new EventSource(url)
    eventSourceRef.current = es

    // Drain missed events immediately after connecting
    drainOutput(targetJobId, cursorRef.current).then(() => {
      if (isMountedRef.current && activeJobIdRef.current === targetJobId) {
        setIsLoading(false)
      }
    })

    const handleUpdate = () => {
      drainOutput(targetJobId)
    }

    es.addEventListener('output-updated', handleUpdate)
    es.addEventListener('message', handleUpdate)

    es.onerror = () => {
      closeEventSource()

      if (
        isMountedRef.current &&
        activeJobIdRef.current === targetJobId &&
        !isTerminalState(jobStateRef.current)
      ) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 16000)
        reconnectAttemptRef.current += 1
        reconnectTimerRef.current = setTimeout(() => {
          if (
            isMountedRef.current &&
            activeJobIdRef.current === targetJobId &&
            !isTerminalState(jobStateRef.current)
          ) {
            connectEventSource(targetJobId)
          }
        }, delay)
      }
    }
  }, [closeEventSource, drainOutput])

  useEffect(() => {
    isMountedRef.current = true

    if (prevJobIdRef.current !== jobId) {
      prevJobIdRef.current = jobId
      jobSwitchIdRef.current += 1
      prevJobStateRef.current = jobStateRef.current
      setEvents([])
      setCursor(0)
      cursorRef.current = 0
      reconnectAttemptRef.current = 0
      pendingDrainRef.current = null
      setError(null)
      setIsLoading(true)

      if (!jobId) {
        closeEventSource()
        setIsLoading(false)
        return
      }

      const isTerminal = isTerminalState(jobStateRef.current)
      if (!isTerminal) {
        connectEventSource(jobId)
      } else {
        drainOutput(jobId, 0).then(() => {
          if (!isMountedRef.current || activeJobIdRef.current !== jobId) return
          setIsLoading(false)
          closeEventSource()
        })
      }
    }

    return () => {
      closeEventSource()
    }
  }, [jobId, closeEventSource, connectEventSource, drainOutput])

  useEffect(() => {
    const prevJobState = prevJobStateRef.current
    prevJobStateRef.current = jobState

    if (!isTerminalState(prevJobState) && isTerminalState(jobState)) {
      if (jobId) {
        drainOutput(jobId).then(() => {
          if (isMountedRef.current && activeJobIdRef.current === jobId) {
            closeEventSource()
          }
        })
      } else {
        closeEventSource()
      }
    }
  }, [jobState, jobId, drainOutput, closeEventSource])

  useEffect(() => {
    return () => {
      isMountedRef.current = false
      closeEventSource()
    }
  }, [closeEventSource])

  const processedItems = useMemo(() => processTranscriptEvents(events), [events])

  return {
    events,
    processedItems,
    cursor,
    streamStatus,
    retainedFrom,
    isLoading,
    error,
    fallbackText: resultText,
  }
}
