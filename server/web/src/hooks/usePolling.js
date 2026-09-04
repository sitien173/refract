import { useEffect, useRef } from 'react'

export function usePolling(callback, interval = 5000, { enabled = true, isTerminal = false, deps = [] } = {}) {
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  useEffect(() => {
    if (!enabled || isTerminal || interval <= 0) return

    let timerId = null
    let cancelled = false

    async function tick() {
      if (cancelled || document.hidden) return
      try {
        await callbackRef.current()
      } catch {
        // preserve loaded data on failure
      } finally {
        if (!cancelled && !isTerminal) {
          timerId = setTimeout(tick, interval)
        }
      }
    }

    function handleVisibilityChange() {
      if (!document.hidden && !cancelled && !isTerminal) {
        if (timerId) clearTimeout(timerId)
        tick()
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
}
