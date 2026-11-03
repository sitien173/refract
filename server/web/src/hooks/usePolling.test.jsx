import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { usePolling, useOverview, useProjectJobs, useJob } from './usePolling.js'

describe('usePolling and data hooks', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    })
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('polls fetcher periodically and updates data', async () => {
    let count = 0
    const fetcher = vi.fn().mockImplementation(async () => ({ count: ++count }))

    const { result } = renderHook(() => usePolling({ fetcher, interval: 3000 }))

    await act(async () => {
      await Promise.resolve()
    })

    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(result.current.data).toEqual({ count: 1 })
    expect(result.current.isLoading).toBe(false)
    expect(result.current.isStale).toBe(false)

    // Advance 3s
    await act(async () => {
      vi.advanceTimersByTime(3000)
      await Promise.resolve()
    })

    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(result.current.data).toEqual({ count: 2 })
  })

  it('useOverview polls at 3s interval', async () => {
    const fetcher = vi.fn().mockResolvedValue({ daemon: { status: 'running' } })
    const { result } = renderHook(() => useOverview({ fetcher }))

    await act(async () => {
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)

    await act(async () => {
      vi.advanceTimersByTime(2999)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)

    await act(async () => {
      vi.advanceTimersByTime(1)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('useProjectJobs polls at 2s interval', async () => {
    const fetcher = vi.fn().mockResolvedValue({ active: [], recent: [] })
    const { result } = renderHook(() => useProjectJobs('proj-1', { fetcher }))

    await act(async () => {
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)

    await act(async () => {
      vi.advanceTimersByTime(2000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('useJob polls at 2s interval until terminal state is reached', async () => {
    let call = 0
    const fetcher = vi.fn().mockImplementation(async () => {
      call++
      if (call === 1) return { id: 'j1', state: 'running' }
      if (call === 2) return { id: 'j1', state: 'succeeded' }
      return { id: 'j1', state: 'succeeded' }
    })

    const { result } = renderHook(() => useJob('j1', { fetcher }))

    await act(async () => {
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(result.current.data?.state).toBe('running')

    // Advance to second poll (state becomes succeeded)
    await act(async () => {
      vi.advanceTimersByTime(2000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(2)
    expect(result.current.data?.state).toBe('succeeded')

    // Advance another 5s, should NOT poll anymore
    await act(async () => {
      vi.advanceTimersByTime(5000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(2)
  })

  it('pauses polling when document is hidden and resumes when visible', async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true })
    renderHook(() => usePolling({ fetcher, interval: 3000 }))

    await act(async () => {
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)

    // Hide document
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    })
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    // Advance timers while hidden - should not poll
    await act(async () => {
      vi.advanceTimersByTime(10000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)

    // Make visible again
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    })
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
      await Promise.resolve()
    })

    // Should poll immediately upon becoming visible
    expect(fetcher).toHaveBeenCalledTimes(2)

    // And continue polling at normal interval
    await act(async () => {
      vi.advanceTimersByTime(3000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(3)
  })

  it('backs off to 10s and marks data stale on error while keeping last data visible', async () => {
    let attempt = 0
    const fetcher = vi.fn().mockImplementation(async () => {
      attempt++
      if (attempt === 1) return { status: 'initial' }
      throw new Error('Network error')
    })

    const { result } = renderHook(() => usePolling({ fetcher, interval: 2000 }))

    await act(async () => {
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(result.current.data).toEqual({ status: 'initial' })
    expect(result.current.isStale).toBe(false)

    // At 2s, second poll fails
    await act(async () => {
      vi.advanceTimersByTime(2000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(2)
    // Last data stays visible!
    expect(result.current.data).toEqual({ status: 'initial' })
    expect(result.current.isStale).toBe(true)
    expect(result.current.error).toBeTruthy()

    // At 2s and 5s later, should NOT poll yet because backed off to 10s
    await act(async () => {
      vi.advanceTimersByTime(5000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(2)

    // At 10s mark after error, polls again
    await act(async () => {
      vi.advanceTimersByTime(5000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(3)
  })

  it('clears timers on unmount without leaking', async () => {
    const fetcher = vi.fn().mockResolvedValue({ ok: true })
    const { unmount } = renderHook(() => usePolling({ fetcher, interval: 2000 }))

    await act(async () => {
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)

    unmount()

    await act(async () => {
      vi.advanceTimersByTime(10000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('does not overwrite new fetcher data when old fetcher response resolves late', async () => {
    let resolveP1
    const p1 = new Promise((resolve) => {
      resolveP1 = resolve
    })
    const fetcher1 = vi.fn().mockImplementation(() => p1)

    let resolveP2
    const p2 = new Promise((resolve) => {
      resolveP2 = resolve
    })
    const fetcher2 = vi.fn().mockImplementation(() => p2)

    const { result, rerender } = renderHook(
      ({ fetcher }) => usePolling({ fetcher, interval: 2000 }),
      { initialProps: { fetcher: fetcher1 } }
    )

    expect(fetcher1).toHaveBeenCalledTimes(1)

    rerender({ fetcher: fetcher2 })
    expect(fetcher2).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveP2({ version: 2 })
      await Promise.resolve()
    })
    expect(result.current.data).toEqual({ version: 2 })

    await act(async () => {
      resolveP1({ version: 1 })
      await Promise.resolve()
    })

    expect(result.current.data).toEqual({ version: 2 })
  })

  it('leaves only one timer chain after a fetcher change and overlapping refetch', async () => {
    let resolveP1
    const p1 = new Promise((resolve) => {
      resolveP1 = resolve
    })
    const fetcher1 = vi.fn().mockImplementation(() => p1)

    let resolveP2
    const p2 = new Promise((resolve) => {
      resolveP2 = resolve
    })
    let p2CallCount = 0
    const fetcher2 = vi.fn().mockImplementation(() => {
      p2CallCount++
      if (p2CallCount === 1) return p2
      return Promise.resolve({ ok: true, count: p2CallCount })
    })

    const { result, rerender } = renderHook(
      ({ fetcher }) => usePolling({ fetcher, interval: 2000 }),
      { initialProps: { fetcher: fetcher1 } }
    )

    rerender({ fetcher: fetcher2 })

    act(() => {
      result.current.refetch()
    })

    await act(async () => {
      resolveP1({ ok: false })
      resolveP2({ ok: true, count: 1 })
      await Promise.resolve()
    })

    const callsAfterSettle = fetcher2.mock.calls.length

    await act(async () => {
      vi.advanceTimersByTime(2000)
      await Promise.resolve()
    })
    expect(fetcher2.mock.calls.length).toBe(callsAfterSettle + 1)

    await act(async () => {
      vi.advanceTimersByTime(2000)
      await Promise.resolve()
    })
    expect(fetcher2.mock.calls.length).toBe(callsAfterSettle + 2)
  })

  it('sets no state and schedules no timer when request resolves after unmount', async () => {
    let resolveP
    const p = new Promise((resolve) => {
      resolveP = resolve
    })
    const fetcher = vi.fn().mockImplementation(() => p)

    const { unmount } = renderHook(() => usePolling({ fetcher, interval: 2000 }))
    expect(fetcher).toHaveBeenCalledTimes(1)

    unmount()

    await act(async () => {
      resolveP({ ok: true })
      await Promise.resolve()
    })

    await act(async () => {
      vi.advanceTimersByTime(10000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('discards request resolving after enabled becomes false', async () => {
    let resolveP
    const p = new Promise((resolve) => {
      resolveP = resolve
    })
    const fetcher = vi.fn().mockImplementation(() => p)

    const { result, rerender } = renderHook(
      ({ enabled }) => usePolling({ fetcher, interval: 2000, enabled }),
      { initialProps: { enabled: true } }
    )
    expect(fetcher).toHaveBeenCalledTimes(1)

    rerender({ enabled: false })

    await act(async () => {
      resolveP({ data: 'stale-data' })
      await Promise.resolve()
    })

    expect(result.current.data).toBeNull()

    await act(async () => {
      vi.advanceTimersByTime(10000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('does not update data and schedules no timer when response resolves after tab hides', async () => {
    let resolveP
    const p = new Promise((resolve) => {
      resolveP = resolve
    })
    const fetcher = vi.fn().mockImplementation(() => p)

    const { result } = renderHook(() => usePolling({ fetcher, interval: 2000 }))
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(result.current.data).toBeNull()

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    })
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    await act(async () => {
      resolveP({ data: 'hidden-data' })
      await Promise.resolve()
    })

    expect(result.current.data).toBeNull()

    await act(async () => {
      vi.advanceTimersByTime(10000)
      await Promise.resolve()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('does not set error or stale or switch to backoff when stale rejected response resolves after fetcher change', async () => {
    let rejectP1
    const p1 = new Promise((_, reject) => {
      rejectP1 = reject
    })
    const fetcher1 = vi.fn().mockImplementation(() => p1)

    let resolveP2
    const p2 = new Promise((resolve) => {
      resolveP2 = resolve
    })
    const fetcher2 = vi.fn().mockImplementation(() => p2)

    const { result, rerender } = renderHook(
      ({ fetcher }) => usePolling({ fetcher, interval: 2000 }),
      { initialProps: { fetcher: fetcher1 } }
    )
    expect(fetcher1).toHaveBeenCalledTimes(1)

    rerender({ fetcher: fetcher2 })
    expect(fetcher2).toHaveBeenCalledTimes(1)

    await act(async () => {
      rejectP1(new Error('stale error'))
      await Promise.resolve()
    })

    expect(result.current.error).toBeNull()
    expect(result.current.isStale).toBe(false)

    await act(async () => {
      resolveP2({ ok: true })
      await Promise.resolve()
    })
    expect(result.current.data).toEqual({ ok: true })
    expect(result.current.error).toBeNull()
    expect(result.current.isStale).toBe(false)

    await act(async () => {
      vi.advanceTimersByTime(2000)
      await Promise.resolve()
    })
    expect(fetcher2).toHaveBeenCalledTimes(2)
  })

  it('runs a fresh request on show and sets isLoading false when initial request was discarded by hide', async () => {
    let resolveP1
    const p1 = new Promise((resolve) => {
      resolveP1 = resolve
    })
    let call = 0
    let resolveP2
    const p2 = new Promise((resolve) => {
      resolveP2 = resolve
    })
    const fetcher = vi.fn().mockImplementation(() => {
      call++
      if (call === 1) return p1
      return p2
    })

    const { result } = renderHook(() => usePolling({ fetcher, interval: 2000 }))
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(result.current.isLoading).toBe(true)

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    })
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })

    await act(async () => {
      resolveP1({ initial: false })
      await Promise.resolve()
    })
    expect(result.current.data).toBeNull()
    expect(result.current.isLoading).toBe(true)

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    })
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'))
      await Promise.resolve()
    })

    expect(fetcher).toHaveBeenCalledTimes(2)

    await act(async () => {
      resolveP2({ resumed: true })
      await Promise.resolve()
    })

    expect(result.current.data).toEqual({ resumed: true })
    expect(result.current.isLoading).toBe(false)
  })

  it('applies only the last response and ends with isLoading false after repeated rapid refetch calls', async () => {
    const resolvers = []
    let call = 0
    const fetcher = vi.fn().mockImplementation(() => {
      call++
      const currentCall = call
      return new Promise((resolve) => {
        resolvers.push({ call: currentCall, resolve })
      })
    })

    const { result } = renderHook(() => usePolling({ fetcher, interval: 2000 }))
    expect(fetcher).toHaveBeenCalledTimes(1)

    act(() => {
      result.current.refetch()
    })
    act(() => {
      result.current.refetch()
    })
    expect(fetcher).toHaveBeenCalledTimes(3)
    expect(result.current.isLoading).toBe(true)

    await act(async () => {
      resolvers[0].resolve({ call: 1 })
      resolvers[1].resolve({ call: 2 })
      await Promise.resolve()
    })
    expect(result.current.data).toBeNull()

    await act(async () => {
      resolvers[2].resolve({ call: 3 })
      await Promise.resolve()
    })

    expect(result.current.data).toEqual({ call: 3 })
    expect(result.current.isLoading).toBe(false)
  })
})
