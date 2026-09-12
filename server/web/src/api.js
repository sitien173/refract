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

export async function getJobOutput(jobId, { after = 0, limit = 100 } = {}, signal) {
  const params = new URLSearchParams()
  if (after !== undefined && after !== null) params.set('after', String(after))
  if (limit !== undefined && limit !== null) params.set('limit', String(limit))
  const qs = params.toString() ? `?${params.toString()}` : ''
  return request(`/dashboard/api/jobs/${encodeURIComponent(jobId)}/output${qs}`, { signal })
}

export async function getTaskGuide(projectId) {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return request(`/dashboard/api/task-guide${query}`)
}

export async function mutateWithCsrf(path, { method = 'POST', body, expectedRevision } = {}) {
  if (!csrfToken) await getBootstrap()
  const headers = {
    Accept: 'application/json',
    'X-OpenMCP-CSRF': csrfToken,
  }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }
  if (expectedRevision !== undefined && expectedRevision !== null) {
    const rev = String(expectedRevision).trim()
    headers['If-Match'] = rev.startsWith('"') && rev.endsWith('"') ? rev : `"${rev}"`
  }
  const payloadBody = body !== undefined ? (typeof body === 'string' ? body : JSON.stringify(body)) : undefined

  let response
  for (let attempt = 0; attempt < 2; attempt += 1) {
    response = await fetch(path, {
      method,
      headers: {
        ...headers,
        'X-OpenMCP-CSRF': csrfToken,
      },
      body: payloadBody,
    })
    const payload = await readPayload(response)
    if (response.status !== 403 || payload.code !== 'forbidden' || attempt === 1) {
      if (!response.ok) {
        throw new DashboardApiError(payload.error || 'Dashboard request failed', response.status, payload)
      }
      return payload
    }
    await getBootstrap()
  }
  throw new DashboardApiError('Dashboard request failed', 403, {})
}

export async function getConfigurationTargets() {
  return request('/dashboard/api/configuration/targets')
}

export async function getConfigurationTarget(targetId) {
  return request(`/dashboard/api/configuration/targets/${encodeURIComponent(targetId)}`)
}

export async function createConfigurationTarget(targetData, expectedRevision) {
  return mutateWithCsrf('/dashboard/api/configuration/targets', {
    method: 'POST',
    body: targetData,
    expectedRevision,
  })
}

export async function updateConfigurationTarget(targetId, targetData, expectedRevision) {
  return mutateWithCsrf(`/dashboard/api/configuration/targets/${encodeURIComponent(targetId)}`, {
    method: 'PUT',
    body: targetData,
    expectedRevision,
  })
}

export async function deleteConfigurationTarget(targetId, expectedRevision) {
  return mutateWithCsrf(`/dashboard/api/configuration/targets/${encodeURIComponent(targetId)}`, {
    method: 'DELETE',
    expectedRevision,
  })
}

export async function getConfigurationProfiles() {
  return request('/dashboard/api/configuration/profiles')
}

export async function getConfigurationProfile(profileId) {
  return request(`/dashboard/api/configuration/profiles/${encodeURIComponent(profileId)}`)
}

export async function createConfigurationProfile(profileData, expectedRevision) {
  return mutateWithCsrf('/dashboard/api/configuration/profiles', {
    method: 'POST',
    body: profileData,
    expectedRevision,
  })
}

export async function updateConfigurationProfile(profileId, profileData, expectedRevision) {
  return mutateWithCsrf(`/dashboard/api/configuration/profiles/${encodeURIComponent(profileId)}`, {
    method: 'PUT',
    body: profileData,
    expectedRevision,
  })
}

export async function deleteConfigurationProfile(profileId, expectedRevision) {
  return mutateWithCsrf(`/dashboard/api/configuration/profiles/${encodeURIComponent(profileId)}`, {
    method: 'DELETE',
    expectedRevision,
  })
}

export async function getProjectProfileOverrides(projectId) {
  return request(`/dashboard/api/projects/${encodeURIComponent(projectId)}/profile-overrides`)
}

export async function getProjectProfileOverride(projectId, profileId) {
  return request(`/dashboard/api/projects/${encodeURIComponent(projectId)}/profile-overrides/${encodeURIComponent(profileId)}`)
}

export async function createProjectProfileOverride(projectId, overrideData, expectedRevision) {
  return mutateWithCsrf(`/dashboard/api/projects/${encodeURIComponent(projectId)}/profile-overrides`, {
    method: 'POST',
    body: overrideData,
    expectedRevision,
  })
}

export async function updateProjectProfileOverride(projectId, profileId, overrideData, expectedRevision) {
  return mutateWithCsrf(`/dashboard/api/projects/${encodeURIComponent(projectId)}/profile-overrides/${encodeURIComponent(profileId)}`, {
    method: 'PUT',
    body: overrideData,
    expectedRevision,
  })
}

export async function deleteProjectProfileOverride(projectId, profileId, expectedRevision) {
  return mutateWithCsrf(`/dashboard/api/projects/${encodeURIComponent(projectId)}/profile-overrides/${encodeURIComponent(profileId)}`, {
    method: 'DELETE',
    expectedRevision,
  })
}
