import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TabbedPanel from './TabbedPanel'

const tabs = [
  { id: 'one', label: 'One' },
  { id: 'two', label: 'Two' },
  { id: 'three', label: 'Three' },
]

describe('TabbedPanel keyboard navigation', () => {
  it.each([
    ['ArrowRight', 'two'],
    ['ArrowLeft', 'three'],
    ['Home', 'one'],
    ['End', 'three'],
  ])('activates and focuses the %s destination', (key, expectedId) => {
    const onTabChange = vi.fn()
    render(<TabbedPanel tabs={tabs} activeTab="one" onTabChange={onTabChange}>Content</TabbedPanel>)
    const active = screen.getByRole('tab', { name: 'One' })

    fireEvent.keyDown(active, { key })

    expect(onTabChange).toHaveBeenCalledWith(expectedId)
    expect(document.activeElement).toBe(screen.getByRole('tab', { name: expectedId === 'one' ? 'One' : expectedId === 'two' ? 'Two' : 'Three' }))
  })
})
