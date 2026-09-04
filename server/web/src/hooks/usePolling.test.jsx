import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePolling } from './usePolling'

describe('usePolling hook', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('invokes callback at specified interval when active', async () => {
    const callback = vi.fn().mockResolvedValue(undefined)
    renderHook(() => usePolling(callback, 5000, { enabled: true, isTerminal: false }))

    expect(callback).toHaveBeenCalledTimes(0)
    await vi.advanceTimersByTimeAsync(5000)
    expect(callback).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(5000)
    expect(callback).toHaveBeenCalledTimes(2)
  })

  it('cleans up timer on unmount and prevents further invocations', async () => {
    const callback = vi.fn().mockResolvedValue(undefined)
    const { unmount } = renderHook(() =>
      usePolling(callback, 5000, { enabled: true, isTerminal: false })
    )

    await vi.advanceTimersByTimeAsync(5000)
    expect(callback).toHaveBeenCalledTimes(1)

    unmount()

    await vi.advanceTimersByTimeAsync(20000)
    expect(callback).toHaveBeenCalledTimes(1)
  })

  it('stops polling when isTerminal is true', async () => {
    const callback = vi.fn().mockResolvedValue(undefined)
    renderHook(() => usePolling(callback, 5000, { enabled: true, isTerminal: true }))

    await vi.advanceTimersByTimeAsync(15000)
    expect(callback).toHaveBeenCalledTimes(0)
  })

  it('pauses polling when document is hidden and resumes on visibilitychange', async () => {
    const callback = vi.fn().mockResolvedValue(undefined)
    renderHook(() => usePolling(callback, 5000, { enabled: true, isTerminal: false }))

    // Simulate tab hidden
    Object.defineProperty(document, 'hidden', { value: true, configurable: true })
    await vi.advanceTimersByTimeAsync(5000)
    expect(callback).toHaveBeenCalledTimes(0)

    // Simulate tab visible again
    Object.defineProperty(document, 'hidden', { value: false, configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(0)
    expect(callback).toHaveBeenCalledTimes(1)
  })
})
