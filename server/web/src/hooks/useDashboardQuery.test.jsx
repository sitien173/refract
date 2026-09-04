import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useDashboardQuery } from './useDashboardQuery'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('useDashboardQuery', () => {
  it('supersedes an in-flight query when dependencies change', async () => {
    const first = deferred()
    const second = deferred()
    const query = vi.fn((route) => route === 'first' ? first.promise : second.promise)
    const { result, rerender } = renderHook(
      ({ route }) => useDashboardQuery(() => query(route), { deps: [route] }),
      { initialProps: { route: 'first' } },
    )

    rerender({ route: 'second' })
    second.resolve('second-result')
    await waitFor(() => expect(result.current.data).toBe('second-result'))

    first.resolve('first-result')
    await act(async () => { await first.promise })
    expect(result.current.data).toBe('second-result')
    expect(query).toHaveBeenCalledTimes(2)
  })

  it('keeps polling results ordered and does not overlap requests', async () => {
    vi.useFakeTimers()
    try {
      const first = deferred()
      const second = deferred()
      const query = vi.fn()
        .mockReturnValueOnce(first.promise)
        .mockReturnValueOnce(second.promise)
      const { result } = renderHook(() => useDashboardQuery(query, { pollInterval: 10 }))

      expect(query).toHaveBeenCalledTimes(1)
      await act(async () => { first.resolve('first-result'); await first.promise })
      await act(async () => { vi.advanceTimersByTime(10) })
      expect(query).toHaveBeenCalledTimes(2)
      expect(result.current.data).toBe('first-result')

      second.resolve('second-result')
      await act(async () => { await second.promise })
      expect(result.current.data).toBe('second-result')
    } finally {
      vi.useRealTimers()
    }
  })
})
