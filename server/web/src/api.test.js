import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  fetchOverview,
  fetchProjects,
  fetchProject,
  fetchProjectJobs,
  fetchJob,
  fetchJobOutput,
  fetchDiagnostics,
  fetchTargets,
  fetchProfiles,
  fetchSettings,
  getJobOutputUpdatesUrl,
  isTerminalState,
  TERMINAL_STATES,
} from './api.js'

describe('API client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('recognizes terminal states', () => {
    expect(TERMINAL_STATES).toEqual(['succeeded', 'failed', 'cancelled', 'interrupted'])
    expect(isTerminalState('succeeded')).toBe(true)
    expect(isTerminalState('running')).toBe(false)
  })

  it('fetches overview with GET /dashboard/api/overview', async () => {
    const payload = {
      daemon: { status: 'running', workers: 2, active_jobs: 1, queued_jobs: 0 },
      configuration: { valid: true, revision: 'rev1' },
      projects: 2,
      unhealthy_targets: 0,
    }
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => payload,
    })

    const result = await fetchOverview()
    expect(fetch).toHaveBeenCalledWith('/dashboard/api/overview', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
    expect(result).toEqual(payload)
  })

  it('fetches project jobs with GET /dashboard/api/projects/:id/jobs', async () => {
    const payload = { active: [], recent: [], more_recent: 0 }
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => payload,
    })

    const result = await fetchProjectJobs('proj-1')
    expect(fetch).toHaveBeenCalledWith('/dashboard/api/projects/proj-1/jobs', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
    expect(result).toEqual(payload)
  })

  it('fetches job output with cursor and limit query params', async () => {
    const payload = { events: [], cursor: 12, has_more: false, retained_from: 0, stream_status: 'complete' }
    fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => payload,
    })

    const result = await fetchJobOutput('job-1', { after: 5, limit: 50 })
    expect(fetch).toHaveBeenCalledWith('/dashboard/api/jobs/job-1/output?after=5&limit=50', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
    expect(result).toEqual(payload)
  })

  it('throws descriptive error on HTTP failure', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: async () => ({ error: 'Job not found', code: 'not_found' }),
    })

    await expect(fetchJob('nonexistent')).rejects.toThrow('Job not found')
  })
})
