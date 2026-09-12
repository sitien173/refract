import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api'
import { reduceTranscriptEvents, useJobStream } from './useJobStream'

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

  it('performs one final output refresh, refreshes cursor and streamStatus, and closes EventSource when transitioning from isTerminal false to true', async () => {
    vi.spyOn(api, 'getJobOutput')
      .mockResolvedValueOnce({
        events: [{ id: 1, kind: 'assistant.text_delta', data: { text: 'live chunk' } }],
        cursor: 1,
        has_more: false,
        retained_from: 1,
        stream_status: 'active',
      })
      .mockResolvedValueOnce({
        events: [{ id: 2, kind: 'attempt.finished', data: { status: 'succeeded' } }],
        cursor: 2,
        has_more: false,
        retained_from: 1,
        stream_status: 'complete',
      })

    const { result, rerender } = renderHook(({ isTerminal }) => useJobStream('job-term-trans', { isTerminal }), {
      initialProps: { isTerminal: false },
    })

    await waitFor(() => expect(result.current.cursor).toBe(1))
    expect(result.current.streamStatus).toBe('active')
    const es = MockEventSource.instances[0]
    expect(es).toBeDefined()
    expect(es.readyState).not.toBe(2)

    // Transition to isTerminal: true
    rerender({ isTerminal: true })

    await waitFor(() => expect(result.current.cursor).toBe(2))
    expect(result.current.streamStatus).toBe('complete')
    expect(result.current.events).toHaveLength(2)
    expect(api.getJobOutput).toHaveBeenCalledTimes(2)
    expect(es.readyState).toBe(2) // Closed
  })

  it('does not add a redundant final fetch for an initially terminal job', async () => {
    vi.spyOn(api, 'getJobOutput').mockResolvedValueOnce({
      events: [{ id: 1, kind: 'assistant.text_delta', data: { text: 'done' } }],
      cursor: 1,
      has_more: false,
      retained_from: 1,
      stream_status: 'complete',
    })

    const { result, rerender } = renderHook(({ isTerminal }) => useJobStream('job-init-term', { isTerminal }), {
      initialProps: { isTerminal: true },
    })

    await waitFor(() => expect(result.current.cursor).toBe(1))
    expect(api.getJobOutput).toHaveBeenCalledTimes(1)

    // Rerender with isTerminal still true
    rerender({ isTerminal: true })
    await new Promise((r) => setTimeout(r, 20))

    expect(api.getJobOutput).toHaveBeenCalledTimes(1)
  })

  it('does not continuously poll terminal jobs', async () => {
    vi.useFakeTimers()
    try {
      vi.spyOn(api, 'getJobOutput').mockResolvedValue({
        events: [{ id: 1, kind: 'assistant.text_delta', data: { text: 'done' } }],
        cursor: 1,
        has_more: false,
        retained_from: 1,
        stream_status: 'complete',
      })

      const { result } = renderHook(() => useJobStream('job-no-poll', { isTerminal: true, pollIntervalMs: 1000 }))

      await act(async () => {
        await Promise.resolve()
      })
      expect(result.current.cursor).toBe(1)
      expect(api.getJobOutput).toHaveBeenCalledTimes(1)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000)
      })

      expect(api.getJobOutput).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('ensures a terminal transition supersedes a concurrent request', async () => {
    let resolveInitial
    const initialPromise = new Promise((resolve) => {
      resolveInitial = resolve
    })

    vi.spyOn(api, 'getJobOutput')
      .mockImplementationOnce(() => initialPromise)
      .mockResolvedValueOnce({
        events: [{ id: 2, kind: 'attempt.finished', data: { status: 'succeeded' } }],
        cursor: 2,
        has_more: false,
        retained_from: 2,
        stream_status: 'complete',
      })

    const { result, rerender } = renderHook(({ isTerminal }) => useJobStream('job-concurrent', { isTerminal }), {
      initialProps: { isTerminal: false },
    })

    // Initial fetch is stalled in flight
    expect(result.current.cursor).toBe(0)

    // Terminal transition happens while initial request is in flight
    rerender({ isTerminal: true })

    // Terminal fetch should supersede and resolve
    await waitFor(() => expect(result.current.cursor).toBe(2))
    expect(result.current.streamStatus).toBe('complete')
    expect(result.current.events).toHaveLength(1)

    // If initial fetch resolves later with stale data, it must not overwrite
    resolveInitial({
      events: [{ id: 1, kind: 'assistant.text_delta', data: { text: 'stale initial' } }],
      cursor: 1,
      has_more: false,
      retained_from: 1,
      stream_status: 'active',
    })

    await new Promise((r) => setTimeout(r, 20))
    expect(result.current.cursor).toBe(2)
    expect(result.current.streamStatus).toBe('complete')
  })
})

