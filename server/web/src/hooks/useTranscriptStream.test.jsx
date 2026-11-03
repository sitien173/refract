import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import {
  useTranscriptStream,
  processTranscriptEvents,
} from './useTranscriptStream.js'
import * as api from '../api.js'

class MockEventSource {
  static instances = []
  static get activeInstances() {
    return MockEventSource.instances.filter((inst) => !inst.closed)
  }

  constructor(url) {
    this.url = url
    this.closed = false
    this.listeners = {}
    MockEventSource.instances.push(this)
  }

  addEventListener(type, callback) {
    if (!this.listeners[type]) {
      this.listeners[type] = []
    }
    this.listeners[type].push(callback)
  }

  removeEventListener(type, callback) {
    if (this.listeners[type]) {
      this.listeners[type] = this.listeners[type].filter((cb) => cb !== callback)
    }
  }

  emit(type, data) {
    if (this.closed) return
    const event = { data: JSON.stringify(data) }
    if (this.listeners[type]) {
      this.listeners[type].forEach((cb) => cb(event))
    }
    if (type === 'message' && this.onmessage) {
      this.onmessage(event)
    }
  }

  triggerError(err = new Event('error')) {
    if (this.closed) return
    if (this.onerror) {
      this.onerror(err)
    }
    if (this.listeners.error) {
      this.listeners.error.forEach((cb) => cb(err))
    }
  }

  close() {
    this.closed = true
  }
}

