import { useState, useEffect, useRef, useCallback } from 'react'
import {
  fetchOverview,
  fetchProjects,
  fetchProject,
  fetchTargets,
  fetchProfiles,
  fetchSettings,
  fetchDiagnostics,
  fetchProjectJobs,
  fetchJob,
  isTerminalState,
} from '../api.js'

const BACKOFF_INTERVAL_MS = 10000

export function usePolling({
  fetcher,
  interval = 3000,
  enabled = true,
  isTerminal = null,
}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isStale, setIsStale] = useState(false)

  const timerRef = useRef(null)
  const activeFetcherRef = useRef(fetcher)
  const isTerminalRef = useRef(isTerminal)
  const enabledRef = useRef(enabled)
  const intervalRef = useRef(interval)
  const isMountedRef = useRef(true)
  const generationRef = useRef(0)

  activeFetcherRef.current = fetcher
  isTerminalRef.current = isTerminal
  enabledRef.current = enabled
  intervalRef.current = interval

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const poll = useCallback(async () => {
    clearTimer()

    if (!enabledRef.current || !isMountedRef.current) {
      return
    }

    if (document.visibilityState === 'hidden') {
      return
    }

    const generation = ++generationRef.current
    let nextInterval = intervalRef.current
    try {
      const result = await activeFetcherRef.current()
      if (!isMountedRef.current || !enabledRef.current || generation !== generationRef.current) {
        return
      }

      setData(result)
      setError(null)
      setIsLoading(false)
      setIsStale(false)

      if (isTerminalRef.current && isTerminalRef.current(result)) {
        // Job is terminal; stop scheduling further polls
        return
      }
    } catch (err) {
      if (!isMountedRef.current || !enabledRef.current || generation !== generationRef.current) {
        return
      }
      setError(err)
      setIsLoading(false)
      setIsStale(true)
      nextInterval = BACKOFF_INTERVAL_MS
    }

    if (isMountedRef.current && enabledRef.current && document.visibilityState !== 'hidden' && generation === generationRef.current) {
      timerRef.current = setTimeout(poll, nextInterval)
    }
  }, [clearTimer])

  useEffect(() => {
    isMountedRef.current = true

    if (!enabled) {
      generationRef.current += 1
      clearTimer()
      return
    }

    // Trigger initial poll
    poll()

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        poll()
      } else {
        generationRef.current += 1
        clearTimer()
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      isMountedRef.current = false
      generationRef.current += 1
      clearTimer()
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [enabled, poll, clearTimer])

  const lastFetcherRef = useRef(fetcher)
  useEffect(() => {
    if (lastFetcherRef.current !== fetcher) {
      lastFetcherRef.current = fetcher
      generationRef.current += 1
      setData(null)
      setIsLoading(true)
      if (enabled && document.visibilityState !== 'hidden') {
        poll()
      }
    }
  }, [fetcher, enabled, poll])

  const refetch = useCallback(() => {
    return poll()
  }, [poll])

  return { data, error, isLoading, isStale, refetch }
}

export function useOverview(options = {}) {
  const fetcher = options.fetcher || fetchOverview
  return usePolling({
    fetcher,
    interval: 3000,
    ...options,
  })
}

export function useProjectJobs(projectId, options = {}) {
  const fetcher = useCallback(
    () => (options.fetcher ? options.fetcher() : fetchProjectJobs(projectId)),
    [projectId, options.fetcher]
  )
  return usePolling({
    fetcher,
    interval: 2000,
    enabled: Boolean(projectId) && (options.enabled ?? true),
    ...options,
  })
}

export function useJob(jobId, options = {}) {
  const fetcher = useCallback(
    () => (options.fetcher ? options.fetcher() : fetchJob(jobId)),
    [jobId, options.fetcher]
  )
  const isTerminal = useCallback(
    (job) => Boolean(job && isTerminalState(job.state)),
    []
  )
  return usePolling({
    fetcher,
    interval: 2000,
    enabled: Boolean(jobId) && (options.enabled ?? true),
    isTerminal,
    ...options,
  })
}

export function useProjects(options = {}) {
  const fetcher = options.fetcher || fetchProjects
  return usePolling({
    fetcher,
    interval: 5000,
    ...options,
  })
}

export function useProject(projectId, options = {}) {
  const fetcher = useCallback(
    () => (options.fetcher ? options.fetcher() : fetchProject(projectId)),
    [projectId, options.fetcher]
  )
  return usePolling({
    fetcher,
    interval: 5000,
    enabled: Boolean(projectId) && (options.enabled ?? true),
    ...options,
  })
}

export function useTargets(options = {}) {
  const fetcher = options.fetcher || fetchTargets
  return usePolling({
    fetcher,
    interval: 3000,
    ...options,
  })
}

export function useProfiles(options = {}) {
  const fetcher = options.fetcher || fetchProfiles
  return usePolling({
    fetcher,
    interval: 3000,
    ...options,
  })
}

export function useSettings(options = {}) {
  const fetcher = options.fetcher || fetchSettings
  return usePolling({
    fetcher,
    interval: 5000,
    ...options,
  })
}

export function useDiagnostics(params = {}, options = {}) {
  const paramsKey = JSON.stringify(params)
  const fetcher = useCallback(
    async () => {
      const result = options.fetcher ? await options.fetcher() : await fetchDiagnostics(params)
      return { ...result, _queryKey: paramsKey }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [paramsKey, options.fetcher]
  )
  return usePolling({
    fetcher,
    interval: 5000,
    ...options,
  })
}
