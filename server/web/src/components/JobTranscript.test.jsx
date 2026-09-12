import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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

  it('shows Jump to live button when user is scrolled up and new items arrive', () => {
    const { rerender } = render(
      <JobTranscript
        entities={sampleEntities}
        status="live"
        streamStatus="active"
      />
    )

    const container = screen.getByTestId('transcript-scroll-container')

    // Simulate scrollbar pointer navigation upward
    Object.defineProperty(container, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(container, 'clientHeight', { value: 300, configurable: true })
    Object.defineProperty(container, 'scrollTop', { value: 100, configurable: true, writable: true })

    fireEvent.pointerDown(container)
    fireEvent.scroll(container)
    fireEvent.pointerUp(container)

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

    const jumpToLiveBtn = screen.getByRole('button', { name: /jump to live/i })
    expect(jumpToLiveBtn).toBeInTheDocument()

    // Clicking Jump to live scrolls to bottom
    const scrollToMock = vi.fn()
    container.scrollTo = scrollToMock

    fireEvent.click(jumpToLiveBtn)
    expect(jumpToLiveBtn).not.toBeInTheDocument()
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

  describe('tool disclosure and payload formatting', () => {
    it('renders tool calls as collapsed native details and summary with tool name and status', () => {
      const toolEntity = [
        {
          type: 'attempt',
          attempt: 1,
          items: [
            {
              type: 'tool_call',
              entity_id: 'tool-1',
              tool_name: 'fetch_data',
              status: 'completed',
              call_id: 'call-1',
              input: { query: 'users' },
              output: { count: 5 },
            },
          ],
        },
      ]

      const { container } = render(<JobTranscript entities={toolEntity} status="live" />)

      const details = container.querySelector('details')
      expect(details).toBeInTheDocument()
      expect(details.open).toBe(false)

      const summary = container.querySelector('summary')
      expect(summary).toBeInTheDocument()
      expect(summary).toHaveTextContent('fetch_data')
      expect(summary).toHaveTextContent('completed')
    })

    it('renders separate Input and Output sections with indented JSON on expansion', () => {
      const toolEntity = [
        {
          type: 'attempt',
          attempt: 1,
          items: [
            {
              type: 'tool_call',
              entity_id: 'tool-1',
              tool_name: 'test_tool',
              status: 'completed',
              input: { key: 'value', count: 1 },
              output: ['item1', 'item2'],
            },
          ],
        },
      ]

      const { container } = render(<JobTranscript entities={toolEntity} status="live" />)

      const details = container.querySelector('details')
      fireEvent.click(container.querySelector('summary'))
      fireEvent(details, new Event('toggle'))

      expect(screen.getByText('Input')).toBeInTheDocument()
      expect(screen.getByText('Output')).toBeInTheDocument()

      const inputFormatted = JSON.stringify({ key: 'value', count: 1 }, null, 2)
      const outputFormatted = JSON.stringify(['item1', 'item2'], null, 2)

      const codes = container.querySelectorAll('.transcript-payload-code')
      expect(codes[0].textContent).toBe(inputFormatted)
      expect(codes[1].textContent).toBe(outputFormatted)
    })

    it('renders multiline text output preserving line breaks', () => {
      const toolEntity = [
        {
          type: 'attempt',
          attempt: 1,
          items: [
            {
              type: 'tool_call',
              entity_id: 'tool-1',
              tool_name: 'bash_exec',
              status: 'completed',
              input: 'echo "hello\nworld"',
              output: 'hello\nworld',
            },
          ],
        },
      ]

      const { container } = render(<JobTranscript entities={toolEntity} status="live" />)

      const details = container.querySelector('details')
      fireEvent.click(container.querySelector('summary'))
      fireEvent(details, new Event('toggle'))
      const codes = container.querySelectorAll('.transcript-payload-code')
      expect(codes[1].textContent).toBe('hello\nworld')
    })

    it('displays exact "Input not available" and "Output not available" when payloads are omitted', () => {
      const toolEntity = [
        {
          type: 'attempt',
          attempt: 1,
          items: [
            {
              type: 'tool_call',
              entity_id: 'tool-1',
              tool_name: 'legacy_tool',
              status: 'completed',
            },
          ],
        },
      ]

      const { container } = render(<JobTranscript entities={toolEntity} status="live" />)
      const details = container.querySelector('details')
      fireEvent.click(container.querySelector('summary'))
      fireEvent(details, new Event('toggle'))

      expect(screen.getByText('Input not available')).toBeInTheDocument()
      expect(screen.getByText('Output not available')).toBeInTheDocument()
    })

    it('renders valid falsy payloads visibly without falling back to unavailable', () => {
      const toolEntity = [
        {
          type: 'attempt',
          attempt: 1,
          items: [
            {
              type: 'tool_call',
              entity_id: 'tool-1',
              tool_name: 'falsy_tool',
              status: 'completed',
              input: false,
              output: 0,
            },
            {
              type: 'tool_call',
              entity_id: 'tool-2',
              tool_name: 'null_tool',
              status: 'completed',
              input: null,
              output: '',
            },
          ],
        },
      ]

      const { container } = render(<JobTranscript entities={toolEntity} status="live" />)
      container.querySelectorAll('details').forEach((d) => {
        d.open = true
        fireEvent(d, new Event('toggle'))
      })

      expect(screen.queryByText('Input not available')).not.toBeInTheDocument()
      expect(screen.queryByText('Output not available')).not.toBeInTheDocument()
      expect(container).toHaveTextContent('false')
      expect(container).toHaveTextContent('0')
      expect(container).toHaveTextContent('null')
    })

    it('uses normal interface typography for assistant text and monospace for IDs and raw payloads', () => {
      const entities = [
        {
          type: 'attempt',
          attempt: 1,
          items: [
            {
              type: 'assistant_message',
              entity_id: 'msg-1',
              text: 'Assistant prose text.',
              status: 'completed',
            },
            {
              type: 'tool_call',
              entity_id: 'tool-mono-id',
              tool_name: 'inspect',
              status: 'completed',
              call_id: 'call-12345',
              input: { param: 'test' },
            },
          ],
        },
      ]

      const { container } = render(<JobTranscript entities={entities} status="live" />)
      const details = container.querySelector('details')
      fireEvent.click(container.querySelector('summary'))
      fireEvent(details, new Event('toggle'))

      const assistantText = container.querySelector('.transcript-assistant-card .transcript-assistant-text, .transcript-assistant-card .transcript-text')
      expect(assistantText).toBeInTheDocument()
      expect(assistantText.tagName.toLowerCase()).not.toBe('pre')

      const idElement = container.querySelector('.transcript-identifier, .cell-code')
      expect(idElement).toBeInTheDocument()
      expect(idElement.tagName.toLowerCase()).toBe('code')

      const payloadCode = container.querySelector('.transcript-payload-code')
      expect(payloadCode).toBeInTheDocument()
      expect(payloadCode.tagName.toLowerCase()).toBe('pre')
    })

    it('renders payloads as inert text without interpreting HTML', () => {
      const toolEntity = [
        {
          type: 'attempt',
          attempt: 1,
          items: [
            {
              type: 'tool_call',
              entity_id: 'tool-html',
              tool_name: 'inject_tool',
              status: 'completed',
              input: '<b data-testid="injected-html">Bold</b>',
              output: '<script>alert(1)</script>',
            },
          ],
        },
      ]

      const { container } = render(<JobTranscript entities={toolEntity} status="live" />)
      const details = container.querySelector('details')
      fireEvent.click(container.querySelector('summary'))
      fireEvent(details, new Event('toggle'))

      expect(screen.queryByTestId('injected-html')).not.toBeInTheDocument()
      expect(container.querySelector('script')).not.toBeInTheDocument()
      expect(container).toHaveTextContent('<b data-testid="injected-html">Bold</b>')
      expect(container).toHaveTextContent('<script>alert(1)</script>')
    })

    it('preserves native keyboard semantics and synchronizes state via details onToggle', () => {
      const toolEntity = [
        {
          type: 'attempt',
          attempt: 1,
          items: [
            {
              type: 'tool_call',
              entity_id: 'tool-kbd',
              tool_name: 'test_kbd',
              status: 'completed',
              input: { param: 42 },
              output: 'result-ok',
            },
          ],
        },
      ]

      const { container } = render(<JobTranscript entities={toolEntity} status="live" />)
      const details = container.querySelector('details')
      const summary = container.querySelector('summary')

      expect(details.open).toBe(false)
      expect(screen.queryByText('Input')).not.toBeInTheDocument()

      // Native keyboard semantics preserved without custom preventDefault interception
      const enterEvent = new KeyboardEvent('keydown', { key: 'Enter', cancelable: true, bubbles: true })
      summary.dispatchEvent(enterEvent)
      expect(enterEvent.defaultPrevented).toBe(false)

      const spaceEvent = new KeyboardEvent('keydown', { key: ' ', cancelable: true, bubbles: true })
      summary.dispatchEvent(spaceEvent)
      expect(spaceEvent.defaultPrevented).toBe(false)

      // State synchronizes through details onToggle
      details.open = true
      fireEvent(details, new Event('toggle'))

      expect(screen.getByText('Input')).toBeInTheDocument()
      expect(screen.getByText('Output')).toBeInTheDocument()
      expect(container).toHaveTextContent('result-ok')

      details.open = false
      fireEvent(details, new Event('toggle'))

      expect(screen.queryByText('Input')).not.toBeInTheDocument()
    })
  })

  describe('measured virtualization and follow-live behavior', () => {
    it('initializes in follow-live mode and scrolls to live edge on mount', () => {
      const scrollToMock = vi.fn()
      HTMLElement.prototype.scrollTo = scrollToMock
      try {
        render(
          <JobTranscript
            entities={sampleEntities}
            status="live"
            streamStatus="active"
          />
        )
        const scrollContainer = screen.getByTestId('transcript-scroll-container')
        expect(scrollContainer).toBeInTheDocument()
        expect(scrollToMock).toHaveBeenCalledWith(
          expect.objectContaining({
            behavior: 'auto',
          })
        )
      } finally {
        delete HTMLElement.prototype.scrollTo
      }
    })

    it('follows assistant text growth and new entities while live following is active', () => {
      const { rerender } = render(
        <JobTranscript
          entities={sampleEntities}
          status="live"
          streamStatus="active"
        />
      )
      const scrollContainer = screen.getByTestId('transcript-scroll-container')
      const scrollToMock = vi.fn()
      scrollContainer.scrollTo = scrollToMock

      // Assistant growth
      const grownEntities = [
        {
          ...sampleEntities[0],
          items: [
            {
              ...sampleEntities[0].items[0],
              text: 'Here is the response text. Streaming more content now...',
            },
            sampleEntities[0].items[1],
          ],
        },
      ]

      rerender(
        <JobTranscript
          entities={grownEntities}
          status="live"
          streamStatus="active"
        />
      )

      expect(scrollToMock).toHaveBeenCalled()
      scrollToMock.mockClear()

      // New entity arrived
      const newEntityList = [
        {
          ...grownEntities[0],
          items: [
            ...grownEntities[0].items,
            {
              type: 'assistant_message',
              entity_id: 'msg-new',
              text: 'A brand new message arrived.',
              status: 'streaming',
            },
          ],
        },
      ]

      rerender(
        <JobTranscript
          entities={newEntityList}
          status="live"
          streamStatus="active"
        />
      )

      expect(scrollToMock).toHaveBeenCalled()
    })

    it('disables following on wheel up, touch scroll up, and keyboard upward navigation', () => {
      render(
        <JobTranscript
          entities={sampleEntities}
          status="live"
          streamStatus="active"
        />
      )
      const scrollContainer = screen.getByTestId('transcript-scroll-container')

      // Wheel upward
      fireEvent.wheel(scrollContainer, { deltaY: -50 })
      expect(screen.getByRole('button', { name: /jump to live/i })).toBeInTheDocument()

      // Reset by clicking Jump to live
      fireEvent.click(screen.getByRole('button', { name: /jump to live/i }))
      expect(screen.queryByRole('button', { name: /jump to live/i })).not.toBeInTheDocument()

      // Touch scroll up (dragging downward)
      fireEvent.touchStart(scrollContainer, { touches: [{ clientY: 100 }] })
      fireEvent.touchMove(scrollContainer, { touches: [{ clientY: 150 }] })
      expect(screen.getByRole('button', { name: /jump to live/i })).toBeInTheDocument()

      // Reset
      fireEvent.click(screen.getByRole('button', { name: /jump to live/i }))

      // Keyboard ArrowUp navigation
      fireEvent.keyDown(scrollContainer, { key: 'ArrowUp' })
      expect(screen.getByRole('button', { name: /jump to live/i })).toBeInTheDocument()
    })

    it('does not scroll viewport while following is disabled and keeps Jump to live visible across new content', () => {
      const { rerender } = render(
        <JobTranscript
          entities={sampleEntities}
          status="live"
          streamStatus="active"
        />
      )
      const scrollContainer = screen.getByTestId('transcript-scroll-container')

      // User scrolls up
      fireEvent.wheel(scrollContainer, { deltaY: -50 })

      const jumpBtn = screen.getByRole('button', { name: /jump to live/i })
      expect(jumpBtn).toBeInTheDocument()

      const scrollToMock = vi.fn()
      scrollContainer.scrollTo = scrollToMock

      // Content arrives while disabled
      const updatedEntities = [
        {
          ...sampleEntities[0],
          items: [
            ...sampleEntities[0].items,
            {
              type: 'assistant_message',
              entity_id: 'msg-disabled',
              text: 'Content while disabled',
              status: 'streaming',
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

      // Must NOT move viewport
      expect(scrollToMock).not.toHaveBeenCalled()
      // Jump to live remains persistent
      expect(screen.getByRole('button', { name: /jump to live/i })).toBeInTheDocument()
    })

    it('restores following on Jump to live activation and continues following subsequent content', () => {
      const { rerender } = render(
        <JobTranscript
          entities={sampleEntities}
          status="live"
          streamStatus="active"
        />
      )
      const scrollContainer = screen.getByTestId('transcript-scroll-container')

      // Scroll up to disable
      fireEvent.wheel(scrollContainer, { deltaY: -100 })
      const jumpBtn = screen.getByRole('button', { name: /jump to live/i })
      expect(jumpBtn).toBeInTheDocument()

      const scrollToMock = vi.fn()
      scrollContainer.scrollTo = scrollToMock

      // Click Jump to live
      fireEvent.click(jumpBtn)
      expect(screen.queryByRole('button', { name: /jump to live/i })).not.toBeInTheDocument()
      expect(scrollToMock).toHaveBeenCalled()

      scrollToMock.mockClear()

      // Subsequent content follows again
      const nextEntities = [
        {
          ...sampleEntities[0],
          items: [
            ...sampleEntities[0].items,
            {
              type: 'assistant_message',
              entity_id: 'msg-after-jump',
              text: 'Text after jumping live',
              status: 'completed',
            },
          ],
        },
      ]

      rerender(
        <JobTranscript
          entities={nextEntities}
          status="live"
          streamStatus="active"
        />
      )

      expect(scrollToMock).toHaveBeenCalled()
    })

    it('does not disable following during programmatic scrolling and measurements', () => {
      const { rerender } = render(
        <JobTranscript
          entities={sampleEntities}
          status="live"
          streamStatus="active"
        />
      )

      // Initial follow is active
      expect(screen.queryByRole('button', { name: /jump to live/i })).not.toBeInTheDocument()

      // Assistant text update (programmatic follow)
      const grown = [
        {
          ...sampleEntities[0],
          items: [
            {
              ...sampleEntities[0].items[0],
              text: 'Grown text',
            },
          ],
        },
      ]
      rerender(<JobTranscript entities={grown} status="live" streamStatus="active" />)

      // Following must NOT be disabled by the programmatic update
      expect(screen.queryByRole('button', { name: /jump to live/i })).not.toBeInTheDocument()
    })

    it('ignores delayed programmatic scroll events without timing assumptions', () => {
      const { rerender } = render(
        <JobTranscript
          entities={sampleEntities}
          status="live"
          streamStatus="active"
        />
      )

      const scrollContainer = screen.getByTestId('transcript-scroll-container')
      Object.defineProperty(scrollContainer, 'scrollHeight', { value: 1200, configurable: true })
      Object.defineProperty(scrollContainer, 'clientHeight', { value: 400, configurable: true })
      Object.defineProperty(scrollContainer, 'scrollTop', { value: 100, configurable: true, writable: true })

      rerender(
        <JobTranscript
          entities={[
            {
              ...sampleEntities[0],
              items: [
                {
                  ...sampleEntities[0].items[0],
                  text: 'Grown assistant text triggers scrollToLive',
                },
                sampleEntities[0].items[1],
              ],
            },
          ]}
          status="live"
          streamStatus="active"
        />
      )

      fireEvent.scroll(scrollContainer)
      expect(screen.queryByRole('button', { name: /jump to live/i })).not.toBeInTheDocument()

      fireEvent.pointerDown(scrollContainer)
      fireEvent.scroll(scrollContainer)
      expect(screen.getByRole('button', { name: /jump to live/i })).toBeInTheDocument()
      fireEvent.pointerUp(scrollContainer)
    })

    it('directly remeasures changed row heights on disclosure toggle, updates positions, ensures later-row non-overlap, and remeasures on responsive reflow', async () => {
      const toolEntities = [
        {
          type: 'attempt',
          attempt: 1,
          items: [
            {
              type: 'assistant_message',
              entity_id: 'msg-1',
              text: 'Introductory assistant message',
              status: 'completed',
            },
            {
              type: 'tool_call',
              entity_id: 'tool-measure-1',
              tool_name: 'test_measure_tool',
              status: 'completed',
              input: { query: 'run' },
              output: 'tool completed output',
            },
            {
              type: 'assistant_message',
              entity_id: 'msg-2',
              text: 'Subsequent assistant message following tool call',
              status: 'completed',
            },
          ],
        },
      ]

      let toolExpanded = false
      let reflowNarrow = false

      const originalGetBoundingClientRect = HTMLElement.prototype.getBoundingClientRect
      HTMLElement.prototype.getBoundingClientRect = function () {
        if (this.classList.contains('transcript-virtual-row')) {
          const index = this.getAttribute('data-index')
          if (index === '0') {
            return { width: reflowNarrow ? 400 : 800, height: reflowNarrow ? 100 : 72, top: 0, bottom: reflowNarrow ? 100 : 72, left: 0, right: 800 }
          }
          if (index === '1') {
            return { width: 800, height: 72, top: 0, bottom: 72, left: 0, right: 800 }
          }
          if (index === '2') {
            return { width: 800, height: toolExpanded ? 180 : 72, top: 0, bottom: toolExpanded ? 180 : 72, left: 0, right: 800 }
          }
          if (index === '3') {
            return { width: 800, height: 72, top: 0, bottom: 72, left: 0, right: 800 }
          }
        }
        return originalGetBoundingClientRect.call(this)
      }

      try {
        const { container } = render(
          <JobTranscript
            entities={toolEntities}
            status="live"
            streamStatus="active"
          />
        )

        let rows = container.querySelectorAll('.transcript-virtual-row')
        expect(rows.length).toBe(4)

        // Initially collapsed:
        // row 0: start 0, size 72
        // row 1: start 80, size 72
        // row 2: start 160, size 72
        // row 3: start 240, size 72
        expect(rows[2].style.transform).toBe('translateY(160px)')
        expect(rows[3].style.transform).toBe('translateY(240px)')

        // Verify later row does not overlap earlier row
        const initialRow2Start = 160
        const initialRow2Size = 72
        const initialRow3Start = 240
        expect(initialRow3Start).toBeGreaterThanOrEqual(initialRow2Start + initialRow2Size)

        // Expand tool disclosure
        toolExpanded = true
        const summary = container.querySelector('summary')
        const toolDetails = container.querySelector('details')
        fireEvent.click(summary)
        fireEvent(toolDetails, new Event('toggle'))

        // Remeasured with changed row height (180px)
        await waitFor(() => {
          rows = container.querySelectorAll('.transcript-virtual-row')
          expect(rows[2].style.transform).toBe('translateY(160px)')
          expect(rows[3].style.transform).toBe('translateY(348px)')
        })

        // Assert later-row non-overlap after expansion (348 >= 160 + 180 = 340)
        const expandedRow2Start = 160
        const expandedRow2Size = 180
        const expandedRow3Start = 348
        expect(expandedRow3Start).toBeGreaterThanOrEqual(expandedRow2Start + expandedRow2Size)

        // Collapse tool disclosure again
        toolExpanded = false
        fireEvent.click(summary)
        fireEvent(toolDetails, new Event('toggle'))

        await waitFor(() => {
          rows = container.querySelectorAll('.transcript-virtual-row')
          expect(rows[3].style.transform).toBe('translateY(240px)')
        })

        // Responsive reflow: row 0 wraps and height increases to 100px
        reflowNarrow = true
        fireEvent(window, new Event('resize'))

        await waitFor(() => {
          rows = container.querySelectorAll('.transcript-virtual-row')
          expect(rows[1].style.transform).toBe('translateY(108px)')
          expect(rows[2].style.transform).toBe('translateY(188px)')
          expect(rows[3].style.transform).toBe('translateY(268px)')
        })

        // Assert non-overlap after reflow
        expect(188).toBeGreaterThanOrEqual(108 + 72)
        expect(268).toBeGreaterThanOrEqual(188 + 72)
      } finally {
        HTMLElement.prototype.getBoundingClientRect = originalGetBoundingClientRect
      }
    })

    it('preserves strictly bounded mounted row elements for large transcripts in virtualizer', () => {
      const largeEntities = Array.from({ length: 50 }, (_, i) => ({
        type: 'attempt',
        attempt: i + 1,
        target_id: `target-${i + 1}`,
        items: [
          {
            type: 'assistant_message',
            entity_id: `msg-${i + 1}`,
            text: `Message chunk ${i + 1}`,
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

      const mountedRows = container.querySelectorAll('.transcript-virtual-row')
      expect(mountedRows.length).toBeLessThanOrEqual(20)
      expect(mountedRows.length).toBeGreaterThan(0)
    })
  })
})
