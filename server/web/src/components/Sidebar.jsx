const navigation = [
  { id: 'overview', label: 'Overview' },
  { id: 'projects', label: 'Projects' },
  { id: 'targets', label: 'Targets' },
  { id: 'profiles', label: 'Profiles' },
  { id: 'jobs', label: 'Jobs' },
]

export default function Sidebar({ route, onNavigate }) {
  return (
    <aside className="app-sidebar" aria-label="Primary navigation">
      <div className="nav-section">Workspace</div>
      <nav>
        {navigation.map((item) => (
          <button
            type="button"
            className={`nav-item ${route === item.id ? 'active' : ''}`}
            aria-current={route === item.id ? 'page' : undefined}
            key={item.id}
            onClick={() => onNavigate(item.id)}
          >
            <span className="nav-icon" aria-hidden="true" />
            {item.label}
          </button>
        ))}
      </nav>
      <div className="nav-section nav-section-bottom">Operations</div>
      <nav>
        <button type="button" className={`nav-item ${route === 'settings' ? 'active' : ''}`} onClick={() => onNavigate('settings')}>
          <span className="nav-icon" aria-hidden="true" />
          Runtime settings
        </button>
        <button type="button" className={`nav-item ${route === 'configuration' ? 'active' : ''}`} onClick={() => onNavigate('configuration')}>
          <span className="nav-icon" aria-hidden="true" />
          Configuration health
        </button>
      </nav>
    </aside>
  )
}
