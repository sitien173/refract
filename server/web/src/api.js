let csrfToken = ''

export class DashboardApiError extends Error {
  constructor(message, status, payload) {
    super(message)
    this.name = 'DashboardApiError'
    this.status = status
    this.payload = payload
  }
}

async function readPayload(response) {
  try {
    return await response.json()
  } catch {
    return {}
  }
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { Accept: 'application/json', ...(options.headers || {}) },
  })
  const payload = await readPayload(response)
  if (!response.ok) {
    throw new DashboardApiError(payload.error || 'Dashboard request failed', response.status, payload)
  }
  return payload
}

let bootstrapPromise = null

export async function getBootstrap() {
  if (!bootstrapPromise) {
    bootstrapPromise = request('/dashboard/api/bootstrap')
      .then((payload) => {
        csrfToken = payload.csrf_token || ''
        return payload
      })
      .finally(() => {
        bootstrapPromise = null
      })
  }
  return bootstrapPromise
}

export function clearCsrfToken() {
  csrfToken = ''
  bootstrapPromise = null
}

export async function getOverview() {
  return request('/dashboard/api/overview')
}

export async function getProjects() {
  return request('/dashboard/api/projects')
}

export async function getTargets() {
  return request('/dashboard/api/targets')
}

export async function getSettings() {
  return request('/dashboard/api/settings')
}

export async function getProfiles() {
  return request('/dashboard/api/profiles')
}

export async function getStatus() {
  return request('/dashboard/api/status')
}

export async function getConfiguration() {
  return request('/dashboard/api/configuration')
}

export async function getProject(projectId) {
  return request(`/dashboard/api/projects/${encodeURIComponent(projectId)}`)
}

export async function getProjectJobs(projectId) {
  return request(`/dashboard/api/projects/${encodeURIComponent(projectId)}/jobs`)
}

export async function getJob(jobId) {
  return request(`/dashboard/api/jobs/${encodeURIComponent(jobId)}`)
}

export async function getTaskGuide(projectId) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return request(`/dashboard/api/task-guide${query}`)
}

export async function getContextInstructions(projectId) {
  return request(`/dashboard/api/projects/${encodeURIComponent(projectId)}/context-instructions`)
}

export async function updateContextInstruction(projectId, workflow, instruction, expectedCurrent) {
  if (!csrfToken) await getBootstrap()
  const path = `/dashboard/api/projects/${encodeURIComponent(projectId)}/context-instructions/${encodeURIComponent(workflow)}`
  const body = JSON.stringify({ instruction, expected_current: expectedCurrent ?? '' })
  let response
  for (let attempt = 0; attempt < 2; attempt += 1) {
    response = await fetch(path, {
      method: 'PUT',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-OpenMCP-CSRF': csrfToken,
      },
      body,
    })
    const payload = await readPayload(response)
    if (response.status !== 403 || payload.code !== 'forbidden' || attempt === 1) {
      if (!response.ok) throw new DashboardApiError(payload.error || 'Dashboard request failed', response.status, payload)
      return payload
    }
    await getBootstrap()
  }
  throw new DashboardApiError('Dashboard request failed', 403, {})
}

export async function deleteContextInstruction(projectId, workflow, expectedCurrent) {
  if (!csrfToken) await getBootstrap()
  const path = `/dashboard/api/projects/${encodeURIComponent(projectId)}/context-instructions/${encodeURIComponent(workflow)}`
  const body = JSON.stringify({ expected_current: expectedCurrent ?? '' })
  let response
  for (let attempt = 0; attempt < 2; attempt += 1) {
    response = await fetch(path, {
      method: 'DELETE',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-OpenMCP-CSRF': csrfToken,
      },
      body,
    })
    const payload = await readPayload(response)
    if (response.status !== 403 || payload.code !== 'forbidden' || attempt === 1) {
      if (!response.ok) throw new DashboardApiError(payload.error || 'Dashboard request failed', response.status, payload)
      return payload
    }
    await getBootstrap()
  }
  throw new DashboardApiError('Dashboard request failed', 403, {})
}