describe('reduceTranscriptEvents', () => {
  it('preserves chronological ordering for assistant, tool, assistant sequences', () => {
    const events = [
      { id: 1, kind: 'assistant.message.started', entity_id: 'msg-1' },
      { id: 2, kind: 'assistant.text.delta', entity_id: 'msg-1', data: { text: 'First response' } },
      { id: 3, kind: 'assistant.message.completed', entity_id: 'msg-1' },
      { id: 4, kind: 'tool.started', entity_id: 'tool-1', data: { tool_name: 'read_file', input: { path: 'a.txt' } } },
      { id: 5, kind: 'tool.completed', entity_id: 'tool-1', data: { status: 'completed', output: 'content' } },
      { id: 6, kind: 'assistant.message.started', entity_id: 'msg-2' },
      { id: 7, kind: 'assistant.text.delta', entity_id: 'msg-2', data: { text: 'Second response' } },
      { id: 8, kind: 'assistant.message.completed', entity_id: 'msg-2' },
    ]
    const attempts = reduceTranscriptEvents(events)
    expect(attempts).toHaveLength(1)
    const items = attempts[0].items
    expect(items).toHaveLength(3)
    expect(items[0].type).toBe('assistant_message')
    expect(items[0].text).toBe('First response')
    expect(items[1].type).toBe('tool_call')
    expect(items[1].entity_id).toBe('tool-1')
    expect(items[2].type).toBe('assistant_message')
    expect(items[2].text).toBe('Second response')
  })

  it('handles interleaved tools with distinct identifiers correctly', () => {
    const events = [
      { id: 1, kind: 'tool.started', entity_id: 'tool-A', data: { tool_name: 'toolA', input: { id: 'A' } } },
      { id: 2, kind: 'tool.started', entity_id: 'tool-B', data: { tool_name: 'toolB', input: { id: 'B' } } },
      { id: 3, kind: 'tool.completed', entity_id: 'tool-A', data: { status: 'completed', output: 'result-A' } },
      { id: 4, kind: 'tool.completed', entity_id: 'tool-B', data: { status: 'completed', output: 'result-B' } },
    ]
    const attempts = reduceTranscriptEvents(events)
    const items = attempts[0].items
    expect(items).toHaveLength(2)
    expect(items[0].entity_id).toBe('tool-A')
    expect(items[0].input).toEqual({ id: 'A' })
    expect(items[0].output).toBe('result-A')
    expect(items[0].status).toBe('completed')

    expect(items[1].entity_id).toBe('tool-B')
    expect(items[1].input).toEqual({ id: 'B' })
    expect(items[1].output).toBe('result-B')
    expect(items[1].status).toBe('completed')
  })

  it('preserves raw object input and raw string output', () => {
    const rawInput = { nested: { array: [1, 2, 3], flag: true } }
    const rawOutput = 'Command output:\nLine 1\nLine 2'
    const events = [
      { id: 1, kind: 'tool.started', entity_id: 'tool-1', data: { tool_name: 'exec', input: rawInput } },
      { id: 2, kind: 'tool.completed', entity_id: 'tool-1', data: { status: 'completed', output: rawOutput } },
    ]
    const attempts = reduceTranscriptEvents(events)
    const tool = attempts[0].items[0]
    expect(tool.input).toEqual(rawInput)
    expect(tool.output).toBe(rawOutput)
  })

  it('authoritatively matches completion by entity_id and never attaches to another tool', () => {
    const events = [
      { id: 1, kind: 'tool.started', entity_id: 'tool-X', data: { tool_name: 'toolX', input: 'x' } },
      { id: 2, kind: 'tool.completed', entity_id: 'tool-Y', data: { status: 'completed', output: 'y' } },
    ]
    const attempts = reduceTranscriptEvents(events)
    const items = attempts[0].items
    expect(items).toHaveLength(1)
    expect(items[0].entity_id).toBe('tool-X')
    expect(items[0].status).toBe('running')
    expect(items[0].input).toBe('x')
    expect('output' in items[0]).toBe(false)
  })

  it('distinguishes absent values from present null and falsy values', () => {
    const events = [
      { id: 1, kind: 'tool.started', entity_id: 'tool-absent', data: { tool_name: 't1' } },
      { id: 2, kind: 'tool.completed', entity_id: 'tool-absent', data: { status: 'completed' } },
      { id: 3, kind: 'tool.started', entity_id: 'tool-null', data: { tool_name: 't2', input: null } },
      { id: 4, kind: 'tool.completed', entity_id: 'tool-null', data: { status: 'completed', output: null } },
      { id: 5, kind: 'tool.started', entity_id: 'tool-falsy-1', data: { tool_name: 't3', input: false } },
      { id: 6, kind: 'tool.completed', entity_id: 'tool-falsy-1', data: { status: 'completed', output: 0 } },
      { id: 7, kind: 'tool.started', entity_id: 'tool-falsy-2', data: { tool_name: 't4', input: '' } },
      { id: 8, kind: 'tool.completed', entity_id: 'tool-falsy-2', data: { status: 'completed', output: [] } },
      { id: 9, kind: 'tool.started', entity_id: 'tool-falsy-3', data: { tool_name: 't5', input: {} } },
    ]
    const attempts = reduceTranscriptEvents(events)
    const items = attempts[0].items

    expect('input' in items[0]).toBe(false)
    expect('output' in items[0]).toBe(false)

    expect('input' in items[1]).toBe(true)
    expect(items[1].input).toBeNull()
    expect('output' in items[1]).toBe(true)
    expect(items[1].output).toBeNull()

    expect('input' in items[2]).toBe(true)
    expect(items[2].input).toBe(false)
    expect('output' in items[2]).toBe(true)
    expect(items[2].output).toBe(0)

    expect('input' in items[3]).toBe(true)
    expect(items[3].input).toBe('')
    expect('output' in items[3]).toBe(true)
    expect(items[3].output).toEqual([])

    expect('input' in items[4]).toBe(true)
    expect(items[4].input).toEqual({})
  })

  it('handles failed tool status with available output', () => {
    const events = [
      { id: 1, kind: 'tool.started', entity_id: 'tool-err', data: { tool_name: 'failing_tool', input: { arg: 1 } } },
      { id: 2, kind: 'tool.completed', entity_id: 'tool-err', data: { status: 'failed', output: 'Process exited with code 1: permission denied' } },
    ]
    const attempts = reduceTranscriptEvents(events)
    const item = attempts[0].items[0]
    expect(item.status).toBe('failed')
    expect(item.input).toEqual({ arg: 1 })
    expect(item.output).toBe('Process exited with code 1: permission denied')
  })

  it('handles historical rows without payloads preserving status and identifiers', () => {
    const events = [
      { id: 1, kind: 'tool.started', entity_id: 'tool-hist', data: { tool: 'legacy_tool', call_id: 'call-hist' } },
      { id: 2, kind: 'tool.completed', entity_id: 'tool-hist', data: { status: 'succeeded' } },
    ]
    const attempts = reduceTranscriptEvents(events)
    const item = attempts[0].items[0]
    expect(item.tool_name).toBe('legacy_tool')
    expect(item.status).toBe('succeeded')
    expect(item.call_id).toBe('call-hist')
    expect('input' in item).toBe(false)
    expect('output' in item).toBe(false)
  })

  it('handles legacy event aliases for tools, assistant, and attempts', () => {
    const events = [
      { id: 1, attempt: 1, kind: 'attempt.started', target_id: 'node-1' },
      { id: 2, attempt: 1, kind: 'assistant.message_start', entity_id: 'm-1' },
      { id: 3, attempt: 1, kind: 'assistant.text_delta', entity_id: 'm-1', data: { text: 'Drafting...' } },
      { id: 4, attempt: 1, kind: 'assistant.message_end', entity_id: 'm-1' },
      { id: 5, attempt: 1, kind: 'tool.call_start', entity_id: 't-1', data: { tool_name: 'test_call', input: 'test' } },
      { id: 6, attempt: 1, kind: 'tool.call_end', entity_id: 't-1', data: { outcome: 'success', output: 'done' } },
      { id: 7, attempt: 1, kind: 'attempt.completed', data: { outcome: 'succeeded' } },
    ]
    const attempts = reduceTranscriptEvents(events)
    expect(attempts).toHaveLength(1)
    expect(attempts[0].status).toBe('succeeded')
    const items = attempts[0].items
    expect(items).toHaveLength(2)
    expect(items[0].type).toBe('assistant_message')
    expect(items[0].text).toBe('Drafting...')
    expect(items[0].status).toBe('completed')
    expect(items[1].type).toBe('tool_call')
    expect(items[1].tool_name).toBe('test_call')
    expect(items[1].status).toBe('success')
    expect(items[1].input).toBe('test')
    expect(items[1].output).toBe('done')
  })
})
