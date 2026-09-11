import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import { useJobStream } from './useJobStream'

class MockEventSource {
  static instances = []

  constructor(url) {
    this.url = url
    this.readyState = 0 // CONNECTING
    this.listeners = {}
    MockEventSource.instances.push(this)
    setTimeout(() => {
      this.readyState = 1 // OPEN
      if (this.onopen) this.onopen(new Event('open'))
    }, 0)
  }

  addEventListener(type, callback) {
    this.listeners[type] = this.listeners[type] || []
    this.listeners[type].push(callback)
  }

  removeEventListener(type, callback) {
    if (this.listeners[type]) {
      this.listeners[type] = this.listeners[type].filter((cb) => cb !== callback)
    }
  }

  dispatchEvent(event) {
    const list = this.listeners[event.type] || []
    list.forEach((cb) => cb(event))
    if (event.type === 'message' && this.onmessage) this.onmessage(event)
    if (event.type === 'error' && this.onerror) this.onerror(event)
  }

  close() {
    this.readyState = 2 // CLOSED
  }
}

describe('useJobStream hook', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    window.EventSource = MockEventSource
    vi.restoreAllMocks()
  })

  afterEach(() => {
    delete window.EventSource
  })

  it('fetches initial durable replay page and sets status to live', async () => {
    vi.spyOn(api, 'getJobOutput').mockResolvedValueOnce({
      events: [
        { id: 1, kind: 'assistant.text_delta', data: { text: 'Hello' } },
        { id: 2, kind: 'assistant.text_delta', data: { text: ' world' } },
      ],
      cursor: 2,
      has_more: false,
      retained_from: 1,
      stream_status: 'active',
    })

    const { result } = renderHook(() => useJobStream('job-1'))

    await waitFor(() => expect(result.current.events.length).toBe(2))
    expect(result.current.cursor).toBe(2)
    expect(result.current.retainedFrom).toBe(1)
    expect(result.current.streamStatus).toBe('active')
    expect(result.current.status).toBe('live')
    expect(api.getJobOutput).toHaveBeenCalledWith('job-1', { after: 0, limit: 100 }, expect.any(Object))
  })

  it('drains multiple pages sequentially when has_more is true', async () => {
    vi.spyOn(api, 'getJobOutput')
      .mockResolvedValueOnce({
        events: [{ id: 1, kind: 'assistant.text_delta', data: { text: 'chunk 1' } }],
        cursor: 1,
        has_more: true,
        retained_from: 1,
        stream_status: 'active',
      })
      .mockResolvedValueOnce({
        events: [{ id: 2, kind: 'assistant.text_delta', data: { text: 'chunk 2' } }],
        cursor: 2,
        has_more: false,
        retained_from: 1,
        stream_status: 'active',
      })

    const { result } = renderHook(() => useJobStream('job-paged'))

    await waitFor(() => expect(result.current.events.length).toBe(2))
    expect(result.current.cursor).toBe(2)
    expect(api.getJobOutput).toHaveBeenNthCalledWith(1, 'job-paged', { after: 0, limit: 100 }, expect.any(Object))
    expect(api.getJobOutput).toHaveBeenNthCalledWith(2, 'job-paged', { after: 1, limit: 100 }, expect.any(Object))
  })

  it('receives SSE invalidation notification and fetches next delta page', async () => {
    vi.spyOn(api, 'getJobOutput')
      .mockResolvedValueOnce({
        events: [{ id: 10, kind: 'assistant.text_delta', data: { text: 'initial' } }],
        cursor: 10,
        has_more: false,
        retained_from: 10,
        stream_status: 'active',
      })
      .mockResolvedValueOnce({
        events: [{ id: 11, kind: 'assistant.text_delta', data: { text: ' new' } }],
        cursor: 11,
        has_more: false,
        retained_from: 10,
        stream_status: 'active',
      })

    const { result } = renderHook(() => useJobStream('job-sse'))

    await waitFor(() => expect(result.current.cursor).toBe(10))

    const es = MockEventSource.instances[0]
    expect(es).toBeDefined()

    // Dispatch SSE output-updated event with cursor 11
    act(() => {
      const event = new MessageEvent('output-updated', {
        data: JSON.stringify({ cursor: 11 }),
      })
      es.dispatchEvent(event)
    })

    await waitFor(() => expect(result.current.cursor).toBe(11))
    expect(result.current.events.length).toBe(2)
    expect(api.getJobOutput).toHaveBeenCalledTimes(2)
    expect(api.getJobOutput).toHaveBeenLastCalledWith('job-sse', { after: 10, limit: 100 }, expect.any(Object))
  })

  it('ignores duplicate or stale notifications where notified cursor <= applied cursor', async () => {
    vi.spyOn(api, 'getJobOutput').mockResolvedValueOnce({
      events: [{ id: 5, kind: 'assistant.text_delta', data: { text: 'five' } }],
      cursor: 5,
      has_more: false,
      retained_from: 5,
      stream_status: 'active',
    })

    const { result } = renderHook(() => useJobStream('job-dedupe'))
    await waitFor(() => expect(result.current.cursor).toBe(5))

    const es = MockEventSource.instances[0]
    act(() => {
      es.dispatchEvent(new MessageEvent('output-updated', { data: JSON.stringify({ cursor: 5 }) }))
      es.dispatchEvent(new MessageEvent('output-updated', { data: JSON.stringify({ cursor: 4 }) }))
    })

    expect(api.getJobOutput).toHaveBeenCalledTimes(1)
  })

  it('transitions to reconnecting state on EventSource error and polls fallback', async () => {
    vi.useFakeTimers()
    try {
      vi.spyOn(api, 'getJobOutput')
        .mockResolvedValueOnce({
          events: [{ id: 1, kind: 'assistant.text_delta', data: { text: '1' } }],
          cursor: 1,
          has_more: false,
          retained_from: 1,
          stream_status: 'active',
        })
        .mockResolvedValueOnce({
          events: [{ id: 2, kind: 'assistant.text_delta', data: { text: '2' } }],
          cursor: 2,
          has_more: false,
          retained_from: 1,
          stream_status: 'active',
        })

      const { result } = renderHook(() => useJobStream('job-reconn', { pollIntervalMs: 5000 }))

      await act(async () => {
        await Promise.resolve()
      })
      expect(result.current.cursor).toBe(1)

      const es = MockEventSource.instances[0]
      act(() => {
        es.dispatchEvent(new Event('error'))
      })

      expect(result.current.status).toBe('reconnecting')

      // Fallback polling should trigger after 5000ms while reconnecting
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000)
      })

      expect(api.getJobOutput).toHaveBeenCalledTimes(2)
      expect(result.current.cursor).toBe(2)
    } finally {
      vi.useRealTimers()
    }
  })

  it('closes EventSource and cancels in-flight requests on unmount', async () => {
    let abortSignal
    vi.spyOn(api, 'getJobOutput').mockImplementation((id, opts, signal) => {
      abortSignal = signal
      return new Promise(() => {}) // never resolves
    })

    const { unmount } = renderHook(() => useJobStream('job-unmount'))
    const es = MockEventSource.instances[0]

    expect(es.readyState).not.toBe(2)
    unmount()

    expect(es.readyState).toBe(2) // CLOSED
    expect(abortSignal?.aborted).toBe(true)
  })

  it('cancels pending requests and resets transcript when jobId changes', async () => {
    vi.spyOn(api, 'getJobOutput')
      .mockResolvedValueOnce({
        events: [{ id: 100, kind: 'assistant.text_delta', data: { text: 'jobA' } }],
        cursor: 100,
        has_more: false,
        retained_from: 100,
        stream_status: 'active',
      })
      .mockResolvedValueOnce({
        events: [{ id: 200, kind: 'assistant.text_delta', data: { text: 'jobB' } }],
        cursor: 200,
        has_more: false,
        retained_from: 200,
        stream_status: 'active',
      })

    const { result, rerender } = renderHook(({ id }) => useJobStream(id), {
      initialProps: { id: 'job-A' },
    })

    await waitFor(() => expect(result.current.cursor).toBe(100))
    expect(result.current.events[0].data.text).toBe('jobA')
    const firstES = MockEventSource.instances[0]

    // Change job ID
    rerender({ id: 'job-B' })

    expect(firstES.readyState).toBe(2) // previous ES closed
    await waitFor(() => expect(result.current.cursor).toBe(200))
    expect(result.current.events[0].data.text).toBe('jobB')
  })

  it('preserves existing events if an incremental delta fetch encounters an error', async () => {
    vi.spyOn(api, 'getJobOutput')
      .mockResolvedValueOnce({
        events: [{ id: 1, kind: 'assistant.text_delta', data: { text: 'durable' } }],
        cursor: 1,
        has_more: false,
        retained_from: 1,
        stream_status: 'active',
      })
      .mockRejectedValueOnce(new Error('Network drop'))

    const { result } = renderHook(() => useJobStream('job-err'))

    await waitFor(() => expect(result.current.events.length).toBe(1))

    const es = MockEventSource.instances[0]
    act(() => {
      es.dispatchEvent(new MessageEvent('output-updated', { data: JSON.stringify({ cursor: 2 }) }))
    })

    await waitFor(() => expect(result.current.error).toBeDefined())
    // Events must be preserved
    expect(result.current.events.length).toBe(1)
    expect(result.current.events[0].data.text).toBe('durable')
  })

  it('ensures a pending old fetch does not block new job initial fetch or mutate its transcript', async () => {
    let resolveJobA
    const jobAPromise = new Promise((resolve) => {
      resolveJobA = resolve
    })

    vi.spyOn(api, 'getJobOutput').mockImplementation((id) => {
      if (id === 'job-slow-A') {
        return jobAPromise
      }
      if (id === 'job-quick-B') {
        return Promise.resolve({
          events: [{ id: 10, kind: 'assistant.text.delta', data: { text: 'from job B' } }],
          cursor: 10,
          has_more: false,
          retained_from: 10,
          stream_status: 'active',
        })
      }
      return Promise.resolve({ events: [], cursor: 0, has_more: false })
    })

    const { result, rerender } = renderHook(({ id }) => useJobStream(id), {
      initialProps: { id: 'job-slow-A' },
    })

    expect(result.current.events).toEqual([])

    // Switch to job-quick-B while job-slow-A fetch is still in flight
    rerender({ id: 'job-quick-B' })

    // job-quick-B initial fetch must succeed and not be blocked
    await waitFor(() => expect(result.current.cursor).toBe(10))
    expect(result.current.events).toHaveLength(1)
    expect(result.current.events[0].data.text).toBe('from job B')

    // Now resolve job-slow-A late
    resolveJobA({
      events: [{ id: 999, kind: 'assistant.text.delta', data: { text: 'stale from job A' } }],
      cursor: 999,
      has_more: false,
      retained_from: 999,
      stream_status: 'complete',
    })

    await new Promise((r) => setTimeout(r, 20))

    // Must not have mutated job-quick-B transcript
    expect(result.current.cursor).toBe(10)
    expect(result.current.events).toHaveLength(1)
    expect(result.current.events[0].data.text).toBe('from job B')
  })
})
