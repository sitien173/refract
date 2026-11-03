import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TranscriptViewer } from './TranscriptViewer.jsx'

describe('TranscriptViewer component', () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, value: 600 })
    Object.defineProperty(HTMLElement.prototype, 'offsetWidth', { configurable: true, value: 800 })
    Element.prototype.getBoundingClientRect = vi.fn(() => ({
      width: 800,
      height: 600,
      top: 0,
      left: 0,
      bottom: 600,
      right: 800,
    }))
  })

  it('falls back to result text when stream_status is unavailable', () => {
    render(
      <TranscriptViewer
        events={[]}
        streamStatus="unavailable"
        fallbackText="Completed fallback output text"
      />
    )

    expect(screen.getByText('Completed fallback output text')).toBeInTheDocument()
  })

  it('renders notice when retained_from indicates pruned events', () => {
    const events = [
      { id: 50, kind: 'lifecycle.info', entity_id: 'e50', data: { message: 'Late event' } },
    ]
    render(
      <TranscriptViewer
        events={events}
        streamStatus="active"
        retainedFrom={50}
      />
    )

    expect(
      screen.getByText(/earlier output pruned/i)
    ).toBeInTheDocument()
  })

  it('renders lifecycle, stream.truncated, and stream.persistence_failed markers', () => {
    const events = [
      { id: 1, kind: 'job.started', entity_id: 'l1', data: { msg: 'Job started' } },
      { id: 2, kind: 'stream.truncated', entity_id: 't1', data: { reason: 'history limit reached' } },
      { id: 3, kind: 'stream.persistence_failed', entity_id: 'p1', data: { error: 'write timeout' } },
    ]

    render(
      <TranscriptViewer
        events={events}
        streamStatus="truncated"
        retainedFrom={1}
      />
    )

    expect(screen.getByText(/stream truncated/i)).toBeInTheDocument()
    expect(screen.getByText(/persistence failed/i)).toBeInTheDocument()
  })

  it('renders merged assistant text and paired tool calls', () => {
    const events = [
      { id: 1, kind: 'assistant.text_delta', entity_id: 'a1', data: { text: 'Analyzing ' } },
      { id: 2, kind: 'assistant.text_delta', entity_id: 'a1', data: { text: 'codebase...' } },
      {
        id: 3,
        kind: 'tool.started',
        entity_id: 't-grep',
        data: { name: 'grep', input: { pattern: 'TODO' } },
      },
      {
        id: 4,
        kind: 'tool.completed',
        entity_id: 't-grep',
        data: { output: '0 matches found' },
      },
    ]

    render(
      <TranscriptViewer
        events={events}
        streamStatus="complete"
        retainedFrom={1}
      />
    )

    expect(screen.getByText(/Analyzing codebase.../)).toBeInTheDocument()
    expect(screen.getByText(/grep/)).toBeInTheDocument()
    expect(screen.getByText(/0 matches found/)).toBeInTheDocument()
  })

  it('renders tool with failed status using negative badge', () => {
    const events = [
      {
        id: 1,
        kind: 'tool.started',
        entity_id: 'tool-fail',
        data: { tool: 'delete_file', input: { path: '/root/test' } },
      },
      {
        id: 2,
        kind: 'tool.completed',
        entity_id: 'tool-fail',
        data: { status: 'failed', error: 'permission denied' },
      },
    ]

    render(
      <TranscriptViewer
        events={events}
        streamStatus="active"
        retainedFrom={1}
      />
    )

    expect(screen.getByText('delete_file')).toBeInTheDocument()
    const badge = screen.getByText('failed')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('tds-tag--negative')
  })

  it('provides jump-to-live control and toggles follow tail', () => {
    const events = [
      { id: 1, kind: 'assistant.text_delta', entity_id: 'a1', data: { text: 'line 1' } },
      { id: 2, kind: 'assistant.text_delta', entity_id: 'a2', data: { text: 'line 2' } },
    ]

    const { container } = render(
      <TranscriptViewer
        events={events}
        streamStatus="active"
        retainedFrom={1}
      />
    )

    const scrollContainer = container.querySelector('[data-testid="transcript-scroll-area"]')
    expect(scrollContainer).toBeInTheDocument()

    // Simulate user scroll up
    Object.defineProperty(scrollContainer, 'scrollHeight', { value: 1000, configurable: true })
    Object.defineProperty(scrollContainer, 'clientHeight', { value: 300, configurable: true })
    Object.defineProperty(scrollContainer, 'scrollTop', { value: 0, writable: true, configurable: true })
    fireEvent.scroll(scrollContainer)

    const jumpButton = screen.queryByRole('button', { name: /jump to live/i })
    expect(jumpButton).toBeInTheDocument()
    fireEvent.click(jumpButton)
  })
})
