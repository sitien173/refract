import React from 'react'

const NAV_ITEMS = [
  { id: 'jobs', label: 'Live Console', hash: '#/jobs' },
  { id: 'projects', label: 'Projects', hash: '#/projects' },
  { id: 'targets', label: 'Targets', hash: '#/targets' },
  { id: 'diagnostics', label: 'Diagnostics', hash: '#/diagnostics' },
  { id: 'runtime', label: 'Runtime', hash: '#/runtime' },
]

export function NavRail({
  currentRoute = 'jobs',
  projects = [],
  selectedProjectId = '',
  onSelectProject = () => {},
}) {
  return (
    <nav
      role="navigation"
      aria-label="Main Navigation"
      data-testid="nav-rail"
      style={{
        width: '220px',
        flexShrink: 0,
        backgroundColor: 'var(--surface-neutral-02)',
        borderRight: '1px solid var(--border-subtle)',
        display: 'flex',
        flexDirection: 'column',
        padding: 'var(--padding-md)',
        gap: 'var(--gap-lg)',
        boxSizing: 'border-box',
      }}
    >
      <div>
        <label
          htmlFor="project-switcher"
          style={{
            display: 'block',
            fontSize: 'var(--font-size-xs)',
            fontWeight: 'var(--font-weight-semibold)',
            color: 'var(--text-description)',
            marginBottom: 'var(--gap-xs)',
          }}
        >
          Project
        </label>
        <select
          id="project-switcher"
          aria-label="Project"
          value={selectedProjectId || ''}
          onChange={(e) => onSelectProject(e.target.value)}
          style={{
            width: '100%',
            height: '32px',
            backgroundColor: 'var(--surface-neutral-01)',
            border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-button)',
            padding: '0 var(--padding-sm)',
            fontSize: 'var(--font-size-sm)',
            color: 'var(--text-default)',
            fontFamily: 'var(--font-family)',
          }}
        >
          {projects.map((proj) => (
            <option key={proj.id} value={proj.id}>
              {proj.alias || proj.id}
            </option>
          ))}
        </select>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap-xs)' }}>
        {NAV_ITEMS.map((item) => {
          const isActive = currentRoute === item.id
          return (
            <a
              key={item.id}
              href={item.hash}
              aria-current={isActive ? 'page' : undefined}
              style={{
                display: 'flex',
                alignItems: 'center',
                padding: 'var(--padding-sm) var(--padding-md)',
                borderRadius: 'var(--radius-button)',
                fontSize: 'var(--font-size-sm)',
                fontWeight: isActive
                  ? 'var(--font-weight-semibold)'
                  : 'var(--font-weight-regular)',
                color: isActive ? 'var(--interactive-default)' : 'var(--text-default)',
                backgroundColor: isActive
                  ? 'var(--surface-selected)'
                  : 'transparent',
                textDecoration: 'none',
                transition: 'background-color 0.15s ease',
              }}
            >
              {item.label}
            </a>
          )
        })}
      </div>
    </nav>
  )
}
