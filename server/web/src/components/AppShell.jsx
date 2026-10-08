import Sidebar from './Sidebar'
import Topbar from './Topbar'

export default function AppShell({ route, title, project, onNavigate, children }) {
  return (
    <div className="app-shell">
      <Topbar title={title} project={project} onMenu={() => document.body.classList.toggle('sidebar-open')} />
      <Sidebar route={route} onNavigate={onNavigate} />
      <main className="app-main">{children}</main>
    </div>
  )
}
