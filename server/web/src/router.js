import { useState, useEffect } from 'react'

export function parseHash(hash = '') {
  const clean = hash.replace(/^#\/?/, '').trim()
  if (!clean || clean.startsWith('jobs')) {
    const parts = clean.split('/')
    if (parts.length > 1 && parts[1]) {
      return { route: 'jobs', params: { id: decodeURIComponent(parts[1]) } }
    }
    return { route: 'jobs', params: {} }
  }
  if (clean.startsWith('projects')) {
    const parts = clean.split('/')
    if (parts.length > 1 && parts[1]) {
      return { route: 'projects', params: { id: decodeURIComponent(parts[1]) } }
    }
    return { route: 'projects', params: {} }
  }
  if (clean.startsWith('targets')) {
    return { route: 'targets', params: {} }
  }
  if (clean.startsWith('diagnostics')) {
    return { route: 'diagnostics', params: {} }
  }
  if (clean.startsWith('runtime')) {
    return { route: 'runtime', params: {} }
  }
  return { route: 'jobs', params: {} }
}

export function useHashRoute() {
  const [routeInfo, setRouteInfo] = useState(() => parseHash(window.location.hash))

  useEffect(() => {
    const handleHashChange = () => {
      setRouteInfo(parseHash(window.location.hash))
    }
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  return routeInfo
}

export function navigateTo(hash) {
  window.location.hash = hash.startsWith('#') ? hash : `#${hash}`
}
