import { useRef } from 'react'

export default function TabbedPanel({ tabs = [], activeTab, onTabChange, children }) {
  const tabRefs = useRef([])

  function handleKeyDown(event, index) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key) || tabs.length === 0) return
    event.preventDefault()
    const activeIndex = tabs.findIndex((tab) => tab.id === activeTab)
    const currentIndex = activeIndex >= 0 ? activeIndex : index
    const nextIndex = event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? tabs.length - 1
        : (currentIndex + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
    const nextTab = tabs[nextIndex]
    onTabChange(nextTab.id)
    tabRefs.current[nextIndex]?.focus()
  }

  return (
    <div className="tabbed-panel">
      <div className="tabs-bar" role="tablist" aria-label="Sections">
        {tabs.map((tab, index) => {
          const isActive = activeTab === tab.id
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={isActive}
              aria-controls={`tabpanel-${tab.id}`}
              tabIndex={isActive ? 0 : -1}
              ref={(element) => { tabRefs.current[index] = element }}
              className={`tab-button ${isActive ? 'active' : ''}`}
              onClick={() => onTabChange(tab.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
            >
              <span>{tab.label}</span>
              {typeof tab.count === 'number' && (
                <span className="tab-count">{tab.count}</span>
              )}
            </button>
          )
        })}
      </div>
      <div
        className="tab-content"
        role="tabpanel"
        id={`tabpanel-${activeTab}`}
        aria-labelledby={`tab-${activeTab}`}
      >
        {children}
      </div>
    </div>
  )
}