describe('useTranscriptStream & EventSource lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    vi.spyOn(api, 'fetchJobOutput').mockResolvedValue({
      events: [],
      cursor: 0,
      has_more: false,
      retained_from: 0,
      stream_status: 'complete',
    })
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('maintains at most one EventSource for active non-terminal job and closes on unmount', async () => {
    const { unmount } = renderHook(() =>
      useTranscriptStream({ jobId: 'job-1', jobState: 'running' })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(1)
    expect(MockEventSource.activeInstances[0].url).toContain('/jobs/job-1/output/updates')

    unmount()

    expect(MockEventSource.activeInstances.length).toBe(0)
  })

  it('does not open EventSource for terminal jobs', async () => {
    renderHook(() =>
      useTranscriptStream({ jobId: 'job-term', jobState: 'succeeded' })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(0)
  })

  it('switches EventSource cleanly when jobId changes without exceeding one instance', async () => {
    let currentJob = 'job-1'
    const { rerender } = renderHook(() =>
      useTranscriptStream({ jobId: currentJob, jobState: 'running' })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(1)
    const firstInstance = MockEventSource.activeInstances[0]
    expect(firstInstance.url).toContain('/jobs/job-1/')

    // Switch job
    currentJob = 'job-2'
    rerender()

    await act(async () => {
      await Promise.resolve()
    })

    expect(firstInstance.closed).toBe(true)
    expect(MockEventSource.activeInstances.length).toBe(1)
    expect(MockEventSource.activeInstances[0].url).toContain('/jobs/job-2/')
  })

  it('pages output until has_more is false', async () => {
    api.fetchJobOutput
      .mockResolvedValueOnce({
        events: [{ id: 1, kind: 'lifecycle.start', entity_id: 'e1', data: {} }],
        cursor: 1,
        has_more: true,
        retained_from: 1,
        stream_status: 'active',
      })
      .mockResolvedValueOnce({
        events: [{ id: 2, kind: 'assistant.text_delta', entity_id: 'a1', data: { text: 'hello' } }],
        cursor: 2,
        has_more: false,
        retained_from: 1,
        stream_status: 'active',
      })

    const { result } = renderHook(() =>
      useTranscriptStream({ jobId: 'job-1', jobState: 'running' })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.fetchJobOutput).toHaveBeenCalledTimes(2)
    expect(api.fetchJobOutput).toHaveBeenNthCalledWith(1, 'job-1', { after: 0, limit: 100 })
    expect(api.fetchJobOutput).toHaveBeenNthCalledWith(2, 'job-1', { after: 1, limit: 100 })
    expect(result.current.events.length).toBe(2)
    expect(result.current.cursor).toBe(2)
  })

  it('reconnects after SSE errors with exponential backoff', async () => {
    renderHook(() =>
      useTranscriptStream({ jobId: 'job-1', jobState: 'running' })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(1)
    const instance = MockEventSource.activeInstances[0]

    // Trigger error on SSE
    act(() => {
      instance.triggerError()
    })

    // Closed immediately
    expect(instance.closed).toBe(true)
    expect(MockEventSource.activeInstances.length).toBe(0)

    // Advance 1s (first backoff)
    await act(async () => {
      vi.advanceTimersByTime(1000)
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(1)
  })

  it('closes EventSource once job becomes terminal and remaining events are drained', async () => {
    let state = 'running'
    const { rerender } = renderHook(() =>
      useTranscriptStream({ jobId: 'job-1', jobState: state })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(1)

    // State becomes terminal
    state = 'succeeded'
    rerender()

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(0)
  })

  it('queues pending drain if update arrives during active drain so no updates are dropped', async () => {
    let resolveFirst
    const firstPromise = new Promise((res) => {
      resolveFirst = res
    })

    api.fetchJobOutput.mockImplementationOnce(() => firstPromise)

    const { result } = renderHook(() =>
      useTranscriptStream({ jobId: 'job-1', jobState: 'running' })
    )

    // Initial page load is in flight
    resolveFirst({
      events: [{ id: 1, kind: 'lifecycle.start', entity_id: 'e1', data: {} }],
      cursor: 1,
      has_more: false,
      retained_from: 1,
      stream_status: 'active',
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(1)
    const es = MockEventSource.activeInstances[0]

    // Now start a second drain that stays pending
    let resolveSecond
    const secondPromise = new Promise((res) => {
      resolveSecond = res
    })
    api.fetchJobOutput.mockImplementationOnce(() => secondPromise)

    act(() => {
      es.emit('output-updated', { cursor: 2 })
    })

    // While second is in flight, trigger another update
    act(() => {
      es.emit('output-updated', { cursor: 3 })
    })

    // Now resolve second
    resolveSecond({
      events: [{ id: 2, kind: 'assistant.text_delta', entity_id: 'a1', data: { text: 'chunk 1' } }],
      cursor: 2,
      has_more: false,
      retained_from: 1,
      stream_status: 'active',
    })

    api.fetchJobOutput.mockResolvedValueOnce({
      events: [{ id: 3, kind: 'assistant.text_delta', entity_id: 'a1', data: { text: 'chunk 2' } }],
      cursor: 3,
      has_more: false,
      retained_from: 1,
      stream_status: 'active',
    })

    await act(async () => {
      await Promise.resolve()
    })

    // Queued drain should run for cursor 2
    expect(api.fetchJobOutput).toHaveBeenCalledWith('job-1', { after: 2, limit: 100 })
    expect(result.current.cursor).toBe(3)
  })

  it('drains immediately from last cursor after reconnect without waiting for SSE event', async () => {
    api.fetchJobOutput.mockResolvedValueOnce({
      events: [{ id: 1, kind: 'lifecycle.start', entity_id: 'e1', data: {} }],
      cursor: 1,
      has_more: false,
      retained_from: 1,
      stream_status: 'active',
    })

    renderHook(() =>
      useTranscriptStream({ jobId: 'job-1', jobState: 'running' })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(1)
    const instance = MockEventSource.activeInstances[0]

    // Trigger disconnect
    act(() => {
      instance.triggerError()
    })
    expect(MockEventSource.activeInstances.length).toBe(0)

    // Prepare response for post-reconnect drain
    api.fetchJobOutput.mockResolvedValueOnce({
      events: [{ id: 2, kind: 'assistant.text_delta', entity_id: 'a1', data: { text: 'missed while disconnected' } }],
      cursor: 2,
      has_more: false,
      retained_from: 1,
      stream_status: 'active',
    })

    // Advance timer to trigger reconnect
    await act(async () => {
      vi.advanceTimersByTime(1000)
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(1)
    // Should have called fetchJobOutput immediately after reconnect with after: 1
    expect(api.fetchJobOutput).toHaveBeenCalledWith('job-1', { after: 1, limit: 100 })
  })

  it('runs terminal drain even if earlier drain was active and closes only when drained', async () => {
    let resolveActive
    const activePromise = new Promise((res) => {
      resolveActive = res
    })

    api.fetchJobOutput
      .mockResolvedValueOnce({
        events: [{ id: 1, kind: 'lifecycle.start', entity_id: 'e1', data: {} }],
        cursor: 1,
        has_more: false,
        retained_from: 1,
        stream_status: 'active',
      })
      .mockImplementationOnce(() => activePromise)
      .mockResolvedValueOnce({
        events: [{ id: 3, kind: 'job.completed', entity_id: 'c1', data: {} }],
        cursor: 3,
        has_more: false,
        retained_from: 1,
        stream_status: 'complete',
      })

    let state = 'running'
    const { rerender } = renderHook(() =>
      useTranscriptStream({ jobId: 'job-1', jobState: state })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(1)
    const es = MockEventSource.activeInstances[0]

    // Trigger an update that starts active drain
    act(() => {
      es.emit('output-updated', { cursor: 2 })
    })

    // Now state changes to terminal while drain is in flight
    state = 'succeeded'
    rerender()

    // EventSource should NOT be closed yet because drain is still running
    expect(MockEventSource.activeInstances.length).toBe(1)

    // Resolve the active drain
    resolveActive({
      events: [{ id: 2, kind: 'assistant.text_delta', entity_id: 'a1', data: { text: 'mid' } }],
      cursor: 2,
      has_more: false,
      retained_from: 1,
      stream_status: 'active',
    })

    await act(async () => {
      await Promise.resolve()
    })

    // Now final terminal drain has executed and stream is closed
    expect(api.fetchJobOutput).toHaveBeenCalledWith('job-1', { after: 2, limit: 100 })
    expect(MockEventSource.activeInstances.length).toBe(0)
  })

  it('fetches and renders new job initial page when switching jobs while previous job request is in flight', async () => {
    let resolveJob1
    const job1Promise = new Promise((resolve) => {
      resolveJob1 = resolve
    })

    api.fetchJobOutput.mockImplementation((jobId, params) => {
      if (jobId === 'job-1') {
        return job1Promise
      }
      if (jobId === 'job-2') {
        return Promise.resolve({
          events: [{ id: 201, kind: 'assistant.text_delta', entity_id: 'a2', data: { text: 'job 2 text' } }],
          cursor: 201,
          has_more: false,
          retained_from: 1,
          stream_status: 'active',
        })
      }
      return Promise.resolve({ events: [], cursor: 0, has_more: false, retained_from: 0, stream_status: 'complete' })
    })

    let currentJob = 'job-1'
    const { rerender, result } = renderHook(() =>
      useTranscriptStream({ jobId: currentJob, jobState: 'running' })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.fetchJobOutput).toHaveBeenCalledWith('job-1', { after: 0, limit: 100 })

    currentJob = 'job-2'
    rerender()

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.fetchJobOutput).toHaveBeenCalledWith('job-2', { after: 0, limit: 100 })
    expect(result.current.events).toEqual([
      expect.objectContaining({ id: 201 }),
    ])

    resolveJob1({
      events: [{ id: 101, kind: 'assistant.text_delta', entity_id: 'a1', data: { text: 'job 1 stale' } }],
      cursor: 101,
      has_more: false,
      retained_from: 1,
      stream_status: 'complete',
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(result.current.events.some((e) => e.id === 101)).toBe(false)
  })

  it('detects non-advancing cursor when has_more is true, terminates loop, and sets error', async () => {
    api.fetchJobOutput.mockResolvedValue({
      events: [{ id: 1, kind: 'assistant.text_delta', entity_id: 'a1', data: { text: 'stuck' } }],
      cursor: 0,
      has_more: true,
      retained_from: 0,
      stream_status: 'active',
    })

    const { result } = renderHook(() =>
      useTranscriptStream({ jobId: 'job-stuck', jobState: 'running' })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.fetchJobOutput).toHaveBeenCalledTimes(1)
    expect(result.current.error).toBeTruthy()
    expect(result.current.error.message).toMatch(/cursor did not advance/i)
  })

  it('ensures coalesced reconnect and terminal callers resolve only after follow-up drain finishes', async () => {
    let resolveActive
    const activePromise = new Promise((res) => {
      resolveActive = res
    })
    let resolveFollowUp
    const followUpPromise = new Promise((res) => {
      resolveFollowUp = res
    })

    api.fetchJobOutput
      .mockResolvedValueOnce({
        events: [{ id: 1, kind: 'lifecycle.start', entity_id: 'e1', data: {} }],
        cursor: 1,
        has_more: false,
        retained_from: 1,
        stream_status: 'active',
      })
      .mockImplementationOnce(() => activePromise)
      .mockImplementationOnce(() => followUpPromise)

    let jobState = 'running'
    const { rerender } = renderHook(() =>
      useTranscriptStream({ jobId: 'job-1', jobState })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(1)
    const es = MockEventSource.activeInstances[0]

    // Trigger update starting active drain
    act(() => {
      es.emit('output-updated', { cursor: 2 })
    })

    // While active drain is pending, transition to terminal
    jobState = 'succeeded'
    rerender()

    // Terminal effect should NOT have closed EventSource yet
    expect(MockEventSource.activeInstances.length).toBe(1)

    // Resolve active drain
    resolveActive({
      events: [{ id: 2, kind: 'assistant.text_delta', entity_id: 'a1', data: { text: 'active' } }],
      cursor: 2,
      has_more: false,
      retained_from: 1,
      stream_status: 'active',
    })

    await act(async () => {
      await Promise.resolve()
    })

    // Follow-up drain is now in flight; EventSource must STILL not be closed
    expect(api.fetchJobOutput).toHaveBeenCalledWith('job-1', { after: 2, limit: 100 })
    expect(MockEventSource.activeInstances.length).toBe(1)

    // Now resolve follow-up drain
    resolveFollowUp({
      events: [{ id: 3, kind: 'job.completed', entity_id: 'c1', data: {} }],
      cursor: 3,
      has_more: false,
      retained_from: 1,
      stream_status: 'complete',
    })

    await act(async () => {
      await Promise.resolve()
    })

    // Only after follow-up finishes should terminal close run
    expect(MockEventSource.activeInstances.length).toBe(0)
  })

  it('does not trigger concurrent fetches or overwrite activeDrain when stale pending drain resolves after switching A to B to A', async () => {
    let resolveStaleA
    const stalePromiseA = new Promise((res) => {
      resolveStaleA = res
    })

    let resolveNewA
    const newPromiseA = new Promise((res) => {
      resolveNewA = res
    })

    let fetchCountA = 0
    let switchedBackToA = false
    let inFlightAfterSwitchA = 0
    let maxConcurrentAfterSwitchA = 0

    api.fetchJobOutput.mockImplementation((jobId, params) => {
      if (jobId === 'job-A') {
        fetchCountA += 1

        if (switchedBackToA) {
          inFlightAfterSwitchA += 1
          maxConcurrentAfterSwitchA = Math.max(maxConcurrentAfterSwitchA, inFlightAfterSwitchA)
        }

        if (fetchCountA === 1) {
          return stalePromiseA
        }

        return newPromiseA.finally(() => {
          if (switchedBackToA) {
            inFlightAfterSwitchA -= 1
          }
        })
      }

      if (jobId === 'job-B') {
        return Promise.resolve({
          events: [{ id: 301, kind: 'assistant.text_delta', entity_id: 'b-1', data: { text: 'job-B content' } }],
          cursor: 301,
          has_more: false,
          retained_from: 1,
          stream_status: 'active',
        })
      }

      return Promise.resolve({ events: [], cursor: 0, has_more: false, retained_from: 0, stream_status: 'complete' })
    })

    let currentJob = 'job-A'
    const { rerender, result } = renderHook(() =>
      useTranscriptStream({ jobId: currentJob, jobState: 'running' })
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.activeInstances.length).toBe(1)
    const esA1 = MockEventSource.activeInstances[0]

    // Trigger an update so a drain is coalesced as pending
    act(() => {
      esA1.emit('output-updated', { cursor: 2 })
    })

    // Switch to B
    currentJob = 'job-B'
    rerender()

    await act(async () => {
      await Promise.resolve()
    })

    // Switch back to A
    switchedBackToA = true
    currentJob = 'job-A'
    rerender()

    await act(async () => {
      await Promise.resolve()
    })

    // Now resolve the old request
    resolveStaleA({
      events: [{ id: 101, kind: 'lifecycle.start', entity_id: 'a-old', data: {} }],
      cursor: 101,
      has_more: false,
      retained_from: 1,
      stream_status: 'active',
    })

    await act(async () => {
      await Promise.resolve()
    })

    // Resolve new A request
    resolveNewA({
      events: [{ id: 501, kind: 'assistant.text_delta', entity_id: 'a-new', data: { text: 'new job-A content' } }],
      cursor: 501,
      has_more: false,
      retained_from: 1,
      stream_status: 'active',
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(maxConcurrentAfterSwitchA).toBe(1)
    expect(fetchCountA).toBe(2)
    expect(result.current.events).toEqual([
      expect.objectContaining({ id: 501 }),
    ])
    expect(result.current.events.some((e) => e.id === 101)).toBe(false)
  })
})

describe('processTranscriptEvents', () => {
  it('merges contiguous assistant.text_delta events by entity_id', () => {
    const rawEvents = [
      { id: 1, kind: 'assistant.text_delta', entity_id: 'ent-1', data: { text: 'Hello ' } },
      { id: 2, kind: 'assistant.text_delta', entity_id: 'ent-1', data: { text: 'world!' } },
      { id: 3, kind: 'assistant.text_delta', entity_id: 'ent-2', data: { text: ' Different' } },
      { id: 4, kind: 'assistant.text_delta', entity_id: 'ent-1', data: { text: ' Again' } },
    ]

    const processed = processTranscriptEvents(rawEvents)
    expect(processed.length).toBe(3)
    expect(processed[0]).toMatchObject({
      kind: 'assistant.text',
      entity_id: 'ent-1',
      text: 'Hello world!',
    })
    expect(processed[1]).toMatchObject({
      kind: 'assistant.text',
      entity_id: 'ent-2',
      text: ' Different',
    })
    expect(processed[2]).toMatchObject({
      kind: 'assistant.text',
      entity_id: 'ent-1',
      text: ' Again',
    })
  })

  it('pairs tool.started and tool.completed by entity_id', () => {
    const rawEvents = [
      {
        id: 1,
        kind: 'tool.started',
        entity_id: 'tool-call-1',
        data: { name: 'search', input: { q: 'refract' } },
      },
      {
        id: 2,
        kind: 'assistant.text_delta',
        entity_id: 'msg-1',
        data: { text: 'Searching...' },
      },
      {
        id: 3,
        kind: 'tool.completed',
        entity_id: 'tool-call-1',
        data: { output: 'found 3 matches' },
      },
    ]

    const processed = processTranscriptEvents(rawEvents)
    expect(processed.length).toBe(2)
    const toolItem = processed.find((item) => item.kind === 'tool.call')
    expect(toolItem).toBeDefined()
    expect(toolItem.entity_id).toBe('tool-call-1')
    expect(toolItem.name).toBe('search')
    expect(toolItem.input).toEqual({ q: 'refract' })
    expect(toolItem.output).toBe('found 3 matches')
    expect(toolItem.status).toBe('completed')
  })

  it('pairs tool.started and tool.completed using data.tool and preserves failed status', () => {
    const rawEvents = [
      {
        id: 1,
        kind: 'tool.started',
        entity_id: 'tool-call-1',
        data: { tool: 'search_files', input: { q: 'refract' } },
      },
      {
        id: 2,
        kind: 'tool.completed',
        entity_id: 'tool-call-1',
        data: { status: 'failed', error: 'permission denied' },
      },
    ]

    const processed = processTranscriptEvents(rawEvents)
    expect(processed.length).toBe(1)
    expect(processed[0]).toMatchObject({
      kind: 'tool.call',
      entity_id: 'tool-call-1',
      name: 'search_files',
      status: 'failed',
      error: 'permission denied',
    })
  })

  it('preserves lifecycle markers and special stream markers', () => {
    const rawEvents = [
      { id: 1, kind: 'job.started', entity_id: 'j1', data: { timestamp: '2026-11-03' } },
      { id: 2, kind: 'stream.truncated', entity_id: 'st1', data: { reason: 'bytes limit' } },
      { id: 3, kind: 'stream.persistence_failed', entity_id: 'sp1', data: { error: 'disk full' } },
    ]

    const processed = processTranscriptEvents(rawEvents)
    expect(processed.length).toBe(3)
    expect(processed[0].kind).toBe('job.started')
    expect(processed[1].kind).toBe('stream.truncated')
    expect(processed[2].kind).toBe('stream.persistence_failed')
  })
})
