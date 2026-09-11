import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import JobTranscript from './JobTranscript'
import { reduceTranscriptEvents } from '../hooks/useJobStream'

describe('reduceTranscriptEvents', () => {
  it('groups events by attempt and merges assistant deltas', () => {
    const events = [
      { id: 1, attempt: 1, target_id: 't1', backend: 'codex', kind: 'attempt.started', created_at: '2026-09-11 10:00:00' },
      { id: 2, attempt: 1, target_id: 't1', backend: 'codex', kind: 'assistant.message_start', entity_id: 'msg-1' },
      { id: 3, attempt: 1, target_id: 't1', backend: 'codex', kind: 'assistant.text_delta', entity_id: 'msg-1', data: { text: 'Hello ' } },
      { id: 4, attempt: 1, target_id: 't1', backend: 'codex', kind: 'assistant.text_delta', entity_id: 'msg-1', data: { text: 'world!' } },
      { id: 5, attempt: 1, target_id: 't1', backend: 'codex', kind: 'assistant.message_end', entity_id: 'msg-1' },
      { id: 6, attempt: 1, target_id: 't1', backend: 'codex', kind: 'attempt.completed', data: { status: 'succeeded' } },
    ]

    const attempts = reduceTranscriptEvents(events)
    expect(attempts).toHaveLength(1)
    expect(attempts[0].attempt).toBe(1)
    expect(attempts[0].target_id).toBe('t1')
    expect(attempts[0].backend).toBe('codex')
    expect(attempts[0].status).toBe('succeeded')

    const items = attempts[0].items
    expect(items).toHaveLength(1)
    expect(items[0].type).toBe('assistant_message')
    expect(items[0].text).toBe('Hello world!')
    expect(items[0].status).toBe('completed')
  })

  it('reduces durable public contract events (attempt.started, attempt.finished, assistant.message.started, assistant.text.delta, assistant.message.completed, tool.started, tool.completed)', () => {
    const events = [
      { id: 1, attempt: 1, target_id: 't-worker', backend: 'claude', kind: 'attempt.started', created_at: '2026-09-11 10:00:00' },
      { id: 2, attempt: 1, target_id: 't-worker', backend: 'claude', kind: 'assistant.message.started', entity_id: 'msg-1' },
      { id: 3, attempt: 1, target_id: 't-worker', backend: 'claude', kind: 'assistant.text.delta', entity_id: 'msg-1', data: { text: 'Running ' } },
      { id: 4, attempt: 1, target_id: 't-worker', backend: 'claude', kind: 'assistant.text.delta', entity_id: 'msg-1', data: { text: 'inspection.' } },
      { id: 5, attempt: 1, target_id: 't-worker', backend: 'claude', kind: 'assistant.message.completed', entity_id: 'msg-1' },
      { id: 6, attempt: 1, target_id: 't-worker', backend: 'claude', kind: 'tool.started', entity_id: 'tool-1', data: { tool: 'find_files', call_id: 'c-1', arguments: { query: 'SECRET' } } },
      { id: 7, attempt: 1, target_id: 't-worker', backend: 'claude', kind: 'tool.completed', entity_id: 'tool-1', data: { status: 'completed', result: { secret: 'LEAK' } } },
      { id: 8, attempt: 1, target_id: 't-worker', backend: 'claude', kind: 'attempt.finished', data: { status: 'succeeded' } },
    ]

    const attempts = reduceTranscriptEvents(events)
    expect(attempts).toHaveLength(1)
    expect(attempts[0].attempt).toBe(1)
    expect(attempts[0].target_id).toBe('t-worker')
    expect(attempts[0].backend).toBe('claude')
    expect(attempts[0].status).toBe('succeeded')

    const items = attempts[0].items
    expect(items).toHaveLength(2)

    // Assistant message
    expect(items[0].type).toBe('assistant_message')
    expect(items[0].text).toBe('Running inspection.')
    expect(items[0].status).toBe('completed')

    // Safe tool call
    expect(items[1].type).toBe('tool_call')
    expect(items[1].tool_name).toBe('find_files')
    expect(items[1].status).toBe('completed')
    expect(items[1].call_id).toBe('c-1')
    expect(items[1].arguments).toBeUndefined()
    expect(items[1].result).toBeUndefined()
  })

  it('reduces safe tool status cards without leaking arguments or results', () => {
    const events = [
      { id: 1, attempt: 1, target_id: 't1', backend: 'claude', kind: 'attempt.started' },
      {
        id: 2,
        attempt: 1,
        target_id: 't1',
        backend: 'claude',
        kind: 'tool.call_start',
        entity_id: 'tool-call-1',
        data: {
          tool_name: 'read_file',
          call_id: 'call-1',
          // Maliciously placed extra fields that should never be copied
          arguments: { secret: 'LEAK' },
        },
      },
      {
        id: 3,
        attempt: 1,
        target_id: 't1',
        backend: 'claude',
        kind: 'tool.call_end',
        entity_id: 'tool-call-1',
        data: {
          status: 'completed',
          result: { content: 'SECRET_FILE_CONTENT' },
        },
      },
    ]

    const attempts = reduceTranscriptEvents(events)
    const toolItem = attempts[0].items[0]
    expect(toolItem.type).toBe('tool_call')
    expect(toolItem.tool_name).toBe('read_file')
    expect(toolItem.status).toBe('completed')
    expect(toolItem.call_id).toBe('call-1')
    expect(toolItem.arguments).toBeUndefined()
    expect(toolItem.result).toBeUndefined()
  })

  it('distinguishes multiple attempts and failed attempts', () => {
    const events = [
      { id: 1, attempt: 1, target_id: 'primary', backend: 'codex', kind: 'attempt.started' },
      { id: 2, attempt: 1, target_id: 'primary', backend: 'codex', kind: 'assistant.text_delta', entity_id: 'm1', data: { text: 'failed try' } },
      { id: 3, attempt: 1, target_id: 'primary', backend: 'codex', kind: 'attempt.completed', data: { status: 'failed' } },
      { id: 4, attempt: 2, target_id: 'fallback', backend: 'pi', kind: 'attempt.started' },
      { id: 5, attempt: 2, target_id: 'fallback', backend: 'pi', kind: 'assistant.text_delta', entity_id: 'm2', data: { text: 'success try' } },
      { id: 6, attempt: 2, target_id: 'fallback', backend: 'pi', kind: 'attempt.completed', data: { status: 'succeeded' } },
    ]

    const attempts = reduceTranscriptEvents(events)
    expect(attempts).toHaveLength(2)
    expect(attempts[0].attempt).toBe(1)
    expect(attempts[0].status).toBe('failed')
    expect(attempts[0].backend).toBe('codex')
    expect(attempts[1].attempt).toBe(2)
    expect(attempts[1].status).toBe('succeeded')
    expect(attempts[1].backend).toBe('pi')
  })

  it('records stream notices and truncation', () => {
    const events = [
      { id: 1, attempt: 1, kind: 'stream.notice', data: { text: 'Notice message' } },
      { id: 2, attempt: 1, kind: 'stream.truncated', data: { reason: 'max_job_bytes' } },
    ]
    const attempts = reduceTranscriptEvents(events)
    expect(attempts[0].items[0].type).toBe('notice')
    expect(attempts[0].items[0].text).toBe('Notice message')
    expect(attempts[0].items[1].type).toBe('truncated')
    expect(attempts[0].items[1].reason).toBe('max_job_bytes')
  })
})

