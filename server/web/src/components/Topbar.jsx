import logoUrl from '../assets/flowforge-logo.png'

export default function Topbar({ title, project, onMenu }) {
  return (
    <header className="app-topbar">
      <button type="button" className="menu-button" aria-label="Open navigation" onClick={onMenu}>
        <span aria-hidden="true">≡</span>
      </button>
      <a className="brand" href="/dashboard/" aria-label="OpenMCP dashboard home">
        <img src={logoUrl} alt="FlowForge" />
        <span>OpenMCP</span>
      </a>
      <span className="topbar-divider" aria-hidden="true" />
      <h1>{title}</h1>
      {project && <span className="topbar-project">{project.alias}</span>}
      <div className="topbar-spacer" />
      <span className="topbar-local">Local administration</span>
    </header>
  )
}
