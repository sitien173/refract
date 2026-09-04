import { useEffect, useState } from 'react'
import AppShell from './components/AppShell'
import PageHeader from './components/PageHeader'
import ConfigHealth from './screens/ConfigHealth'
import Overview from './screens/Overview'
import Profiles from './screens/Profiles'
import ProjectDetail from './screens/ProjectDetail'
import Projects from './screens/Projects'
import RuntimeSettings from './screens/RuntimeSettings'
import Targets from './screens/Targets'

function parseLocation() {
  const pathname = window.location.pathname
  const clean = pathname.replace(/^\/dashboard\/?/, '')
  const parts = clean.split('/').filter(Boolean)

  if (parts.length === 0 || parts[0] === 'overview') {
    return { name: 'overview', projectId: '' }
  }
  if (parts[0] === 'projects') {
    if (parts.length > 1 && parts[1]) {
      return { name: 'project-detail', projectId: decodeURIComponent(parts[1]) }
    }
    return { name: 'projects', projectId: '' }
  }
  if (parts[0] === 'targets') {
    return { name: 'targets', projectId: '' }
  }
  if (parts[0] === 'profiles') {
    return { name: 'profiles', projectId: '' }
  }
  if (parts[0] === 'settings') {
    return { name: 'settings', projectId: '' }
  }
  if (parts[0] === 'configuration' || parts[0] === 'config') {
    return { name: 'configuration', projectId: '' }
  }

  return { name: 'not-found', projectId: '' }
}

export default function App() {
  const [route, setRoute] = useState(parseLocation)

  useEffect(() => {
    function handlePopState() {
      setRoute(parseLocation())
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  function navigate(destination) {
    let targetPath = destination
    if (!destination.startsWith('/')) {
      if (destination === 'overview') targetPath = '/dashboard/'
      else targetPath = `/dashboard/${destination}`
    }
    window.history.pushState({}, '', targetPath)
    setRoute(parseLocation())
  }

  let content = null
  let title = 'Overview'
  const activeNav = route.name === 'project-detail' ? 'projects' : route.name

  if (route.name === 'overview') {
    title = 'Overview'
    content = <Overview onNavigate={navigate} />
  } else if (route.name === 'projects') {
    title = 'Projects'
    content = <Projects onNavigate={navigate} />
  } else if (route.name === 'project-detail') {
    title = 'Project workspace'
    content = <ProjectDetail projectId={route.projectId} onNavigate={navigate} />
  } else if (route.name === 'targets') {
    title = 'Targets'
    content = <Targets />
  } else if (route.name === 'profiles') {
    title = 'Profiles'
    content = <Profiles />
  } else if (route.name === 'settings') {
    title = 'Runtime settings'
    content = <RuntimeSettings />
  } else if (route.name === 'configuration') {
    title = 'Configuration health'
    content = <ConfigHealth />
  } else {
    title = 'Not found'
    content = (
      <div className="page">
        <PageHeader title="Not found" description="That dashboard view does not exist." />
        <section className="panel empty-panel">
          <p>The requested page was not found.</p>
          <button
            type="button"
            className="button button-secondary button-sm"
            onClick={() => navigate('overview')}
          >
            Return to Overview
          </button>
        </section>
      </div>
    )
  }

  return (
    <AppShell route={activeNav} title={title} onNavigate={navigate}>
      {content}
    </AppShell>
  )
}
