import { useCallback, useEffect, useRef, useState } from 'react'

export function useDashboardQuery(queryFn, { pollInterval = 0, enabled = true, deps = [] } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const queryFnRef = useRef(queryFn)
  queryFnRef.current = queryFn

  const requestIdRef = useRef(0)
  const timerRef = useRef(null)
  const isMountedRef = useRef(true)
  const isRunningRef = useRef(false)
  const hasLoadedOnceRef = useRef(false)

  const clearPollTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  const execute = useCallback(async (isManualOrPoll = false, supersede = false) => {
    if (!enabled) return
    // A dependency change represents a new query identity and must not be
    // blocked by the previous promise still being in flight. Manual refreshes
    // and timers retain the no-overlap guard.
    if (isRunningRef.current && !supersede) return
    isRunningRef.current = true

    const currentRequestId = ++requestIdRef.current
    if (isManualOrPoll || hasLoadedOnceRef.current) {
      setIsRefreshing(true)
    } else {
      setIsLoading(true)
    }

    try {
      const result = await queryFnRef.current()
      if (!isMountedRef.current || currentRequestId !== requestIdRef.current) {
        return
      }
      setData(result)
      setError(null)
      hasLoadedOnceRef.current = true
    } catch (err) {
      if (!isMountedRef.current || currentRequestId !== requestIdRef.current) {
        return
      }
      // Preserve previously loaded data on refresh failure!
      setError(err)
    } finally {
      if (isMountedRef.current && currentRequestId === requestIdRef.current) {
        setIsLoading(false)
        setIsRefreshing(false)
        isRunningRef.current = false
        if (pollInterval > 0 && enabled) {
          clearPollTimer()
          timerRef.current = setTimeout(() => {
            execute(true)
          }, pollInterval)
        }
      }
    }
  }, [enabled, pollInterval])

  useEffect(() => {
    isMountedRef.current = true
    execute(false, true)

    return () => {
      isMountedRef.current = false
      clearPollTimer()
      requestIdRef.current += 1
    }
  }, [execute, ...deps])

  const refresh = useCallback(() => {
    clearPollTimer()
    // A user refresh is an explicit request for newer data and supersedes an
    // in-flight poll; stale completion is ignored by requestIdRef.
    return execute(true, true)
  }, [execute])

  return { data, error, isLoading, isRefreshing, refresh }
}
