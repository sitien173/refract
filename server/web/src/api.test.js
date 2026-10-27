import { describe, expect, it, vi } from 'vitest'

function response(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  }
}

describe('dashboard API mutation retry boundary', () => {
  it('does not retry an unstructured forbidden response', async () => {
    vi.resetModules()
    const { updateConfigurationTarget } = await import('./api')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(200, { csrf_token: 'token' }))
      .mockResolvedValueOnce(response(403, { error: 'Forbidden' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(updateConfigurationTarget('target', { backend: 'codex' }, 'rev')).rejects.toMatchObject({ status: 403 })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('shares exactly one CSRF bootstrap request across concurrent mutations', async () => {
    vi.resetModules()
    const { deleteConfigurationTarget, updateConfigurationTarget } = await import('./api')
    let bootstrapCalls = 0
    const fetchMock = vi.fn().mockImplementation(async (url) => {
      if (url === '/dashboard/api/bootstrap') {
        bootstrapCalls += 1
        await new Promise((resolve) => setTimeout(resolve, 10))
        return response(200, { csrf_token: 'shared-csrf-token' })
      }
      return response(200, { id: 'ok' })
    })
    vi.stubGlobal('fetch', fetchMock)

    const [res1, res2] = await Promise.all([
      updateConfigurationTarget('target-1', { backend: 'codex' }, 'rev 1'),
      deleteConfigurationTarget('target-2', 'rev 2'),
    ])

    expect(res1).toEqual({ id: 'ok' })
    expect(res2).toEqual({ id: 'ok' })
    expect(bootstrapCalls).toBe(1)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[0][0]).toBe('/dashboard/api/bootstrap')
    expect(fetchMock.mock.calls[1][1].headers['X-Refract-CSRF']).toBe('shared-csrf-token')
    expect(fetchMock.mock.calls[2][1].headers['X-Refract-CSRF']).toBe('shared-csrf-token')
  })
})

describe('dashboard API diagnostics client', () => {
  it('queries diagnostics with optional bounded filters and cursor', async () => {
    vi.resetModules()
    const { getDiagnostics } = await import('./api')
    const fetchMock = vi.fn().mockResolvedValue(
      response(200, {
        reports: [
          {
            id: '10',
            job_id: 'job-1',
            category: 'protocol',
            created_at: '2026-10-27 10:00:00',
            expected: 'valid response',
            observed: 'malformed json',
            project_id: 'proj-1',
            current_state: 'failed',
          },
        ],
        next_before: '10',
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    const result = await getDiagnostics({
      projectId: 'proj-1',
      jobId: 'job-1',
      category: 'protocol',
      before: '20',
      limit: 10,
    })

    expect(result.reports).toHaveLength(1)
    expect(result.next_before).toBe('10')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const calledUrl = fetchMock.mock.calls[0][0]
    expect(calledUrl).toContain('/dashboard/api/diagnostics?')
    expect(calledUrl).toContain('project_id=proj-1')
    expect(calledUrl).toContain('job_id=job-1')
    expect(calledUrl).toContain('category=protocol')
    expect(calledUrl).toContain('before=20')
    expect(calledUrl).toContain('limit=10')
  })

  it('omits empty filter parameters to prevent 400 bad request from server', async () => {
    vi.resetModules()
    const { getDiagnostics } = await import('./api')
    const fetchMock = vi.fn().mockResolvedValue(response(200, { reports: [], next_before: null }))
    vi.stubGlobal('fetch', fetchMock)

    await getDiagnostics({ projectId: '', jobId: '', category: '' })

    expect(fetchMock).toHaveBeenCalledWith('/dashboard/api/diagnostics', expect.any(Object))
  })

  it('propagates abort signal to fetch', async () => {
    vi.resetModules()
    const { getDiagnostics } = await import('./api')
    const controller = new AbortController()
    const fetchMock = vi.fn().mockResolvedValue(response(200, { reports: [], next_before: null }))
    vi.stubGlobal('fetch', fetchMock)

    await getDiagnostics({}, controller.signal)

    expect(fetchMock).toHaveBeenCalledWith(
      '/dashboard/api/diagnostics',
      expect.objectContaining({ signal: controller.signal })
    )
  })
})
