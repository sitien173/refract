export default function TabbedPanel({ tabs = [], activeTab, onTabChange, children }) {
  return (
    <div className="tabbed-panel">
      <div className="tabs-bar" role="tablist" aria-label="Sections">
        {tabs.map((tab) => {
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
              className={`tab-button ${isActive ? 'active' : ''}`}
              onClick={() => onTabChange(tab.id)}
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
