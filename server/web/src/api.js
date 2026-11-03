export const API_BASE = '/dashboard/api'

export const TERMINAL_STATES = Object.freeze([
  'succeeded',
  'failed',
  'cancelled',
  'interrupted',
])

export function isTerminalState(state) {
  return TERMINAL_STATES.includes(state)
}

async function requestJson(path, options = {}) {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    let message = response.statusText || `Request failed with status ${response.status}`
    let errorDetails = null
    try {
      errorDetails = await response.json()
      if (errorDetails && errorDetails.error) {
        message = errorDetails.error
      }
    } catch {
      // response was not JSON
    }
    const err = new Error(message)
    err.status = response.status
    err.details = errorDetails
    throw err
  }

  return response.json()
}

export async function fetchOverview() {
  return requestJson('/overview')
}

export async function fetchProjects() {
  return requestJson('/projects')
}

export async function fetchProject(projectId) {
  return requestJson(`/projects/${encodeURIComponent(projectId)}`)
}

export async function fetchProjectJobs(projectId) {
  return requestJson(`/projects/${encodeURIComponent(projectId)}/jobs`)
}

export async function fetchJob(jobId) {
  return requestJson(`/jobs/${encodeURIComponent(jobId)}`)
}

export async function fetchJobOutput(jobId, { after = 0, limit = 100 } = {}) {
  const params = new URLSearchParams()
  if (after !== undefined && after !== null) {
    params.set('after', String(after))
  }
  if (limit !== undefined && limit !== null) {
    params.set('limit', String(limit))
  }
  const query = params.toString() ? `?${params.toString()}` : ''
  return requestJson(`/jobs/${encodeURIComponent(jobId)}/output${query}`)
}

export async function fetchDiagnostics(params = {}) {
  const searchParams = new URLSearchParams()
  for (const [key, val] of Object.entries(params)) {
    if (val !== undefined && val !== null && val !== '') {
      searchParams.set(key, String(val))
    }
  }
  const query = searchParams.toString() ? `?${searchParams.toString()}` : ''
  return requestJson(`/diagnostics${query}`)
}

export async function fetchTargets() {
  return requestJson('/targets')
}

export async function fetchProfiles() {
  return requestJson('/profiles')
}

export async function fetchSettings() {
  return requestJson('/settings')
}

export function getJobOutputUpdatesUrl(jobId) {
  return `${API_BASE}/jobs/${encodeURIComponent(jobId)}/output/updates`
}
