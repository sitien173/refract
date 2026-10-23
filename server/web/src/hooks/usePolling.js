import { useEffect, useRef, useState } from 'react'
import { POLL_INTERVAL_MS } from './constants'

export function usePolling(callback, interval = POLL_INTERVAL_MS, { enabled = true, isTerminal = false, deps = [] } = {}) {
  const [error, setError] = useState(null)
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  useEffect(() => {
    if (!enabled || isTerminal || interval <= 0) return

    let timerId = null
    let cancelled = false
    let running = false

    async function tick() {
      if (cancelled || document.hidden || running) return
      running = true
      try {
        await callbackRef.current()
        if (!cancelled) setError(null)
      } catch (err) {
        if (!cancelled) setError(err)
      } finally {
        running = false
        if (!cancelled && !isTerminal) {
          timerId = setTimeout(tick, interval)
        }
      }
    }

    function handleVisibilityChange() {
      if (!document.hidden && !cancelled && !isTerminal) {
        if (timerId) clearTimeout(timerId)
        void tick()
      }
    }

    timerId = setTimeout(tick, interval)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      cancelled = true
      if (timerId) clearTimeout(timerId)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [enabled, isTerminal, interval, ...deps])

  return { error }
}