describe('JobTranscript component', () => {
  const sampleEntities = [
    {
      type: 'attempt',
      attempt: 1,
      target_id: 'primary-node',
      backend: 'codex',
      status: 'succeeded',
      started_at: '2026-09-11 10:00:00',
      items: [
        {
          type: 'assistant_message',
          entity_id: 'msg-1',
          text: 'Here is the response text.',
          status: 'completed',
        },
        {
          type: 'tool_call',
          entity_id: 'tool-1',
          tool_name: 'view_file',
          call_id: 'call-1',
          status: 'completed',
        },
      ],
    },
  ]

  it('renders transcript with attempt header, backend badge, and assistant message', () => {
    render(
      <JobTranscript
        entities={sampleEntities}
        status="live"
        streamStatus="active"
      />
    )

    expect(screen.getByText(/Attempt 1/i)).toBeInTheDocument()
    expect(screen.getByText('primary-node')).toBeInTheDocument()
    expect(screen.getByText('codex')).toBeInTheDocument()
    expect(screen.getByText('Here is the response text.')).toBeInTheDocument()
    expect(screen.getByText('view_file')).toBeInTheDocument()
  })

  it('announces connection updates in an accessible polite live region without flooding deltas', () => {
    const { rerender } = render(
      <JobTranscript
        entities={sampleEntities}
        status="connecting"
        streamStatus="active"
      />
    )

    const liveRegion = screen.getByTestId('transcript-live-region')
    expect(liveRegion).toHaveAttribute('aria-live', 'polite')
    expect(liveRegion).toHaveTextContent(/Connecting/i)

    rerender(
      <JobTranscript
        entities={sampleEntities}
        status="live"
        streamStatus="active"
      />
    )
    expect(liveRegion).toHaveTextContent(/Live stream connected/i)

    rerender(
      <JobTranscript
        entities={sampleEntities}
        status="reconnecting"
        streamStatus="active"
      />
    )
    expect(liveRegion).toHaveTextContent(/Reconnecting/i)
  })

  it('shows New activity button when user is scrolled up and new items arrive', () => {
    const { rerender } = render(
      <JobTranscript
        entities={sampleEntities}
        status="live"
        streamStatus="active"
      />
    )

    const container = screen.getByTestId('transcript-scroll-container')

    // Simulate user scrolled up
    Object.defineProperty(container, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(container, 'clientHeight', { value: 300, configurable: true })
    Object.defineProperty(container, 'scrollTop', { value: 100, configurable: true, writable: true })

    fireEvent.scroll(container)

    // New items arrive
    const updatedEntities = [
      {
        ...sampleEntities[0],
        items: [
          ...sampleEntities[0].items,
          {
            type: 'assistant_message',
            entity_id: 'msg-2',
            text: 'Newly arrived live text.',
            status: 'completed',
          },
        ],
      },
    ]

    rerender(
      <JobTranscript
        entities={updatedEntities}
        status="live"
        streamStatus="active"
      />
    )

    const newActivityBtn = screen.getByRole('button', { name: /New activity/i })
    expect(newActivityBtn).toBeInTheDocument()

    // Clicking New activity scrolls to bottom
    const scrollToMock = vi.fn()
    container.scrollTo = scrollToMock

    fireEvent.click(newActivityBtn)
    expect(newActivityBtn).not.toBeInTheDocument()
  })

  it('renders historical fallback note when stream is unavailable', () => {
    render(
      <JobTranscript
        entities={[]}
        status="complete"
        streamStatus="unavailable"
      />
    )

    expect(screen.getByText(/Transcript is not available for this job/i)).toBeInTheDocument()
  })

  it('renders assistant text, attempt header, and safe tool activity from persisted events without leaking secrets', () => {
    const rawEvents = [
      { id: 1, attempt: 1, target_id: 'prod-target', backend: 'codex', kind: 'attempt.started' },
      { id: 2, attempt: 1, target_id: 'prod-target', backend: 'codex', kind: 'assistant.message.started', entity_id: 'msg-1' },
      { id: 3, attempt: 1, target_id: 'prod-target', backend: 'codex', kind: 'assistant.text.delta', entity_id: 'msg-1', data: { text: 'Persisted assistant text.' } },
      { id: 4, attempt: 1, target_id: 'prod-target', backend: 'codex', kind: 'assistant.message.completed', entity_id: 'msg-1' },
      { id: 5, attempt: 1, target_id: 'prod-target', backend: 'codex', kind: 'tool.started', entity_id: 'tool-42', data: { tool: 'search_code', call_id: 'call-42', query: 'TOP_SECRET' } },
      { id: 6, attempt: 1, target_id: 'prod-target', backend: 'codex', kind: 'tool.completed', entity_id: 'tool-42', data: { status: 'completed', result: 'SECRET_DATA' } },
      { id: 7, attempt: 1, target_id: 'prod-target', backend: 'codex', kind: 'attempt.finished', data: { status: 'succeeded' } },
    ]

    const entities = reduceTranscriptEvents(rawEvents)

    render(
      <JobTranscript
        entities={entities}
        status="live"
        streamStatus="active"
      />
    )

    // Attempt header
    expect(screen.getByText('Attempt 1')).toBeInTheDocument()
    expect(screen.getByText('prod-target')).toBeInTheDocument()
    expect(screen.getByText('codex')).toBeInTheDocument()

    // Assistant text
    expect(screen.getByText('Persisted assistant text.')).toBeInTheDocument()

    // Safe tool activity
    expect(screen.getByText('search_code')).toBeInTheDocument()
    expect(screen.getByText('call-42')).toBeInTheDocument()

    // Redaction: secret fields must never render
    expect(screen.queryByText('TOP_SECRET')).not.toBeInTheDocument()
    expect(screen.queryByText('SECRET_DATA')).not.toBeInTheDocument()
  })

  it('preserves bounded DOM when virtualizer rows are unavailable for a large transcript', () => {
    const largeEntities = Array.from({ length: 100 }, (_, i) => ({
      type: 'attempt',
      attempt: i + 1,
      target_id: `target-${i + 1}`,
      backend: 'codex',
      status: 'succeeded',
      started_at: '2026-09-11 10:00:00',
      items: [
        {
          type: 'assistant_message',
          entity_id: `msg-${i + 1}`,
          text: `Message chunk for attempt ${i + 1}`,
          status: 'completed',
        },
        {
          type: 'tool_call',
          entity_id: `tool-${i + 1}`,
          tool_name: 'inspect_node',
          call_id: `call-${i + 1}`,
          status: 'completed',
        },
      ],
    }))

    const { container } = render(
      <JobTranscript
        entities={largeEntities}
        status="live"
        streamStatus="active"
      />
    )

    // Flat items would be 300 total (100 headers + 100 messages + 100 tool calls)
    // DOM nodes must remain strictly bounded even before layout measurement
    const renderedNodes = container.querySelectorAll('.transcript-attempt-header, .transcript-card')
    expect(renderedNodes.length).toBeLessThanOrEqual(20)
    expect(renderedNodes.length).toBeGreaterThan(0)
  })
})
